"""Tests vue structurée dashboard."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from packages.dashboard.detail_view import (
    build_structured_summary,
    registry_summary_has_content,
)
from packages.dashboard.enterprises import get_enterprise_detail
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import Base
from packages.persistence.repositories import (
    insert_raw_document_record,
    transition_state,
    upsert_enterprise,
)
from packages.persistence import session as persistence_session
from packages.persistence.session import reset_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def test_structured_summary_from_consolidated_payload() -> None:
    view = build_structured_summary(
        latest_snapshot={
            "snapshot_at": "2026-05-21T10:00:00+00:00",
            "schema_version": 1,
            "payload": {
                "parsed_at": "2026-05-21T10:00:00+00:00",
                "enterprise_detail": {
                    "legal_name": "Farys",
                    "status_label": "Actief",
                    "headquarters_address": "Drukpersstraat 4, 9000 Gent",
                    "postal_code": "9000",
                    "managers": [{"role": "Bestuurder", "name": "X"}],
                    "vat_activities": [{"code": "36.00", "label": "Water"}],
                    "registry_complete": True,
                },
                "documents": [],
            },
        }
    )
    assert view is not None
    assert view["has_data"] is True
    assert registry_summary_has_content(view)
    assert any(r["value"] == "Farys" for r in view["identity"])
    assert any(r["value"] == "Actif" for r in view["identity"])
    assert view["managers"][0]["role"] == "Administrateur"
    assert view["managers"][0]["name"] == "X"


def test_structured_summary_legacy_skips_kbo_profile_when_detail_present() -> None:
    view = build_structured_summary(
        latest_snapshot={
            "snapshot_at": "2026-05-21T10:00:00+00:00",
            "schema_version": 1,
            "payload": {
                "documents": [
                    {
                        "source": "kbo",
                        "doc_type": "profile",
                        "partial": False,
                        "fields": {"legal_name": "Profil"},
                    },
                    {
                        "source": "kbo",
                        "doc_type": "enterprise_detail",
                        "partial": False,
                        "fields": {"legal_name": "Vraie raison sociale"},
                    },
                ],
            },
        }
    )
    assert view is not None
    assert any(r["value"] == "Vraie raison sociale" for r in view["identity"])
    assert not any(r["value"] == "Profil" for r in view["identity"])


def test_structured_summary_pending_parse_without_snapshot() -> None:
    view = build_structured_summary(
        latest_snapshot=None,
        raw_documents=[
            {
                "source": "kbo",
                "doc_type": "enterprise_detail",
                "download_status": "SUCCESS",
            },
            {
                "source": "bnb",
                "doc_type": "consult_profile",
                "download_status": "SUCCESS",
            },
        ],
    )
    assert view is not None
    assert view["pending_parse"] is True
    assert view["raw_doc_count"] == 2
    assert not registry_summary_has_content(view)


def test_structured_summary_legacy_payload_with_raw_docs() -> None:
    view = build_structured_summary(
        latest_snapshot={
            "snapshot_at": "2026-05-21T10:00:00+00:00",
            "schema_version": 1,
            "payload": {"name": "Ancien format"},
        },
        raw_documents=[
            {
                "source": "kbo",
                "doc_type": "enterprise_detail",
                "download_status": "SUCCESS",
            },
        ],
    )
    assert view is not None
    assert view["pending_parse"] is True
    assert view["reason"] == "legacy_payload"


@pytest.fixture
def sqlite_detail_db(monkeypatch: pytest.MonkeyPatch):
    reset_engine()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    persistence_session._engine = engine
    persistence_session._session_factory = factory
    session = factory()
    upsert_enterprise(session, "0203430576", SeedSource.CSV)
    transition_state(
        session,
        "0203430576",
        ProcessingState.NEW,
        ProcessingState.STRUCTURED,
    )
    insert_raw_document_record(
        session,
        enterprise_number="0203430576",
        source="kbo",
        doc_type="enterprise_detail",
        run_id="run-1",
        hdfs_dir="hdfs://localhost/raw/kbo",
        document_path="document.html",
        metadata_path="metadata.json",
        sha256="a" * 64,
        size_bytes=100,
        scraped_at=datetime.now(UTC),
        http_status=200,
        download_status="SUCCESS",
    )
    session.commit()
    session.close()
    yield
    reset_engine()


def test_enterprise_detail_structured_without_snapshot_flags(
    sqlite_detail_db,
) -> None:
    detail = get_enterprise_detail("0203430576")
    assert detail["processing"]["state"] == "STRUCTURED"
    assert detail["latest_snapshot"] is None
    assert detail["structured_summary"]["pending_parse"] is True
    assert detail["has_registry"] is False
    assert detail["registry_inconsistent"] is True
    assert detail["needs_parse"] is True
    assert len(detail["raw_documents"]) == 1
