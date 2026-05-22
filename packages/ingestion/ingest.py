"""Ingestion CSV → file PostgreSQL (MS-01)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from packages.ingestion.config import IngestionConfig, get_ingestion_config
from packages.ingestion.csv_stream import iter_enterprise_values, open_csv_stream
from packages.ingestion.quarantine import QuarantineWriter
from packages.ingestion.report import IngestReport
from packages.persistence.config import PersistenceConfig, get_persistence_config
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import Base, Enterprise, EnterpriseProcessingState
from packages.persistence.repositories import upsert_enterprise
from packages.persistence.session import get_engine, reset_engine, session_scope
from packages.storage.paths import normalize_enterprise_number


def _ensure_schema(config: PersistenceConfig) -> None:
    engine = get_engine(config)
    Base.metadata.create_all(engine)


def _upsert_batch(
    session: Session,
    numbers: list[str],
    *,
    created: int,
    already_existed: int,
    seen_in_file: set[str],
) -> tuple[int, int]:
    unique_new: list[str] = []
    for raw in numbers:
        number = normalize_enterprise_number(raw)
        if number in seen_in_file:
            already_existed += 1
            continue
        seen_in_file.add(number)
        unique_new.append(number)

    if not unique_new:
        return created, already_existed

    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        return _upsert_batch_postgresql(
            session,
            unique_new,
            created=created,
            already_existed=already_existed,
        )

    for number in unique_new:
        if session.get(Enterprise, number) is not None:
            already_existed += 1
            continue
        upsert_enterprise(
            session,
            number,
            SeedSource.CSV,
            initial_state=ProcessingState.QUEUED_SCRAPE,
        )
        created += 1

    return created, already_existed


def _upsert_batch_postgresql(
    session: Session,
    numbers: list[str],
    *,
    created: int,
    already_existed: int,
) -> tuple[int, int]:
    """INSERT par lot (ON CONFLICT DO NOTHING) — adapté aux gros CSV prof."""
    now = datetime.now(UTC)
    enterprise_rows = [
        {"enterprise_number": n, "seed_source": SeedSource.CSV.value}
        for n in numbers
    ]
    ent_stmt = (
        pg_insert(Enterprise)
        .values(enterprise_rows)
        .on_conflict_do_nothing(index_elements=["enterprise_number"])
        .returning(Enterprise.enterprise_number)
    )
    inserted = list(session.execute(ent_stmt).scalars().all())
    n_inserted = len(inserted)
    created += n_inserted
    already_existed += len(numbers) - n_inserted

    if inserted:
        state_rows = [
            {
                "enterprise_number": n,
                "state": ProcessingState.QUEUED_SCRAPE.value,
                "state_since": now,
                "updated_at": now,
                "version": 1,
            }
            for n in inserted
        ]
        state_stmt = (
            pg_insert(EnterpriseProcessingState)
            .values(state_rows)
            .on_conflict_do_nothing(index_elements=["enterprise_number"])
        )
        session.execute(state_stmt)

    return created, already_existed


def ingest_csv(
    path: str | Path,
    *,
    column: str | None = None,
    batch_size: int = 5000,
    persistence_config: PersistenceConfig | None = None,
    ingestion_config: IngestionConfig | None = None,
) -> IngestReport:
    """
    Ingère un CSV d'entreprises belges (flux, lots transactionnels).

    Les numéros invalides sont écrits sous ``data/quarantine/`` (ou
    ``INGESTION_QUARANTINE_DIR``).
    """
    if batch_size < 1:
        msg = f"batch_size must be >= 1, got {batch_size}"
        raise ValueError(msg)

    source = Path(path).resolve()
    if not source.is_file():
        msg = f"CSV file not found: {source}"
        raise FileNotFoundError(msg)

    pconfig = persistence_config or get_persistence_config()
    iconfig = ingestion_config or get_ingestion_config()
    _ensure_schema(pconfig)

    stream = open_csv_stream(source, column=column)
    quarantine = QuarantineWriter(iconfig.quarantine_dir, source.name)

    rows_read = 0
    created = 0
    already_existed = 0
    rejected = 0
    seen_in_file: set[str] = set()
    pending_valid: list[str] = []

    started = time.perf_counter()

    with session_scope(pconfig) as session:
        for line_no, raw_value in iter_enterprise_values(stream):
            rows_read += 1
            stripped = (raw_value or "").strip()
            if not stripped:
                rejected += 1
                quarantine.write(line_no, raw_value, "empty_value")
                continue

            try:
                normalize_enterprise_number(stripped)
            except ValueError as exc:
                rejected += 1
                quarantine.write(line_no, raw_value, str(exc))
                continue

            pending_valid.append(stripped)
            if len(pending_valid) >= batch_size:
                created, already_existed = _upsert_batch(
                    session,
                    pending_valid,
                    created=created,
                    already_existed=already_existed,
                    seen_in_file=seen_in_file,
                )
                session.commit()
                pending_valid.clear()

        if pending_valid:
            created, already_existed = _upsert_batch(
                session,
                pending_valid,
                created=created,
                already_existed=already_existed,
                seen_in_file=seen_in_file,
            )
            session.commit()

    quarantine.close()
    duration = time.perf_counter() - started

    return IngestReport(
        rows_read=rows_read,
        created=created,
        already_existed=already_existed,
        rejected=rejected,
        quarantine_path=quarantine.path,
        source_file=source,
        duration_seconds=duration,
    )


def reset_persistence_for_tests() -> None:
    """Réinitialise le singleton engine (tests uniquement)."""
    reset_engine()
