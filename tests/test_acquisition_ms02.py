"""Tests MS-02 — acquisition (réseau mocké)."""

from __future__ import annotations

from pathlib import Path

import pytest
from packages.acquisition.config import AcquisitionConfig
from packages.acquisition.fetch import fetch
from packages.acquisition.http_transport import HttpResponse, set_http_transport
from packages.acquisition.metrics import reset_metrics, snapshot
from packages.acquisition.models import ValidationAction
from packages.acquisition.proxy_pool import ProxyPool
from packages.acquisition.sources.bnb import BnbAdapter
from packages.acquisition.sources.kbo import KboAdapter, format_kbo_nummer
from packages.acquisition.sources.moniteur import MoniteurAdapter
from packages.acquisition.sources.registry import ALL_ADAPTERS, default_adapters, get_adapters
from packages.acquisition.sources.statutes import StatutesAdapter
from packages.acquisition.validate import validate_fetch
from packages.acquisition.worker import scrape_enterprise
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import Base, EnterpriseProcessingState
from packages.persistence.repositories import transition_state, upsert_enterprise
from packages.persistence.session import reset_engine
from packages.storage.config import StorageConfig
from packages.storage.raw_store import read_raw_bundle
from packages.storage.registry import clear_raw_document_listeners
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

_SAMPLE_HTML = (
    b"<!DOCTYPE html><html><head><title>Enterprise profile</title></head>"
    b"<body><p>KBO public search page with sufficient content for validation.</p></body></html>"
)


class FakeTransport:
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        proxy_url: str | None,
        timeout_s: float,
        user_agent: str,
    ) -> HttpResponse:
        self.calls.append(url)
        if url not in self.responses:
            msg = f"unexpected url: {url}"
            raise KeyError(msg)
        return self.responses[url]


@pytest.fixture
def acquisition_config(tmp_path: Path) -> AcquisitionConfig:
    return AcquisitionConfig(
        min_delay_s=0.0,
        max_delay_s=0.0,
        max_retries=2,
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
        worker_id="test-worker",
        http_timeout_s=5.0,
        user_agent="test-agent",
    )


@pytest.fixture
def storage_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StorageConfig:
    cfg = StorageConfig(
        hdfs_raw_root="hdfs://localhost:9000/raw/v1",
        hdfs_local_root=tmp_path / "hdfs-stub",
    )
    monkeypatch.setenv("HDFS_LOCAL_ROOT", str(cfg.hdfs_local_root))
    monkeypatch.setenv("HDFS_RAW_ROOT", cfg.hdfs_raw_root)
    return cfg


@pytest.fixture(autouse=True)
def _reset_transport_and_metrics() -> None:
    reset_metrics()
    set_http_transport(None)
    clear_raw_document_listeners()
    yield
    set_http_transport(None)
    clear_raw_document_listeners()
    reset_metrics()


@pytest.fixture
def db_session() -> Session:
    reset_engine()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        reset_engine()


def test_format_kbo_nummer() -> None:
    assert format_kbo_nummer("0203430576") == "0203.430.576"


def test_kbo_build_urls_default_single_detail() -> None:
    adapter = KboAdapter()
    jobs = adapter.build_urls("0203430576")
    assert len(jobs) == 1
    assert jobs[0].doc_type == "enterprise_detail"
    assert "toonondernemingps.html" in jobs[0].url
    assert "lang=fr" in jobs[0].url
    assert "ondernemingsnummer=0203430576" in jobs[0].url


def test_kbo_build_urls_with_profile_env(monkeypatch) -> None:
    monkeypatch.setenv("KBO_INCLUDE_PROFILE", "true")
    jobs = KboAdapter().build_urls("0203430576")
    assert len(jobs) == 2
    profile = next(j for j in jobs if j.doc_type == "profile")
    assert "lang=fr" in profile.url
    assert "nummer=0203.430.576" in profile.url


