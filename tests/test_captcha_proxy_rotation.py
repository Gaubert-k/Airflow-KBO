"""Tests captcha KBO + rotation proxy."""

from __future__ import annotations

from packages.acquisition.models import FetchResult, REASON_CAPTCHA_SUSPECT
from packages.acquisition.proxy_pool import ProxyEntry, ProxyPool
from packages.acquisition.validate import validate_fetch


def test_validate_captchaform_url() -> None:
    result = FetchResult(
        body=b"<html><title>Captcha</title></html>",
        http_status=200,
        url="https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html",
        final_url="https://kbopub.economie.fgov.be/kbopub/captchaform.html",
    )
    decision = validate_fetch(result)
    assert decision.reason_code == REASON_CAPTCHA_SUSPECT


def test_ban_proxy_label() -> None:
    pool = ProxyPool(
        entries=[
            ProxyEntry(host="1.2.3.4", port=8080),
            ProxyEntry(host="5.6.7.8", port=9090),
        ],
        allow_direct=False,
    )
    assert pool.healthy_count() == 2
    pool.ban_proxy_label("1.2.3.4:8080", reason="captcha")
    assert pool.healthy_count() == 1
    assert pool.pick() is not None
    assert pool.pick().label == "5.6.7.8:9090"
