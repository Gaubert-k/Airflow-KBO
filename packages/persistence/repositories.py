"""Repositories MS-05 — API publique gelée."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from packages.persistence.enums import ProcessingState, RawDocumentStatus, SeedSource
from packages.persistence.exceptions import EnterpriseNotFoundError, StateTransitionError
from packages.persistence.models import (
    Enterprise,
    EnterpriseDiscovery,
    EnterpriseProcessingState,
    EnterpriseSnapshot,
    RawDocument,
)
from packages.storage.models import RawDocumentStoredEvent
from packages.storage.paths import normalize_enterprise_number


def _utc_now() -> datetime:
    return datetime.now(UTC)


def upsert_enterprise(
    session: Session,
    enterprise_number: str,
    seed_source: SeedSource | str,
    *,
    initial_state: ProcessingState = ProcessingState.NEW,
) -> Enterprise:
    """Crée ou retourne l'entreprise ; initialise l'état si nouvelle."""
    number = normalize_enterprise_number(enterprise_number)
    source = SeedSource(seed_source) if isinstance(seed_source, str) else seed_source

    existing = session.get(Enterprise, number)
    if existing is not None:
        return existing

    enterprise = Enterprise(enterprise_number=number, seed_source=source)
    session.add(enterprise)
    session.flush()

    session.add(
        EnterpriseProcessingState(
            enterprise_number=number,
            state=initial_state,
            state_since=_utc_now(),
        )
    )
    session.flush()
    return enterprise


def transition_state(
    session: Session,
    enterprise_number: str,
    from_state: ProcessingState | str,
    to_state: ProcessingState | str,
    *,
    lock_owner: str | None = None,
    lock_until: datetime | None = None,
) -> EnterpriseProcessingState:
    """Transition avec verrouillage optimiste (colonne version)."""
    number = normalize_enterprise_number(enterprise_number)
    expected = ProcessingState(from_state) if isinstance(from_state, str) else from_state
    target = ProcessingState(to_state) if isinstance(to_state, str) else to_state

    row = session.execute(
        select(EnterpriseProcessingState)
        .where(EnterpriseProcessingState.enterprise_number == number)
        .with_for_update()
    ).scalar_one_or_none()

    if row is None:
        msg = f"No processing state for enterprise {number}"
        raise StateTransitionError(msg)
    if row.state != expected:
        msg = f"State mismatch for {number}: expected {expected.value}, got {row.state.value}"
        raise StateTransitionError(msg)

    now = _utc_now()
    result = session.execute(
        update(EnterpriseProcessingState)
        .where(
            EnterpriseProcessingState.enterprise_number == number,
            EnterpriseProcessingState.version == row.version,
            EnterpriseProcessingState.state == expected,
        )
        .values(
            state=target,
            state_since=now,
            updated_at=now,
            lock_owner=lock_owner,
            lock_until=lock_until,
            version=row.version + 1,
        )
    )
    if result.rowcount != 1:
        msg = f"Optimistic lock failed for {number}"
        raise StateTransitionError(msg)

    session.expire(row)
    session.refresh(row)
    return row


def claim_enterprises_for_parse(
    session: Session,
    *,
    limit: int = 10,
    worker_id: str,
    lock_seconds: int = 300,
) -> list[str]:
    """Pattern file : QUEUED_PARSE → PARSING."""
    from datetime import timedelta

    stmt = (
        select(EnterpriseProcessingState.enterprise_number)
        .where(EnterpriseProcessingState.state == ProcessingState.QUEUED_PARSE)
        .order_by(EnterpriseProcessingState.state_since)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    numbers = list(session.scalars(stmt))
    lock_until = _utc_now() + timedelta(seconds=lock_seconds)
    for number in numbers:
        transition_state(
            session,
            number,
            ProcessingState.QUEUED_PARSE,
            ProcessingState.PARSING,
            lock_owner=worker_id,
            lock_until=lock_until,
        )
    return numbers


def claim_enterprises_for_scrape(
    session: Session,
    *,
    limit: int = 10,
    worker_id: str,
    lock_seconds: int = 300,
    enterprise_numbers: list[str] | None = None,
) -> list[str]:
    """Pattern file d'attente : QUEUED_SCRAPE → SCRAPING (SKIP LOCKED PostgreSQL)."""
    from datetime import timedelta

    if enterprise_numbers:
        normalized = [normalize_enterprise_number(n) for n in enterprise_numbers]
        stmt = (
            select(EnterpriseProcessingState.enterprise_number)
            .where(
                EnterpriseProcessingState.enterprise_number.in_(normalized),
                EnterpriseProcessingState.state == ProcessingState.QUEUED_SCRAPE,
            )
            .order_by(EnterpriseProcessingState.state_since)
            .with_for_update(skip_locked=True)
        )
        numbers = list(session.scalars(stmt))
    else:
        stmt = (
            select(EnterpriseProcessingState.enterprise_number)
            .where(EnterpriseProcessingState.state == ProcessingState.QUEUED_SCRAPE)
            .order_by(EnterpriseProcessingState.state_since)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        numbers = list(session.scalars(stmt))
    lock_until = _utc_now() + timedelta(seconds=lock_seconds)
    for number in numbers:
        transition_state(
            session,
            number,
            ProcessingState.QUEUED_SCRAPE,
            ProcessingState.SCRAPING,
            lock_owner=worker_id,
            lock_until=lock_until,
        )
    return numbers


def _require_enterprise(session: Session, enterprise_number: str) -> Enterprise:
    number = normalize_enterprise_number(enterprise_number)
    enterprise = session.get(Enterprise, number)
    if enterprise is None:
        msg = f"Enterprise {number} not found — upsert via MS-01/MS-06 first"
        raise EnterpriseNotFoundError(msg)
    return enterprise


def fetch_success_raw_keys_for_source(
    session: Session,
    *,
    enterprise_numbers: Sequence[str],
    source: str,
    chunk_size: int = 2000,
) -> frozenset[tuple[str, str]]:
    """Paires (enterprise_number, doc_type) déjà en SUCCESS pour une source."""
    numbers = [normalize_enterprise_number(n) for n in enterprise_numbers]
    if not numbers:
        return frozenset()
    keys: set[tuple[str, str]] = set()
    for offset in range(0, len(numbers), chunk_size):
        chunk = numbers[offset : offset + chunk_size]
        rows = session.execute(
            select(RawDocument.enterprise_number, RawDocument.doc_type)
            .where(
                RawDocument.enterprise_number.in_(chunk),
                RawDocument.source == source,
                RawDocument.download_status == "SUCCESS",
            )
            .distinct()
        ).all()
        keys.update((row[0], row[1]) for row in rows)
    return frozenset(keys)


def insert_raw_document_record(
    session: Session,
    *,
    enterprise_number: str,
    source: str,
    doc_type: str,
    run_id: str,
    hdfs_dir: str,
    document_path: str,
    metadata_path: str,
    sha256: str,
    size_bytes: int,
    scraped_at: datetime,
    http_status: int,
    download_status: str,
    attempt_count: int = 1,
    status: RawDocumentStatus | str = RawDocumentStatus.STORED,
) -> RawDocument:
    """Enregistre un document brut (idempotent sur la clé MS-03)."""
    number = normalize_enterprise_number(enterprise_number)
    _require_enterprise(session, number)

    doc_status = (
        RawDocumentStatus(status) if isinstance(status, str) else status
    )

    existing = session.execute(
        select(RawDocument).where(
            RawDocument.enterprise_number == number,
            RawDocument.source == source,
            RawDocument.doc_type == doc_type,
            RawDocument.run_id == run_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    record = RawDocument(
        enterprise_number=number,
        source=source,
        doc_type=doc_type,
        run_id=run_id,
        hdfs_dir=hdfs_dir,
        document_path=document_path,
        metadata_path=metadata_path,
        sha256=sha256,
        size_bytes=size_bytes,
        scraped_at=scraped_at,
        http_status=http_status,
        download_status=download_status,
        attempt_count=attempt_count,
        status=doc_status,
    )
    session.add(record)
    session.flush()
    return record


def insert_raw_document_from_event(
    session: Session,
    event: RawDocumentStoredEvent,
    *,
    attempt_count: int = 1,
    status: RawDocumentStatus | str = RawDocumentStatus.STORED,
) -> RawDocument:
    return insert_raw_document_record(
        session,
        enterprise_number=event.enterprise_number,
        source=event.source,
        doc_type=event.doc_type,
        run_id=event.run_id,
        hdfs_dir=event.hdfs_dir,
        document_path=event.document_path,
        metadata_path=event.metadata_path,
        sha256=event.sha256,
        size_bytes=event.size_bytes,
        scraped_at=event.scraped_at,
        http_status=event.http_status,
        download_status=event.download_status,
        attempt_count=attempt_count,
        status=status,
    )


def append_snapshot(
    session: Session,
    enterprise_number: str,
    payload: dict[str, Any],
    *,
    schema_version: int = 1,
    snapshot_at: datetime | None = None,
) -> EnterpriseSnapshot:
    """Append-only — jamais de suppression métier."""
    number = normalize_enterprise_number(enterprise_number)
    _require_enterprise(session, number)

    snapshot = EnterpriseSnapshot(
        enterprise_number=number,
        payload=payload,
        schema_version=schema_version,
        snapshot_at=snapshot_at or _utc_now(),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def record_discovery(
    session: Session,
    *,
    source_enterprise_number: str,
    discovered_enterprise_number: str,
    reason: str,
    reason_code: str | None = None,
    discovered_at: datetime | None = None,
) -> EnterpriseDiscovery:
    """Provenance découverte (MS-06) + upsert entreprise DISCOVERED."""
    source = normalize_enterprise_number(source_enterprise_number)
    discovered = normalize_enterprise_number(discovered_enterprise_number)

    upsert_enterprise(session, discovered, SeedSource.DISCOVERED)

    existing = session.execute(
        select(EnterpriseDiscovery).where(
            EnterpriseDiscovery.source_enterprise_number == source,
            EnterpriseDiscovery.discovered_enterprise_number == discovered,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    discovery = EnterpriseDiscovery(
        source_enterprise_number=source,
        discovered_enterprise_number=discovered,
        reason=reason,
        reason_code=reason_code,
        discovered_at=discovered_at or _utc_now(),
    )
    session.add(discovery)
    session.flush()
    return discovery
