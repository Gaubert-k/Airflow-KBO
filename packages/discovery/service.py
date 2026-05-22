"""MS-06 — provenance + enqueue nouvelles entreprises."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import EnterpriseProcessingState, EnterpriseSnapshot
from packages.persistence.repositories import record_discovery, transition_state, upsert_enterprise
from packages.storage.paths import normalize_enterprise_number


@dataclass
class EnqueueDecision:
    enterprise_number: str
    created: bool
    queued: bool


def enqueue_if_new(session: Session, enterprise_number: str) -> EnqueueDecision:
    """Crée l'entreprise DISCOVERED et la met en file si elle n'était pas déjà en cours."""
    number = normalize_enterprise_number(enterprise_number)
    existing = session.get(EnterpriseProcessingState, number)
    created = existing is None

    enterprise = upsert_enterprise(session, number, SeedSource.DISCOVERED)
    state_row = session.get(EnterpriseProcessingState, enterprise.enterprise_number)
    if state_row is None:
        return EnqueueDecision(enterprise_number=number, created=True, queued=False)

    terminal_or_done = {
        ProcessingState.STRUCTURED,
        ProcessingState.QUEUED_SCRAPE,
        ProcessingState.SCRAPING,
        ProcessingState.QUEUED_PARSE,
        ProcessingState.PARSING,
        ProcessingState.RAW_STORED,
    }
    if state_row.state in terminal_or_done:
        return EnqueueDecision(enterprise_number=number, created=created, queued=False)

    if state_row.state in {ProcessingState.NEW, ProcessingState.FAILED_SCRAPE, ProcessingState.FAILED_PARSE}:
        transition_state(
            session,
            number,
            state_row.state,
            ProcessingState.QUEUED_SCRAPE,
        )
        return EnqueueDecision(enterprise_number=number, created=created, queued=True)

    return EnqueueDecision(enterprise_number=number, created=created, queued=False)


def apply_discovery_from_parse(
    session: Session,
    *,
    source_enterprise_number: str,
    candidates: list[str],
    reason_code: str = "ENTITY_LINK",
) -> list[EnqueueDecision]:
    """Enregistre provenance et enqueue les numéros découverts."""
    source = normalize_enterprise_number(source_enterprise_number)
    decisions: list[EnqueueDecision] = []
    seen: set[str] = set()

    for raw in candidates:
        try:
            discovered = normalize_enterprise_number(raw)
        except ValueError:
            continue
        if discovered == source or discovered in seen:
            continue
        seen.add(discovered)

        record_discovery(
            session,
            source_enterprise_number=source,
            discovered_enterprise_number=discovered,
            reason=f"Link from {source} parse",
            reason_code=reason_code,
        )
        decisions.append(enqueue_if_new(session, discovered))
    return decisions


def fanout_from_recent_snapshots(
    session: Session,
    *,
    hours: int = 48,
    limit: int = 50,
) -> dict[str, int]:
    """Scanne les snapshots récents pour liens non encore traités (DAG 05)."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = session.scalars(
        select(EnterpriseSnapshot)
        .where(EnterpriseSnapshot.snapshot_at >= since)
        .order_by(EnterpriseSnapshot.snapshot_at.desc())
        .limit(limit)
    )
    enqueued = 0
    recorded = 0
    for snap in rows:
        candidates: list[str] = []
        payload = snap.payload or {}
        detail = payload.get("enterprise_detail") or {}
        links = detail.get("entity_links") or []
        candidates.extend(links)
        for doc in payload.get("documents", []):
            if doc.get("source") == "kbo" and doc.get("doc_type") == "profile":
                continue
            links = doc.get("fields", {}).get("entity_links", [])
            candidates.extend(links)
        decisions = apply_discovery_from_parse(
            session,
            source_enterprise_number=snap.enterprise_number,
            candidates=candidates,
        )
        recorded += len(decisions)
        enqueued += sum(1 for d in decisions if d.queued)
    return {"snapshots_scanned": limit, "discoveries_recorded": recorded, "enqueued": enqueued}
