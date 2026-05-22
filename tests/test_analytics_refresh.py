"""Tests MS-08 — agrégats depuis snapshots."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from packages.analytics.refresh import analytics_refresh
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import (
    AnalyticsStateSummary,
    Base,
    Enterprise,
    EnterpriseProcessingState,
    EnterpriseSnapshot,
)
from packages.persistence.session import reset_engine


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch):
    reset_engine()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    @contextmanager
    def _scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("packages.persistence.session.get_engine", lambda: engine)
    monkeypatch.setattr("packages.analytics.refresh.get_engine", lambda: engine)
    monkeypatch.setattr("packages.analytics.refresh.session_scope", _scope)
    yield factory


def test_analytics_status_from_snapshots_not_unknown_bucket(isolated_db) -> None:
    session = isolated_db()
    num = "0123456789"
    session.add(Enterprise(enterprise_number=num, seed_source=SeedSource.CSV))
    session.add(
        EnterpriseProcessingState(
            enterprise_number=num,
            state=ProcessingState.STRUCTURED,
        )
    )
    session.add(
        EnterpriseSnapshot(
            enterprise_number=num,
            payload={
                "enterprise_detail": {
                    "status_label": "Actief",
                    "postal_code": "1000",
                    "vat_activities": [
                        {"code": "84114", "label": "Gemeentelijke overheid, met uitzondering van het OCMW"}
                    ],
                }
            },
        )
    )
    session.commit()

    report = analytics_refresh(run_id="test")
    assert report.postal_rows == 1
    assert report.state_rows == 1
    assert report.activity_rows == 1
    assert report.metrics["status_breakdown"].get("ACTIVE") == 1

    row = session.scalars(select(AnalyticsStateSummary)).first()
    assert row is not None
    assert row.business_status == "ACTIVE"
    assert row.enterprise_count == 1
    session.close()