def test_bnb_moniteur_statutes_build_urls() -> None:
    bnb = BnbAdapter().build_urls("0203430576")
    assert len(bnb) == 1
    assert bnb[0].source == "bnb"
    assert "consult-enterprise/0203430576" in bnb[0].url

    mon = MoniteurAdapter().build_urls("0203430576")[0]
    assert mon.source == "moniteur"
    assert "rech.pl" in mon.url
    assert "language=fr" in mon.url
    assert "btw=0203430576" in mon.url

    stat = StatutesAdapter().build_urls("0203430576")[0]
    assert stat.source == "statutes"
    assert stat.doc_type == "publications_index"
    assert "list.pl" in stat.url
    assert "language=fr" in stat.url


def test_statutes_notaire_when_url_set(monkeypatch) -> None:
    monkeypatch.setenv(
        "NOTAIRE_STATUTES_URL",
        "https://www.notaire.be/entreprendre/demarrer-une-entreprise/"
        "comment-creer-une-societe-etapes-suivre/les-statuts-dune-societe",
    )
    stat = StatutesAdapter().build_urls("0203430576")[0]
    assert stat.doc_type == "statutes_notaire_info"
    assert "notaire.be" in stat.url


def test_kbo_page_with_field_placeholder_is_stored_not_error_marker() -> None:
    from packages.acquisition.models import FetchResult
    from packages.acquisition.validate import validate_fetch

    html = (
        b"<html><head><title>Gegevens van de geregistreerde entiteit</title></head>"
        b"<body><td>Geen gegevens opgenomen in KBO.</td></body></html>"
    )
    result = FetchResult(
        body=html,
        http_status=200,
        headers={"content-type": "text/html"},
        timing_ms=100,
        proxy_or_ip="direct",
        attempt_count=1,
        error=None,
    )
    decision = validate_fetch(result)
    assert decision.reason_code == "HTTP_2XX"


def test_default_adapters_includes_all_sources() -> None:
    assert len(default_adapters()) == len(ALL_ADAPTERS) == 4
    sources = {a.source for a in default_adapters()}
    assert sources == {"kbo", "moniteur", "statutes", "bnb"}


def test_get_adapters_subset() -> None:
    adapters = get_adapters(enabled_sources=("kbo", "bnb"))
    assert [a.source for a in adapters] == ["kbo", "bnb"]


def test_validate_fetch_store_and_drop() -> None:
    from packages.acquisition.models import FetchResult

    ok = FetchResult(
        body=_SAMPLE_HTML,
        http_status=200,
        headers={"content-type": "text/html"},
        timing_ms=10.0,
        proxy_or_ip="direct",
        attempt_count=1,
    )
    assert validate_fetch(ok).action == ValidationAction.STORE

    not_found = FetchResult(body=b"x", http_status=404, headers={}, attempt_count=1)
    assert validate_fetch(not_found).action == ValidationAction.DROP
    assert validate_fetch(not_found).reason_code == "HTTP_404"

    server_err = FetchResult(body=None, http_status=503, headers={}, attempt_count=1)
    assert validate_fetch(server_err).action == ValidationAction.RETRY


def test_fetch_with_mock_transport(acquisition_config: AcquisitionConfig) -> None:
    adapter = KboAdapter()
    job = adapter.build_urls("0123456789")[0]
    transport = FakeTransport(
        {job.url: HttpResponse(200, _SAMPLE_HTML, {"content-type": "text/html"}, 5.0)}
    )
    set_http_transport(transport)

    pool = ProxyPool(entries=[], allow_direct=True)
    result = fetch(job, pool, config=acquisition_config)
    assert result.http_status == 200
    assert result.body == _SAMPLE_HTML
    assert result.proxy_or_ip == "direct"


