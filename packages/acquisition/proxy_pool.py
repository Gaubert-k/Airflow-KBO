"""Pool de proxies — chargement, sélection pondérée, health-check optionnel."""

from __future__ import annotations

import logging
import random
import re
import threading
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen

from packages.acquisition.config import AcquisitionConfig
from packages.acquisition.http_transport import ProxyTunnelError, get_http_transport
from packages.acquisition.metrics import record_proxy_failure

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from packages.acquisition.config import AcquisitionConfig

_HOST_PORT_RE = re.compile(r"^[\w.-]+:\d{1,5}$")
_HEALTH_URL = "http://httpbin.org/ip"


@dataclass
class ProxyEntry:
    host: str
    port: int
    weight: float = 1.0
    healthy: bool = True

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class ProxyPool:
    entries: list[ProxyEntry] = field(default_factory=list)
    allow_direct: bool = True
    _rng: random.Random = field(default_factory=random.Random)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __len__(self) -> int:
        return len(self.entries)

    def pick(self) -> ProxyEntry | None:
        with self._lock:
            return self._pick_unlocked()

    def _pick_unlocked(self) -> ProxyEntry | None:
        candidates = [e for e in self.entries if e.healthy and e.weight > 0]
        if not candidates:
            return None
        total = sum(e.weight for e in candidates)
        r = self._rng.uniform(0, total)
        upto = 0.0
        for entry in candidates:
            upto += entry.weight
            if r <= upto:
                return entry
        return candidates[-1]

    def record_success(self, entry: ProxyEntry | None) -> None:
        if entry is None:
            return
        with self._lock:
            entry.weight = min(entry.weight * 1.1 + 0.1, 10.0)

    def ban_proxy_label(self, label: str, *, reason: str = "captcha") -> None:
        """Désactive un proxy (ex. page captcha KBO) — le suivant sera utilisé au retry."""
        with self._lock:
            self._ban_proxy_label_unlocked(label, reason=reason)

    def _ban_proxy_label_unlocked(self, label: str, *, reason: str = "captcha") -> None:
        for entry in self.entries:
            if entry.label == label:
                entry.healthy = False
                entry.weight = 0.0
                logger.warning(
                    "Proxy %s désactivé (%s) — rotation vers le suivant",
                    label,
                    reason,
                )
                return
        if label not in ("direct", "none"):
            logger.debug("Proxy %s introuvable dans le pool (%s)", label, reason)

    def healthy_count(self) -> int:
        return sum(1 for e in self.entries if e.healthy and e.weight > 0)

    def record_failure(self, entry: ProxyEntry | None, *, reason: str) -> None:
        label = entry.label if entry else "direct"
        record_proxy_failure(label, reason=reason)
        if entry is None:
            return
        with self._lock:
            entry.weight = max(entry.weight * 0.5, 0.01)
            if reason in ("tunnel", "timeout", "connection"):
                entry.healthy = False

    def filter_working_sync(self, config: AcquisitionConfig) -> int:
        """Teste chaque proxy (HTTPS) et désactive ceux qui ne répondent pas."""
        probe_url = config.proxy_probe_url
        timeout_s = min(config.proxy_probe_timeout_s, config.http_timeout_s)
        transport = get_http_transport()
        ok = 0
        for entry in list(self.entries):
            try:
                transport.get(
                    probe_url,
                    proxy_url=entry.url,
                    timeout_s=timeout_s,
                    user_agent=config.user_agent,
                )
                entry.healthy = True
                ok += 1
            except (ProxyTunnelError, OSError, TimeoutError) as exc:
                entry.healthy = False
                entry.weight = 0.0
                logger.debug("proxy probe failed %s: %s", entry.label, exc)
        return ok

    @classmethod
    def from_config(cls, config: AcquisitionConfig) -> ProxyPool:
        if not config.use_proxies:
            return cls(entries=[], allow_direct=True)
        entries: list[ProxyEntry] = []
        entries.extend(_parse_proxy_file(config.proxy_file))
        for url in config.proxy_urls:
            entries.extend(_fetch_proxy_list_url(url))
        pool = cls(entries=entries, allow_direct=config.allow_direct)
        if config.proxy_healthcheck and entries:
            pool._schedule_healthchecks(config)
        return pool

    def _schedule_healthchecks(self, config: AcquisitionConfig) -> None:
        def _run() -> None:
            transport = get_http_transport()
            for entry in list(self.entries):
                try:
                    transport.get(
                        _HEALTH_URL,
                        proxy_url=entry.url,
                        timeout_s=min(config.http_timeout_s, 10.0),
                        user_agent=config.user_agent,
                    )
                    entry.healthy = True
                except (ProxyTunnelError, OSError, TimeoutError) as exc:
                    entry.healthy = False
                    record_proxy_failure(entry.label, reason="healthcheck")
                    logger.debug("proxy healthcheck failed %s: %s", entry.label, exc)

        threading.Thread(target=_run, name="proxy-healthcheck", daemon=True).start()


def _parse_proxy_line(line: str) -> ProxyEntry | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if not _HOST_PORT_RE.match(stripped):
        return None
    host, port_str = stripped.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        return None
    if port < 1 or port > 65535:
        return None
    return ProxyEntry(host=host, port=port)


def _parse_proxy_file(path: Path) -> list[ProxyEntry]:
    if not path.is_file():
        return []
    entries: list[ProxyEntry] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = _parse_proxy_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def _fetch_proxy_list_url(url: str) -> list[ProxyEntry]:
    try:
        with urlopen(url, timeout=15) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except OSError as exc:
        logger.warning("failed to download proxy list from %s: %s", url, exc)
        return []
    return [e for line in text.splitlines() if (e := _parse_proxy_line(line)) is not None]
