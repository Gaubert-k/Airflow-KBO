"""Sélection rescrape et transitions (sans suppression)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.lifecycle.config import LifecycleConfig, get_lifecycle_config
from packages.lifecycle.status import record_business_status_from_snapshot
from packages.persistence.enums import ProcessingState
from packages.persistence.models import EnterpriseProcessingState, RawDocument
from packages.persistence.repositories import transition_state


@dataclass
class LifecycleReport:
    due_selected: int
    queued: int
    statuses_updated: int


def select_due_enterprises(
    session: Session,
    *,
    limit: int = 50,
    config: LifecycleConfig | None = None,
) -> list[str]:
    """Entreprises dont le dernier scrape réussi est plus vieux que max_age_days."""
    cfg = config or get_lifecycle_config()
    cutoff = datetime.now(UTC) - timedelta(days=cfg.max_age_days)

    subq = (
        select(
            RawDocument.enterprise_number,
            func.max(RawDocument.scraped_at).label("last_scrape"),
        )
        .where(RawDocument.download_status == "SUCCESS")
        .group_by(RawDocument.enterprise_number)
        .subquery()
    )

    stmt = (
        select(subq.c.enterprise_number)
        .join(
            EnterpriseProcessingState,
            EnterpriseProcessingState.enterprise_number == subq.c.enterprise_number,
        )
        .where(
            subq.c.last_scrape < cutoff,
            EnterpriseProcessingState.state.in_(
                [
                    ProcessingState.STRUCTURED,
                    ProcessingState.FAILED_SCRAPE,
                    ProcessingState.FAILED_PARSE,
                ]
            ),
        )
        .order_by(subq.c.last_scrape)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def lifecycle_tick(
    session: Session,
    *,
    limit: int = 50,
    config: LifecycleConfig | None = None,
) -> LifecycleReport:
    """Remet en file les entreprises « dues » et met à jour le statut métier."""
    due = select_due_enterprises(session, limit=limit, config=config)
    queued = 0
    statuses = 0

    for number in due:
        row = session.get(EnterpriseProcessingState, number)
        if row is None:
            continue
        if row.state == ProcessingState.STRUCTURED:
            transition_state(
                session,
                number,
                ProcessingState.STRUCTURED,
                ProcessingState.QUEUED_SCRAPE,
            )
            queued += 1
        elif row.state in {ProcessingState.FAILED_SCRAPE, ProcessingState.FAILED_PARSE}:
            transition_state(
                session,
                number,
                row.state,
                ProcessingState.QUEUED_SCRAPE,
            )
            queued += 1
        if record_business_status_from_snapshot(session, number):
            statuses += 1

    return LifecycleReport(
        due_selected=len(due),
        queued=queued,
        statuses_updated=statuses,
    )
