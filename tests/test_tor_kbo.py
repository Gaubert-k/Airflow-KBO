"""Tests Tor KBO — transport, scheduler, passes worker."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from packages.acquisition.config import AcquisitionConfig
from packages.acquisition.http_transport import (
    HttpResponse,
    RequestsTransport,
    DirectSessionTransport,
    UrllibTransport,
    get_http_transport,
    set_http_transport,
)
from packages.acquisition.models import CaptchaBlockedError, FetchJob
from packages.acquisition.proxy_pool import ProxyPool
from packages.acquisition.tor_strategy import (
    KboTorLaneCoordinator,
    KboTorScheduler,
    build_kbo_lanes,
    is_kbo_rate_or_captcha,
    wait_tor_loop_cycle_interval,
)
from packages.acquisition.worker import (
    _process_job,
    _scrape_kbo_tor_passes,
    _scrape_statutes_direct_passes,
)


def _cfg(tmp_path: Path, **overrides) -> AcquisitionConfig:
    base = dict(
        min_delay_s=0.0,
        max_delay_s=0.0,
        max_retries=2,
        use_proxies=False,
        proxy_file=tmp_path / "proxies.txt",
        proxy_urls=(),
        allow_direct=True,
        use_tor=True,
        tor_proxies=("socks5h://tor1:9050", "socks5h://tor2:9050"),
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
    base.update(overrides)
    return AcquisitionConfig(**base)


def test_build_kbo_lanes_direct_then_tor() -> None:
    cfg = _cfg(Path("/tmp"), kbo_direct_first=True, tor_proxies=("socks5h://tor1:9050",))
    lanes = build_kbo_lanes(cfg)
    assert [lane.name for lane in lanes] == ["direct", "tor1"]


def test_coordinator_escalate_on_captcha_is_immediate() -> None:
    lanes = build_kbo_lanes(
        _cfg(Path("/tmp"), kbo_direct_first=True, tor_proxies=("socks5h://t1:9050",)),
    )
    coord = KboTorLaneCoordinator(lanes=lanes, tor_loop=False, tor_loop_min_interval_s=0.0)
    assert coord.current_lane().name == "direct"
    assert coord.escalate_on_captcha() is True
    assert coord.current_lane().name == "tor1"


def test_kbo_tor_scheduler_advance_and_exhausted() -> None:
    lanes = build_kbo_lanes(
        _cfg(Path("/tmp"), kbo_direct_first=False, tor_proxies=("socks5h://t1:9050", "socks5h://t2:9050")),
    )
    sched = KboTorScheduler(lanes=lanes, tor_loop=False)
    assert sched.current_lane().name == "tor1"
    assert sched.advance_lane() is True
    assert sched.current_lane().name == "tor2"
    assert sched.advance_lane() is False


def test_wait_tor_loop_cycle_interval_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("packages.acquisition.tor_strategy.time.sleep", _fake_sleep)
    monkeypatch.setattr("packages.acquisition.tor_strategy.time.monotonic", lambda: 1000.0)

    # Premier cycle : pas d'attente
    t0 = wait_tor_loop_cycle_interval(min_interval_s=600.0, last_cycle_completed_at=None)
    assert not slept

    # Simule fin de cycle à t=1000, maintenant t=1100 → il reste 500 s
    monkeypatch.setattr(
        "packages.acquisition.tor_strategy.time.monotonic",
        lambda: 1100.0,
    )
    wait_tor_loop_cycle_interval(min_interval_s=600.0, last_cycle_completed_at=t0)
    assert slept == [500.0]


def test_is_kbo_rate_or_captcha() -> None:
    assert is_kbo_rate_or_captcha("CAPTCHA_SUSPECT")
    assert is_kbo_rate_or_captcha("HTTP_4XX")
    assert not is_kbo_rate_or_captcha("HTTP_404")


class _LaneTransport:
    """direct et tor1 = captcha ; tor2 = succès (bascule immédiate attendue)."""

    def __init__(self) -> None:
        self.proxy_labels: list[str | None] = []

    def get(self, url: str, *, proxy_url: str | None, timeout_s: float, user_agent: str):
        self.proxy_labels.append(proxy_url)
        if proxy_url in (None, "socks5h://tor1:9050"):
            return HttpResponse(
                status=200,
                body=b"<html>captcha</html>",
                headers={"content-type": "text/html"},
                timing_ms=1.0,
                final_url="https://kbopub.economie.fgov.be/kbopub/captchaform.html",
            )
        return HttpResponse(
            status=200,
            body=b"<!DOCTYPE html><html><body><p>OK entreprise belge avec assez de contenu.</p></body></html>",
            headers={"content-type": "text/html"},
            timing_ms=1.0,
            final_url=url,
        )


@pytest.fixture
def tor_cfg(tmp_path: Path) -> AcquisitionConfig:
    return _cfg(tmp_path, kbo_direct_first=False, tor_proxies=("socks5h://tor1:9050",))


def test_process_job_tor_lane_no_raise_on_captcha(tor_cfg: AcquisitionConfig) -> None:
    set_http_transport(_LaneTransport())
    pool = ProxyPool(entries=[], allow_direct=True)
    from packages.acquisition.tor_strategy import KboEgressLane

    lane = KboEgressLane("tor1", "socks5h://tor1:9050")
    job = FetchJob(
        source="kbo",
        enterprise_number="0123456789",
        doc_type="enterprise_detail",
        url="https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
    )
    ok, reason = _process_job(job, pool, tor_cfg, egress_lane=lane, raise_on_captcha=False)
    assert ok is False
    assert reason == "CAPTCHA_SUSPECT"


def test_scrape_kbo_tor_passes_rotates_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDFS_LOCAL_ROOT", str(tmp_path / "hdfs-stub"))
    monkeypatch.setenv("HDFS_RAW_ROOT", "hdfs://localhost:9000/raw/v1")
    transport = _LaneTransport()
    set_http_transport(transport)
    cfg = _cfg(
        tmp_path,
        kbo_direct_first=True,
        tor_proxies=("socks5h://tor1:9050", "socks5h://tor2:9050"),
    )
    adapter = MagicMock()
    adapter.source = "kbo"
    adapter.build_urls.return_value = [
        FetchJob(
            source="kbo",
            enterprise_number="0123456789",
            doc_type="enterprise_detail",
            url="https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
        )
    ]

    report = _scrape_kbo_tor_passes(
        ["0123456789"],
        adapter=adapter,
        cfg=cfg,
        tor_loop=False,
        kbo_direct_first=True,
        parallel_requests_per_site=1,
    )
    assert report["succeeded"] == 1
    assert report["kbo_ok_numbers"] == ["0123456789"]
    assert report["tor_lanes_used"] == ["direct", "tor1", "tor2"]
    assert None in transport.proxy_labels
    assert "socks5h://tor2:9050" in transport.proxy_labels


def test_scrape_kbo_tor_exhausted_raises(tmp_path: Path) -> None:
    set_http_transport(_LaneTransport())
    cfg = _cfg(
        tmp_path,
        kbo_direct_first=True,
        tor_proxies=("socks5h://tor1:9050",),
    )
    adapter = MagicMock()
    adapter.source = "kbo"
    adapter.build_urls.return_value = [
        FetchJob(
            source="kbo",
            enterprise_number="0999999999",
            doc_type="enterprise_detail",
            url="https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
        )
    ]
    with pytest.raises(CaptchaBlockedError, match="lanes"):
        _scrape_kbo_tor_passes(
            ["0999999999"],
            adapter=adapter,
            cfg=cfg,
            tor_loop=False,
            kbo_direct_first=True,
            parallel_requests_per_site=1,
        )


def test_get_http_transport_uses_requests_when_tor_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    set_http_transport(None)
    monkeypatch.setenv("ACQUISITION_USE_TOR", "1")
    transport = get_http_transport()
    assert isinstance(transport, RequestsTransport)


def test_get_http_transport_direct_session_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    set_http_transport(None)
    monkeypatch.setenv("ACQUISITION_USE_TOR", "0")
    transport = get_http_transport()
    assert isinstance(transport, DirectSessionTransport)


def test_requests_transport_proxies_dict() -> None:
    transport = RequestsTransport()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"ok"
    mock_resp.headers = {}
    mock_resp.url = "https://example.test/"

    with patch("requests.get", return_value=mock_resp) as mock_get:
        transport.get(
            "https://example.test/",
            proxy_url="socks5h://tor1:9050",
            timeout_s=5.0,
            user_agent="test",
        )
        _, kwargs = mock_get.call_args
        assert kwargs["proxies"] == {
            "http": "socks5h://tor1:9050",
            "https": "socks5h://tor1:9050",
        }


class _EjusticeCaptchaTransport:
    """Toujours captcha — pour tester l'épuisement des lanes statuts."""

    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        return HttpResponse(
            status=200,
            body=b"<html>captcha</html>",
            headers={"content-type": "text/html"},
            timing_ms=1.0,
            final_url="https://www.ejustice.just.fgov.be/cgi_tsv/captchaform.html",
        )


def _statutes_job(number: str = "0123456789") -> FetchJob:
    return FetchJob(
        source="statutes",
        enterprise_number=number,
        doc_type="publications_index",
        url=f"https://www.ejustice.just.fgov.be/cgi_tsv/list.pl?language=fr&btw={number}",
    )


def test_scrape_statutes_direct_stops_on_captcha_without_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HDFS_LOCAL_ROOT", str(tmp_path / "hdfs-stub"))
    monkeypatch.setenv("HDFS_RAW_ROOT", "hdfs://localhost:9000/raw/v1")
    set_http_transport(_EjusticeCaptchaTransport())
    cfg = _cfg(tmp_path, kbo_direct_first=True, tor_proxies=())
    adapter = MagicMock()
    adapter.source = "statutes"
    adapter.build_urls.return_value = [_statutes_job()]

    report = _scrape_statutes_direct_passes(
        ["0123456789", "0999999999"],
        adapter=adapter,
        cfg=cfg,
    )
    assert report["stopped_early"] is True
    assert report["stop_reason"] == "CAPTCHA_SUSPECT"
    assert len(report["enterprises"]) == 1
    assert report["pending_not_processed"] == 1
    assert report["enterprises"][0]["reason"] == "CAPTCHA_SUSPECT"
