"""Tests MS-05 — repositories (SQLite en mémoire ; SKIP LOCKED ignoré)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.exceptions import EnterpriseNotFoundError, StateTransitionError
from packages.persistence.models import Base, EnterpriseSnapshot, RawDocument
from packages.persistence.repositories import (
    append_snapshot,
    insert_raw_document_record,
    record_discovery,
    transition_state,
    upsert_enterprise,
)
from packages.persistence.session import reset_engine
from packages.storage.models import RawDocumentStoredEvent
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


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


def test_upsert_enterprise_and_state(db_session: Session) -> None:
    ent = upsert_enterprise(db_session, "BE 0123.456.789", SeedSource.CSV)
    db_session.commit()

    assert ent.enterprise_number == "0123456789"
    assert ent.processing_state is not None
    assert ent.processing_state.state == ProcessingState.NEW


def test_transition_state_optimistic(db_session: Session) -> None:
    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    row = transition_state(
        db_session,
        "0123456789",
        ProcessingState.NEW,
        ProcessingState.QUEUED_SCRAPE,
    )
    db_session.commit()

    assert row.state == ProcessingState.QUEUED_SCRAPE
    assert row.version == 2

    with pytest.raises(StateTransitionError, match="State mismatch"):
        transition_state(
            db_session,
            "0123456789",
            ProcessingState.NEW,
            ProcessingState.SCRAPING,
        )


def test_raw_document_idempotent(db_session: Session) -> None:
    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    scraped = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    kwargs = dict(
        enterprise_number="0123456789",
        source="kbo",
        doc_type="profile",
        run_id="run-1",
        hdfs_dir="hdfs://localhost:9000/raw/v1/...",
        document_path="hdfs://.../document.html",
        metadata_path="hdfs://.../metadata.json",
        sha256="a" * 64,
        size_bytes=100,
        scraped_at=scraped,
        http_status=200,
        download_status="SUCCESS",
    )
    first = insert_raw_document_record(db_session, **kwargs)
    second = insert_raw_document_record(db_session, **kwargs)
    db_session.commit()

    assert first.id == second.id
    assert db_session.query(RawDocument).count() == 1


def test_raw_document_requires_enterprise(db_session: Session) -> None:
    with pytest.raises(EnterpriseNotFoundError):
        insert_raw_document_record(
            db_session,
            enterprise_number="0999999999",
            source="kbo",
            doc_type="profile",
            run_id="x",
            hdfs_dir="hdfs://x",
            document_path="hdfs://x/doc",
            metadata_path="hdfs://x/meta",
            sha256="b" * 64,
            size_bytes=1,
            scraped_at=datetime.now(UTC),
            http_status=200,
            download_status="SUCCESS",
        )


def test_append_snapshot_no_delete(db_session: Session) -> None:
    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    s1 = append_snapshot(db_session, "0123456789", {"name": "Acme", "status": "active"})
    s2 = append_snapshot(db_session, "0123456789", {"name": "Acme", "status": "closed"})
    db_session.commit()

    assert s1.id != s2.id
    assert db_session.query(EnterpriseSnapshot).count() == 2


def test_record_discovery(db_session: Session) -> None:
    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    disc = record_discovery(
        db_session,
        source_enterprise_number="0123456789",
        discovered_enterprise_number="0987654321",
        reason="mentioned_in_vat_section",
        reason_code="VAT_MENTION",
    )
    db_session.commit()

    assert disc.discovered_enterprise_number == "0987654321"
    from packages.persistence.models import Enterprise

    ent = db_session.get(Enterprise, "0987654321")
    assert ent is not None
    assert ent.seed_source == SeedSource.DISCOVERED


def test_insert_from_storage_event(db_session: Session) -> None:
    from packages.persistence.repositories import insert_raw_document_from_event

    upsert_enterprise(db_session, "0123456789", SeedSource.CSV)
    event = RawDocumentStoredEvent(
        enterprise_number="0123456789",
        source="kbo",
        doc_type="profile",
        run_id="evt",
        hdfs_dir="hdfs://dir",
        document_path="hdfs://dir/doc.html",
        metadata_path="hdfs://dir/metadata.json",
        sha256="c" * 64,
        size_bytes=50,
        scraped_at=datetime.now(UTC),
        http_status=200,
        download_status="SUCCESS",
    )
    doc = insert_raw_document_from_event(db_session, event)
    db_session.commit()
    assert doc.run_id == "evt"