def test_scrape_enterprise_success(
    db_session: Session,
    acquisition_config: AcquisitionConfig,
    storage_setup: StorageConfig,
) -> None:
    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    transition_state(
        db_session,
        "0123456789",
        ProcessingState.NEW,
        ProcessingState.QUEUED_SCRAPE,
    )
    transition_state(
        db_session,
        "0123456789",
        ProcessingState.QUEUED_SCRAPE,
        ProcessingState.SCRAPING,
        lock_owner="test-worker",
    )
    db_session.commit()

    adapter = KboAdapter()
    kbo_jobs = adapter.build_urls("0123456789")
    set_http_transport(
        FakeTransport(
            {
                j.url: HttpResponse(200, _SAMPLE_HTML, {"content-type": "text/html"}, 1.0)
                for j in kbo_jobs
            }
        )
    )

    ok = scrape_enterprise(
        db_session,
        "0123456789",
        adapters=(adapter,),
        config=acquisition_config,
        proxy_pool=ProxyPool(entries=[], allow_direct=True),
    )
    db_session.commit()

    assert ok is True
    state = db_session.get(EnterpriseProcessingState, "0123456789")
    assert state is not None
    assert state.state == ProcessingState.QUEUED_PARSE

    local_root = storage_setup.hdfs_local_root
    kbo_dirs = list(
        (local_root / "raw" / "v1" / "source=kbo" / "enterprise_number=0123456789").glob(
            "doc_type=*/run_id=*"
        )
    )
    assert len(kbo_dirs) == 1
    detail_dir = next(p for p in kbo_dirs if "doc_type=enterprise_detail" in str(p))
    run_id = detail_dir.name.split("=", 1)[1]
    hdfs_dir = (
        f"hdfs://localhost:9000/raw/v1/source=kbo/enterprise_number=0123456789"
        f"/doc_type=enterprise_detail/run_id={run_id}"
    )
    content, meta = read_raw_bundle(hdfs_dir)
    assert content == _SAMPLE_HTML
    assert meta["download_status"] == "SUCCESS"
    assert meta["http_status"] == 200


def test_scrape_enterprise_http_404_fails(
    db_session: Session,
    acquisition_config: AcquisitionConfig,
) -> None:
    upsert_enterprise(db_session, "0888888888", SeedSource.CSV)
    transition_state(
        db_session,
        "0888888888",
        ProcessingState.NEW,
        ProcessingState.SCRAPING,
    )
    db_session.commit()

    kbo_jobs = KboAdapter().build_urls("0888888888")
    set_http_transport(
        FakeTransport({j.url: HttpResponse(404, b"not found", {}, 1.0) for j in kbo_jobs})
    )

    ok = scrape_enterprise(
        db_session,
        "0888888888",
        adapters=(KboAdapter(),),
        config=acquisition_config,
        proxy_pool=ProxyPool(entries=[], allow_direct=True),
    )
    db_session.commit()

    assert ok is False
    state = db_session.get(EnterpriseProcessingState, "0888888888")
    assert state is not None
    assert state.state == ProcessingState.FAILED_SCRAPE
    assert snapshot()["scrape_failures"]


def test_scrape_enterprise_all_sources_mocked(
    db_session: Session,
    acquisition_config: AcquisitionConfig,
    storage_setup: StorageConfig,
) -> None:
    """Scrape complet : 4 jobs (KBO detail + moniteur + statuts + BNB)."""
    upsert_enterprise(db_session, "0203430576", SeedSource.CSV)
    transition_state(
        db_session,
        "0203430576",
        ProcessingState.NEW,
        ProcessingState.SCRAPING,
    )
    db_session.commit()

    responses: dict[str, HttpResponse] = {}
    for adapter in default_adapters():
        for job in adapter.build_urls("0203430576"):
            responses[job.url] = HttpResponse(
                200,
                _SAMPLE_HTML,
                {"content-type": "text/html"},
                1.0,
            )
    set_http_transport(FakeTransport(responses))

    ok = scrape_enterprise(
        db_session,
        "0203430576",
        adapters=default_adapters(),
        config=acquisition_config,
        proxy_pool=ProxyPool(entries=[], allow_direct=True),
    )
    db_session.commit()

    assert ok is True
    assert len(responses) == 4
    state = db_session.get(EnterpriseProcessingState, "0203430576")
    assert state is not None
    assert state.state == ProcessingState.QUEUED_PARSE

    local_root = storage_setup.hdfs_local_root
    for source in ("kbo", "moniteur", "statutes", "bnb"):
        dirs = list((local_root / "raw" / "v1" / f"source={source}").glob("enterprise_number=*"))
        assert dirs, f"missing hdfs artifacts for source={source}"


