"""Captcha → échec immédiat de la task (pas de retry)."""

from __future__ import annotations

from pathlib import Path

import pytest
from packages.acquisition.config import AcquisitionConfig
from packages.acquisition.fetch import fetch
from packages.acquisition.http_transport import HttpResponse, set_http_transport
from packages.acquisition.models import CaptchaBlockedError, FetchJob
from packages.acquisition.proxy_pool import ProxyPool
from packages.acquisition.worker import _process_job


class _CaptchaTransport:
    def get(self, url: str, *, proxy_url: str | None, timeout_s: float, user_agent: str):
        return HttpResponse(
            status=200,
            body=b"<html>captcha</html>",
            headers={"content-type": "text/html"},
            timing_ms=1.0,
            final_url="https://kbopub.economie.fgov.be/kbopub/captchaform.html",
        )


@pytest.fixture
def cfg(tmp_path: Path) -> AcquisitionConfig:
    return AcquisitionConfig(
        min_delay_s=0.0,
        max_delay_s=0.0,
        max_retries=3,
        use_proxies=False,
        proxy_file=tmp_path / "proxies.txt",
        proxy_urls=(),
        allow_direct=True,
        use_tor=False,
        tor_proxies=(),
        kbo_direct_first=True,
        tor_loop=False,
        tor_loop_min_interval_s=0.0,
        tor_log_exit_ip=False,
        proxy_healthcheck=False,
        proxy_filter_at_start=False,
        proxy_probe_url="https://example.test/",
        proxy_probe_timeout_s=5.0,
        worker_id="test",
        http_timeout_s=5.0,
        user_agent="test",
    )


def test_captcha_raises_and_aborts(cfg: AcquisitionConfig) -> None:
    set_http_transport(_CaptchaTransport())
    pool = ProxyPool(entries=[], allow_direct=True)
    job = FetchJob(
        source="kbo",
        enterprise_number="0123456789",
        doc_type="enterprise_detail",
        url="https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
    )
    with pytest.raises(CaptchaBlockedError, match="Captcha"):
        _process_job(job, pool, cfg)
