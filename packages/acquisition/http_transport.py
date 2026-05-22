"""Transport HTTP — urllib (direct) ou requests+PySocks (Tor SOCKS5)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

logger = logging.getLogger(__name__)

IP_CHECK_URL = "https://api.ipify.org?format=json"


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    timing_ms: float
    final_url: str = ""


class HttpTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        ...


class UrllibTransport:
    """GET HTTP(S) avec proxy optionnel (HTTP uniquement) — une connexion par requête."""

    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        handlers = []
        if proxy_url:
            handlers.append(ProxyHandler({"http": proxy_url, "https": proxy_url}))
        opener = build_opener(*handlers) if handlers else None

        req = Request(url, method="GET", headers={"User-Agent": user_agent})
        started = time.perf_counter()
        resolved_url = url
        try:
            if opener is not None:
                resp = opener.open(req, timeout=timeout_s)
            else:
                resp = urlopen(req, timeout=timeout_s)
            try:
                body = resp.read()
                status = getattr(resp, "status", None) or resp.getcode() or 0
                headers = {k.lower(): v for k, v in resp.headers.items()}
                resolved_url = getattr(resp, "url", None) or url
            finally:
                resp.close()
        except HTTPError as exc:
            body = exc.read() if exc.fp else b""
            status = exc.code
            headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
            resolved_url = getattr(exc, "url", None) or url
        except URLError as exc:
            if proxy_url:
                raise ProxyTunnelError(str(exc)) from exc
            raise

        timing_ms = (time.perf_counter() - started) * 1000
        return HttpResponse(
            status=int(status),
            body=body,
            headers=headers,
            timing_ms=timing_ms,
            final_url=resolved_url,
        )


class DirectSessionTransport:
    """GET direct (sans proxy) via requests.Session — réutilise TCP/TLS (keep-alive)."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()

    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        import requests

        if proxy_url:
            return _requests_get_once(
                url,
                proxy_url=proxy_url,
                timeout_s=timeout_s,
                user_agent=user_agent,
            )

        started = time.perf_counter()
        try:
            resp = self._session.get(
                url,
                headers={"User-Agent": user_agent},
                timeout=timeout_s,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            raise OSError(str(exc)) from exc

        timing_ms = (time.perf_counter() - started) * 1000
        return HttpResponse(
            status=int(resp.status_code),
            body=resp.content,
            headers={k.lower(): v for k, v in resp.headers.items()},
            timing_ms=timing_ms,
            final_url=str(resp.url),
        )


def _requests_get_once(
    url: str,
    *,
    proxy_url: str,
    timeout_s: float,
    user_agent: str,
) -> HttpResponse:
    import requests

    proxies = {"http": proxy_url, "https": proxy_url}
    started = time.perf_counter()
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": user_agent},
            proxies=proxies,
            timeout=timeout_s,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ProxyTunnelError(str(exc)) from exc

    timing_ms = (time.perf_counter() - started) * 1000
    return HttpResponse(
        status=int(resp.status_code),
        body=resp.content,
        headers={k.lower(): v for k, v in resp.headers.items()},
        timing_ms=timing_ms,
        final_url=str(resp.url),
    )


class RequestsTransport:
    """GET via requests — supporte socks5h:// (DNS via Tor)."""

    def __init__(self, *, log_exit_ip: bool = False) -> None:
        self.log_exit_ip = log_exit_ip
        self._logged_ip = False

    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        import requests

        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}
            if self.log_exit_ip and not self._logged_ip:
                self._log_exit_ip_once(proxies, timeout_s, user_agent)

        started = time.perf_counter()
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": user_agent},
                proxies=proxies,
                timeout=timeout_s,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            if proxy_url:
                raise ProxyTunnelError(str(exc)) from exc
            raise

        timing_ms = (time.perf_counter() - started) * 1000
        return HttpResponse(
            status=int(resp.status_code),
            body=resp.content,
            headers={k.lower(): v for k, v in resp.headers.items()},
            timing_ms=timing_ms,
            final_url=str(resp.url),
        )

    def _log_exit_ip_once(
        self,
        proxies: dict[str, str],
        timeout_s: float,
        user_agent: str,
    ) -> None:
        import requests

        try:
            check = requests.get(
                IP_CHECK_URL,
                headers={"User-Agent": user_agent},
                proxies=proxies,
                timeout=min(timeout_s, 15.0),
            )
            data = check.json()
            logger.info("Tor sortie IP: %s", data.get("ip", data))
            self._logged_ip = True
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            logger.debug("Tor IP check ignoré: %s", exc)


class ProxyTunnelError(Exception):
    """Échec tunnel / connexion proxy."""


_default_transport: HttpTransport | None = None


def get_http_transport() -> HttpTransport:
    global _default_transport
    if _default_transport is None:
        from packages.acquisition.config import get_acquisition_config

        cfg = get_acquisition_config()
        if cfg.use_tor:
            _default_transport = RequestsTransport(log_exit_ip=cfg.tor_log_exit_ip)
        else:
            _default_transport = DirectSessionTransport()
    return _default_transport


def set_http_transport(transport: HttpTransport | None) -> None:
    global _default_transport
    _default_transport = transport
