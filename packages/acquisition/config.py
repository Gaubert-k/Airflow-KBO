"""Configuration MS-02 — variables d'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


@dataclass(frozen=True)
class AcquisitionConfig:
    min_delay_s: float
    max_delay_s: float
    max_retries: int
    use_proxies: bool
    proxy_file: Path
    proxy_urls: tuple[str, ...]
    allow_direct: bool
    use_tor: bool
    tor_proxies: tuple[str, ...]
    kbo_direct_first: bool
    tor_loop: bool
    tor_loop_min_interval_s: float
    tor_log_exit_ip: bool
    proxy_healthcheck: bool
    proxy_filter_at_start: bool
    proxy_probe_url: str
    proxy_probe_timeout_s: float
    worker_id: str
    http_timeout_s: float
    user_agent: str

    @classmethod
    def from_env(cls) -> AcquisitionConfig:
        root = find_repo_root()

        def _float(name: str, default: float) -> float:
            raw = os.environ.get(name, "").strip()
            return float(raw) if raw else default

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name, "").strip()
            return int(raw) if raw else default

        use_proxies = os.environ.get("ACQUISITION_USE_PROXIES", "0").strip() in (
            "1",
            "true",
            "True",
        )

        proxy_file = root / "data" / "proxies" / "proxies.txt"
        proxy_urls: tuple[str, ...] = ()
        if use_proxies:
            proxy_file_raw = os.environ.get("ACQUISITION_PROXY_FILE", "").strip()
            candidates: list[Path] = []
            if proxy_file_raw:
                candidates.append(Path(proxy_file_raw))
            candidates.extend(
                (
                    root / "data" / "proxies" / "proxies.txt",
                    root / "scripts" / "proxies-pool.txt",
                )
            )
            for path in candidates:
                if path.is_file():
                    proxy_file = path
                    break
            urls_raw = os.environ.get("ACQUISITION_PROXY_URLS", "").strip()
            proxy_urls = tuple(u.strip() for u in urls_raw.split(",") if u.strip())

        allow_direct = os.environ.get("ACQUISITION_ALLOW_DIRECT", "1").strip() not in (
            "0",
            "false",
            "False",
        )
        use_tor = os.environ.get("ACQUISITION_USE_TOR", "0").strip() in ("1", "true", "True")
        tor_raw = os.environ.get(
            "ACQUISITION_TOR_PROXIES",
            "socks5h://tor1:9050,socks5h://tor2:9050,socks5h://tor3:9050",
        ).strip()
        tor_proxies = tuple(p.strip() for p in tor_raw.split(",") if p.strip())
        kbo_direct_first = os.environ.get("ACQUISITION_KBO_DIRECT_FIRST", "1").strip() not in (
            "0",
            "false",
            "False",
        )
        tor_loop = os.environ.get("ACQUISITION_TOR_LOOP", "0").strip() in ("1", "true", "True")
        tor_loop_min_interval_s = _float("ACQUISITION_TOR_LOOP_MIN_INTERVAL_S", 600.0)
        tor_log_exit_ip = os.environ.get("ACQUISITION_TOR_LOG_EXIT_IP", "0").strip() in (
            "1",
            "true",
            "True",
        )
        healthcheck = os.environ.get("ACQUISITION_PROXY_HEALTHCHECK", "0").strip() in (
            "1",
            "true",
            "True",
        )
        proxy_filter = os.environ.get("ACQUISITION_PROXY_FILTER_AT_START", "0").strip() in (
            "1",
            "true",
            "True",
        )
        probe_url = os.environ.get(
            "ACQUISITION_PROXY_PROBE_URL",
            os.environ.get(
                "KBO_PUBLIC_BASE_URL",
                "https://kbopub.economie.fgov.be/kbopub/",
            ),
        ).strip() or "https://kbopub.economie.fgov.be/kbopub/"

        return cls(
            use_proxies=use_proxies,
            min_delay_s=_float("ACQUISITION_MIN_DELAY_S", 0.5),
            max_delay_s=_float("ACQUISITION_MAX_DELAY_S", 2.0),
            max_retries=_int("ACQUISITION_MAX_RETRIES", 3),
            proxy_file=proxy_file,
            proxy_urls=proxy_urls,
            allow_direct=allow_direct,
            use_tor=use_tor,
            tor_proxies=tor_proxies,
            kbo_direct_first=kbo_direct_first,
            tor_loop=tor_loop,
            tor_loop_min_interval_s=tor_loop_min_interval_s,
            tor_log_exit_ip=tor_log_exit_ip,
            proxy_healthcheck=healthcheck,
            proxy_filter_at_start=proxy_filter,
            proxy_probe_url=probe_url,
            proxy_probe_timeout_s=_float("ACQUISITION_PROXY_PROBE_TIMEOUT_S", 8.0),
            worker_id=os.environ.get("ACQUISITION_WORKER_ID", "acquisition-worker-1").strip()
            or "acquisition-worker-1",
            http_timeout_s=_float("ACQUISITION_HTTP_TIMEOUT_S", 30.0),
            user_agent=os.environ.get(
                "ACQUISITION_USER_AGENT",
                "belgian-companies-platform/0.1 (+acquisition; MS-02)",
            ).strip(),
        )


def get_acquisition_config() -> AcquisitionConfig:
    return AcquisitionConfig.from_env()
