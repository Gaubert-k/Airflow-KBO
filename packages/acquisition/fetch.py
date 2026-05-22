"""T02.2 — fetch(job, proxy_pool) -> FetchResult."""

from __future__ import annotations

import time

from packages.acquisition.config import AcquisitionConfig, get_acquisition_config
from packages.acquisition.http_transport import ProxyTunnelError, get_http_transport
from packages.acquisition.metrics import record_proxy_failure
from packages.acquisition.models import FetchJob, FetchResult
from packages.acquisition.proxy_pool import ProxyEntry, ProxyPool


def fetch(
    job: FetchJob,
    proxy_pool: ProxyPool,
    *,
    config: AcquisitionConfig | None = None,
    attempt_count: int = 1,
    force_proxy_url: str | None = None,
    force_proxy_label: str | None = None,
) -> FetchResult:
    """
    Exécute une requête GET pour le job.

    Une seule tentative HTTP ; les retries sont gérés par le worker via validate_fetch.
    """
    cfg = config or get_acquisition_config()
    transport = get_http_transport()

    if force_proxy_label is not None or force_proxy_url is not None:
        proxy_url = force_proxy_url
        proxy_label = force_proxy_label or ("direct" if not force_proxy_url else "tor")
        proxy_entry = None
    else:
        proxy_entry = proxy_pool.pick()
        proxy_url = proxy_entry.url if proxy_entry else None
        proxy_label = proxy_entry.label if proxy_entry else "direct"

    if proxy_entry is None and not proxy_pool.allow_direct and force_proxy_label is None:
        return FetchResult(
            body=None,
            http_status=None,
            headers={},
            timing_ms=0.0,
            proxy_or_ip="none",
            attempt_count=attempt_count,
            url=job.url,
            error="no_proxy_available",
        )

    try:
        response = transport.get(
            job.url,
            proxy_url=proxy_url,
            timeout_s=cfg.http_timeout_s,
            user_agent=cfg.user_agent,
        )
        proxy_pool.record_success(proxy_entry)
        return FetchResult(
            body=response.body,
            http_status=response.status,
            headers=response.headers,
            timing_ms=response.timing_ms,
            proxy_or_ip=proxy_label,
            attempt_count=attempt_count,
            url=job.url,
            final_url=response.final_url or job.url,
        )
    except ProxyTunnelError as exc:
        proxy_pool.record_failure(proxy_entry, reason="tunnel")
        record_proxy_failure(proxy_label, reason="PROXY_TUNNEL_FAILED")
        return FetchResult(
            body=None,
            http_status=None,
            headers={},
            timing_ms=0.0,
            proxy_or_ip=proxy_label,
            attempt_count=attempt_count,
            url=job.url,
            error=str(exc),
        )
    except OSError as exc:
        proxy_pool.record_failure(proxy_entry, reason="connection")
        return FetchResult(
            body=None,
            http_status=None,
            headers={},
            timing_ms=0.0,
            proxy_or_ip=proxy_label,
            attempt_count=attempt_count,
            url=job.url,
            error=str(exc),
        )


def polite_delay(config: AcquisitionConfig, *, source: str | None = None) -> None:
    """Délai aléatoire entre requêtes (MS-02 courtoisie), sauf sources exemptées."""
    from packages.acquisition.scrape_policy import skip_inter_request_delay

    if source is not None and skip_inter_request_delay(source):
        return

    import random

    lo = min(config.min_delay_s, config.max_delay_s)
    hi = max(config.min_delay_s, config.max_delay_s)
    if hi <= 0:
        return
    time.sleep(random.uniform(lo, hi))
