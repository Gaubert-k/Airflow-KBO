"""Tests MS-10 — parse DAGs (DagBag) sans scrape réseau."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = REPO_ROOT / "airflow" / "dags"

PHASE_B_DAG_FILES = (
    "belgian_ingest_csv.py",
    "belgian_scrape_batch.py",
    "belgian_pipeline_dev.py",
)

EXPECTED_MS10_DAG_IDS = frozenset(
    {
        "01_ingest_csv",
        "02_scrape_batch",
        "02_scrape_by_source",
        "03_pipeline_dev",
        "04_extract_batch",
        "05_discovery_fanout",
        "06_lifecycle_refresh",
        "07_analytics_refresh",
        "08_full_pipeline",
        "09_platform_bootstrap",
    }
)

FORBIDDEN_PARSE_IMPORTS = frozenset(
    {
        "packages.ingestion",
        "packages.acquisition",
    }
)


def _top_level_import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("dag_file", PHASE_B_DAG_FILES)
def test_phase_b_dags_no_heavy_packages_at_parse_time(dag_file: str) -> None:
    modules = _top_level_import_modules(DAGS_DIR / dag_file)
    for forbidden in FORBIDDEN_PARSE_IMPORTS:
        assert not any(m == forbidden or m.startswith(forbidden + ".") for m in modules), (
            f"{dag_file} must not import {forbidden} at module level"
        )


@pytest.fixture(scope="module")
def dag_bag():
    airflow = pytest.importorskip("airflow")
    _ = airflow  # usage explicite pour éviter lint « unused »
    from airflow.dag_processing.dagbag import DagBag

    bag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False)
    return bag


def test_dagbag_no_import_errors(dag_bag) -> None:
    assert not dag_bag.import_errors, f"DAG import errors: {dag_bag.import_errors}"


def test_dagbag_contains_expected_ms10_dags(dag_bag) -> None:
    loaded = set(dag_bag.dag_ids)
    missing = EXPECTED_MS10_DAG_IDS - loaded
    assert not missing, f"Missing DAGs: {missing}; loaded={sorted(loaded)}"


def test_dagbag_hello_still_present(dag_bag) -> None:
    assert "00_hello" in dag_bag.dag_ids


def test_run_ingest_all_csv_skips_non_enterprise_files(tmp_path) -> None:
    from packages.orchestration.ingest_all import discover_enterprise_csv_files

    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "enterprise.csv").write_text(
        "EnterpriseNumber\n0203430576\n",
        encoding="utf-8",
    )
    (seed / "meta.csv").write_text('Variable,Value\n"SnapshotDate","today"\n', encoding="utf-8")
    (seed / "code.csv").write_text(
        '"Category","Code"\n"ActivityGroup","001"\n',
        encoding="utf-8",
    )

    found = discover_enterprise_csv_files([seed])
    assert len(found) == 1
    assert found[0].name == "enterprise.csv"


def test_run_ingest_all_csv_aggregates(tmp_path) -> None:
    from packages.orchestration import run_ingest_all_csv

    d = tmp_path / "csv"
    d.mkdir()
    (d / "a.csv").write_text("enterprise_number\n0123456789\n", encoding="utf-8")
    (d / "b.csv").write_text("enterprise_number\n0888888888\n", encoding="utf-8")

    summary = run_ingest_all_csv([str(d)], batch_size=100)
    assert summary["mode"] == "ingest_all"
    assert summary["files_processed"] == 2
    assert summary["created"] >= 0
    assert len(summary["files"]) == 2


def test_ingest_dag_does_not_call_scrape_at_parse_time() -> None:
    text = (DAGS_DIR / "belgian_ingest_csv.py").read_text(encoding="utf-8")
    assert "scrape_batch" not in text
    assert "run_scrape_batch" not in text


def test_phase_c_dags_have_phase_c_tag(dag_bag) -> None:
    for dag_id in (
        "04_extract_batch",
        "05_discovery_fanout",
        "06_lifecycle_refresh",
        "07_analytics_refresh",
        "08_full_pipeline",
    ):
        dag = dag_bag.dags[dag_id]
        assert "phase-c" in dag.tags


def test_statutes_parallel_forced_to_one() -> None:
    from packages.orchestration.scrape_parallel import effective_parallel_requests_per_site

    assert effective_parallel_requests_per_site("statutes", 5) == 1
    assert effective_parallel_requests_per_site("kbo", 5) == 5
    assert effective_parallel_requests_per_site("moniteur", 1) == 1


def test_statutes_skip_if_already_stored_policy() -> None:
    from packages.acquisition.scrape_policy import (
        graceful_stop_on_block,
        skip_if_already_stored,
        use_tor_escalation_on_error,
    )

    assert skip_if_already_stored("statutes") is True
    assert skip_if_already_stored("moniteur") is False
    assert use_tor_escalation_on_error("statutes") is False
    assert graceful_stop_on_block("statutes") is True
    assert graceful_stop_on_block("moniteur") is False


def test_statutes_skips_inter_request_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    from pathlib import Path

    from packages.acquisition.config import AcquisitionConfig
    from packages.acquisition.scrape_policy import skip_inter_request_delay

    assert skip_inter_request_delay("statutes") is True
    assert skip_inter_request_delay("kbo") is False

    fetch_module = importlib.import_module("packages.acquisition.fetch")
    polite_delay = fetch_module.polite_delay

    slept: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(fetch_module, "time", type("T", (), {"sleep": staticmethod(_fake_sleep)})())

    cfg = AcquisitionConfig(
        min_delay_s=1.0,
        max_delay_s=2.0,
        max_retries=1,
        use_proxies=False,
        proxy_file=Path("."),
        proxy_urls=(),
        allow_direct=True,
        use_tor=False,
        tor_proxies=(),
        kbo_direct_first=True,
        tor_loop=False,
        tor_loop_min_interval_s=600.0,
        tor_log_exit_ip=False,
        proxy_healthcheck=False,
        proxy_filter_at_start=False,
        proxy_probe_url="https://example.com/",
        proxy_probe_timeout_s=8.0,
        worker_id="test",
        http_timeout_s=30.0,
        user_agent="test",
    )

    polite_delay(cfg, source="statutes")
    assert slept == []

    polite_delay(cfg, source="kbo")
    assert len(slept) == 1
    assert 1.0 <= slept[0] <= 2.0


def test_parse_sources_param() -> None:
    from packages.orchestration.scrape_parallel import (
        DEFAULT_SCRAPE_SOURCES,
        parse_sources_param,
    )

    assert parse_sources_param(None) == list(DEFAULT_SCRAPE_SOURCES)
    assert parse_sources_param("kbo,bnb") == ["kbo", "bnb"]
    with pytest.raises(ValueError, match="inconnues"):
        parse_sources_param("kbo,unknown")


def test_scrape_by_source_dag_has_sources_param(dag_bag) -> None:
    dag = dag_bag.dags["02_scrape_by_source"]
    assert "sources" in dag.params
    assert "kbo_use_tor" in dag.params
    assert "tor_loop" in dag.params
    task_ids = {t.task_id for t in dag.tasks}
    assert task_ids == {
        "prepare_claim",
        "scrape_kbo",
        "scrape_moniteur",
        "scrape_statutes",
        "scrape_bnb",
        "finalize_scrape",
    }


def test_scrape_kbo_before_secondary_sources(dag_bag) -> None:
    dag = dag_bag.dags["02_scrape_by_source"]
    kbo = dag.get_task("scrape_kbo")
    prep = dag.get_task("prepare_claim")
    assert kbo in prep.downstream_list
    for task_id in ("scrape_moniteur", "scrape_statutes", "scrape_bnb"):
        assert dag.get_task(task_id) in kbo.downstream_list


def test_full_pipeline_kbo_first(dag_bag) -> None:
    dag = dag_bag.dags["08_full_pipeline"]
    kbo = dag.get_task("scrape_kbo")
    for task_id in ("scrape_moniteur", "scrape_statutes", "scrape_bnb"):
        assert dag.get_task(task_id) in kbo.downstream_list


def test_full_pipeline_uses_scrape_by_source_pattern(dag_bag) -> None:
    dag = dag_bag.dags["08_full_pipeline"]
    task_ids = {t.task_id for t in dag.tasks}
    assert "prepare_claim" in task_ids
    assert "scrape_kbo" in task_ids
    assert "finalize_scrape" in task_ids
    assert "extract" in task_ids
    assert "scrape" not in task_ids


def test_run_ingest_csv_returns_serializable_dict(tmp_path) -> None:
    from packages.orchestration import run_ingest_csv

    csv = tmp_path / "sample.csv"
    csv.write_text("enterprise_number\n0123456789\n", encoding="utf-8")
    summary = run_ingest_csv(str(csv), batch_size=100)
    assert isinstance(summary, dict)
    assert "rows_read" in summary
    assert "created" in summary
    assert isinstance(summary["source_file"], str)