def test_proxy_pool_parse_file(tmp_path: Path) -> None:
    proxy_file = tmp_path / "proxies.txt"
    proxy_file.write_text("1.2.3.4:8080\n# comment\nbad line\n5.6.7.8:3128\n", encoding="utf-8")
    cfg = AcquisitionConfig(
        min_delay_s=0,
        max_delay_s=0,
        max_retries=1,
        use_proxies=True,
        proxy_file=proxy_file,
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
        worker_id="w",
        http_timeout_s=5,
        user_agent="ua",
    )
    pool = ProxyPool.from_config(cfg)
    assert len(pool) == 2
    assert pool.pick() is not None


def test_fetch_success_raw_keys_for_source(db_session: Session) -> None:
    from datetime import UTC, datetime

    from packages.persistence.repositories import (
        fetch_success_raw_keys_for_source,
        insert_raw_document_record,
        upsert_enterprise,
    )

    upsert_enterprise(db_session, "0203430576", seed_source=SeedSource.CSV)
    upsert_enterprise(db_session, "0123456789", seed_source=SeedSource.CSV)
    now = datetime.now(UTC)
    insert_raw_document_record(
        db_session,
        enterprise_number="0203430576",
        source="statutes",
        doc_type="publications_index",
        run_id="run-a",
        hdfs_dir="/raw/a",
        document_path="/raw/a/doc.html",
        metadata_path="/raw/a/metadata.json",
        sha256="a" * 64,
        size_bytes=100,
        scraped_at=now,
        http_status=200,
        download_status="SUCCESS",
    )
    db_session.commit()

    keys = fetch_success_raw_keys_for_source(
        db_session,
        enterprise_numbers=["0203430576", "0123456789"],
        source="statutes",
    )
    assert keys == frozenset({("0203430576", "publications_index")})


def test_statutes_skips_http_when_already_stored(
    acquisition_config: AcquisitionConfig,
) -> None:
    from packages.acquisition.sources.statutes import StatutesAdapter
    from packages.acquisition.worker import _scrape_one_enterprise_for_source

    transport = FakeTransport({})
    set_http_transport(transport)

    outcome = _scrape_one_enterprise_for_source(
        "0203430576",
        adapter=StatutesAdapter(),
        source="statutes",
        proxy_pool=ProxyPool(entries=[], allow_direct=True),
        cfg=acquisition_config,
        existing_success=frozenset({("0203430576", "publications_index")}),
    )

    assert outcome["ok"] is True
    assert outcome["reason"] == "already_stored"
    assert transport.calls == []


def test_direct_session_transport_reuses_session() -> None:
    from packages.acquisition.http_transport import DirectSessionTransport, set_http_transport

    class _FakeResp:
        status_code = 200
        content = b"ok"
        headers: dict[str, str] = {}
        url = "https://example.test/page"

    calls = 0

    class _FakeSession:
        def get(self, url: str, **kwargs: object) -> _FakeResp:
            nonlocal calls
            calls += 1
            return _FakeResp()

    transport = DirectSessionTransport()
    transport._session = _FakeSession()  # type: ignore[assignment]
    set_http_transport(transport)

    transport.get(
        "https://example.test/one",
        proxy_url=None,
        timeout_s=5.0,
        user_agent="ua",
    )
    transport.get(
        "https://example.test/two",
        proxy_url=None,
        timeout_s=5.0,
        user_agent="ua",
    )
    assert calls == 2
