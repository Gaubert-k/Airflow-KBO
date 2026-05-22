"""Tests concurrence scrape par site."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from packages.orchestration.scrape_parallel import parse_parallel_requests_per_site


def test_parse_parallel_requests_defaults_and_clamp() -> None:
    assert parse_parallel_requests_per_site(None) == 1
    assert parse_parallel_requests_per_site(5) == 5
    assert parse_parallel_requests_per_site(100) == 32
    assert parse_parallel_requests_per_site("3") == 3


@patch("packages.acquisition.sources.registry.get_adapters")
@patch("packages.acquisition.worker.ProxyPool.from_config")
@patch("packages.acquisition.worker._process_job", return_value=(True, "ok"))
def test_scrape_source_uses_thread_pool_when_concurrency_gt_1(
    mock_process: MagicMock,
    mock_pool_cfg: MagicMock,
    mock_adapters: MagicMock,
) -> None:
    from packages.acquisition.worker import scrape_source_for_enterprises

    adapter = MagicMock()
    adapter.source = "bnb"
    adapter.build_urls.return_value = [MagicMock(url="http://example.test", source="bnb")]
    mock_adapters.return_value = (adapter,)
    mock_pool_cfg.return_value = MagicMock()

    numbers = [f"020000000{i}" for i in range(5)]
    report = scrape_source_for_enterprises(
        numbers,
        source="bnb",
        wire_persistence_bridge=False,
        parallel_requests_per_site=5,
    )

    assert report["parallel_requests_per_site"] == 5
    assert report["probed"] == 5
    assert mock_process.call_count == 5
