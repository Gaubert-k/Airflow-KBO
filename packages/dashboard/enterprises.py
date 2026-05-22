"""Liste entreprises + actions scrape/parse depuis le dashboard (MS-09)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.acquisition.worker import scrape_enterprise
from packages.extraction.worker import _parse_enterprise
from packages.extraction.config import get_extraction_config
from packages.persistence.bridge import wire_storage_events
from packages.persistence.enums import ProcessingState
from packages.persistence.exceptions import EnterpriseNotFoundError, StateTransitionError
from packages.persistence.models import (
    Base,
    Enterprise,
    EnterpriseProcessingState,
    EnterpriseSnapshot,
    RawDocument,
)
from packages.persistence.repositories import transition_state
from packages.persistence.session import get_engine, session_scope
from packages.dashboard.detail_view import (
    build_structured_summary,
    registry_summary_has_content,
)


class EnterpriseActionError(Exception):
    """Action dashboard refusée (état incompatible ou entreprise occupée)."""


_REQUEUE_SCRAPE: dict[ProcessingState, tuple[ProcessingState, ProcessingState] | None] = {
    ProcessingState.QUEUED_SCRAPE: None,
    ProcessingState.STRUCTURED: (
        ProcessingState.STRUCTURED,
        ProcessingState.QUEUED_SCRAPE,
    ),
    ProcessingState.FAILED_SCRAPE: (
        ProcessingState.FAILED_SCRAPE,
        ProcessingState.QUEUED_SCRAPE,
    ),
    ProcessingState.FAILED_PARSE: (
        ProcessingState.FAILED_PARSE,
        ProcessingState.QUEUED_SCRAPE,
    ),
    ProcessingState.NEW: (ProcessingState.NEW, ProcessingState.QUEUED_SCRAPE),
    ProcessingState.RAW_STORED: (
        ProcessingState.RAW_STORED,
        ProcessingState.QUEUED_SCRAPE,
    ),
    ProcessingState.QUEUED_PARSE: (
        ProcessingState.QUEUED_PARSE,
        ProcessingState.QUEUED_SCRAPE,
    ),
}

_REQUEUE_PARSE: dict[ProcessingState, tuple[ProcessingState, ProcessingState] | None] = {
    ProcessingState.QUEUED_PARSE: None,
    ProcessingState.STRUCTURED: (
        ProcessingState.STRUCTURED,
        ProcessingState.QUEUED_PARSE,
    ),
    ProcessingState.FAILED_PARSE: (
        ProcessingState.FAILED_PARSE,
        ProcessingState.QUEUED_PARSE,
    ),
    ProcessingState.RAW_STORED: (
        ProcessingState.RAW_STORED,
        ProcessingState.QUEUED_PARSE,
    ),
}

_BUSY = {ProcessingState.SCRAPING, ProcessingState.PARSING}


def _last_scrape_subq():
    return (
        select(
            RawDocument.enterprise_number.label("enterprise_number"),
            func.max(RawDocument.scraped_at).label("last_scrape_at"),
            func.count(RawDocument.id).label("raw_doc_count"),
        )
        .group_by(RawDocument.enterprise_number)
        .subquery()
    )


def _snapshot_count_subq():
    return (
        select(
            EnterpriseSnapshot.enterprise_number.label("enterprise_number"),
            func.count(EnterpriseSnapshot.id).label("snapshot_count"),
            func.max(EnterpriseSnapshot.snapshot_at).label("last_snapshot_at"),
        )
        .group_by(EnterpriseSnapshot.enterprise_number)
        .subquery()
    )


def get_enterprise_detail(enterprise_number: str) -> dict[str, Any]:
    """Fiche entreprise : état, documents bruts, dernier snapshot, découvertes."""
    from packages.persistence.models import EnterpriseDiscovery
    from packages.storage.paths import normalize_enterprise_number

    number = normalize_enterprise_number(enterprise_number)
    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        ent = session.get(Enterprise, number)
        if ent is None:
            raise EnterpriseNotFoundError(number)
        eps = session.get(EnterpriseProcessingState, number)
        raw_docs = list(
            session.scalars(
                select(RawDocument)
                .where(RawDocument.enterprise_number == number)
                .order_by(RawDocument.scraped_at.desc())
            )
        )
        snapshot = session.scalar(
            select(EnterpriseSnapshot)
            .where(EnterpriseSnapshot.enterprise_number == number)
            .order_by(EnterpriseSnapshot.snapshot_at.desc())
            .limit(1)
        )
        discoveries_from = list(
            session.scalars(
                select(EnterpriseDiscovery)
                .where(EnterpriseDiscovery.source_enterprise_number == number)
                .order_by(EnterpriseDiscovery.discovered_at.desc())
                .limit(20)
            )
        )
        discoveries_to = list(
            session.scalars(
                select(EnterpriseDiscovery)
                .where(EnterpriseDiscovery.discovered_enterprise_number == number)
                .order_by(EnterpriseDiscovery.discovered_at.desc())
                .limit(20)
            )
        )

    latest_snapshot = (
        {
            "snapshot_at": snapshot.snapshot_at.isoformat(),
            "schema_version": snapshot.schema_version,
            "payload": snapshot.payload,
        }
        if snapshot
        else None
    )

    raw_documents = [
        {
            "id": d.id,
            "source": d.source,
            "doc_type": d.doc_type,
            "run_id": d.run_id,
            "scraped_at": d.scraped_at.isoformat(),
            "hdfs_dir": d.hdfs_dir,
            "sha256": d.sha256,
            "size_bytes": d.size_bytes,
            "http_status": d.http_status,
            "download_status": d.download_status,
        }
        for d in raw_docs
    ]
    structured_summary = build_structured_summary(
        latest_snapshot=latest_snapshot,
        raw_documents=raw_documents,
    )
    proc_state = eps.state.value if eps and hasattr(eps.state, "value") else None
    success_raw_count = sum(
        1 for d in raw_documents if d.get("download_status") == "SUCCESS"
    )
    has_registry = registry_summary_has_content(structured_summary)
    registry_inconsistent = (
        proc_state == ProcessingState.STRUCTURED.value
        and not has_registry
        and success_raw_count > 0
    )
    needs_parse = bool(
        registry_inconsistent
        or (structured_summary or {}).get("pending_parse")
        or (
            proc_state
            in {
                ProcessingState.QUEUED_PARSE.value,
                ProcessingState.RAW_STORED.value,
            }
            and success_raw_count > 0
        )
    )

    return {
        "enterprise_number": number,
        "seed_source": ent.seed_source.value
        if hasattr(ent.seed_source, "value")
        else str(ent.seed_source),
        "created_at": ent.created_at.isoformat() if ent.created_at else None,
        "processing": {
            "state": proc_state,
            "state_since": eps.state_since.isoformat() if eps and eps.state_since else None,
            "lock_owner": eps.lock_owner if eps else None,
            "lock_until": eps.lock_until.isoformat() if eps and eps.lock_until else None,
            "version": eps.version if eps else None,
        },
        "raw_documents": raw_documents,
        "latest_snapshot": latest_snapshot,
        "structured_summary": structured_summary,
        "has_registry": has_registry,
        "needs_parse": needs_parse,
        "registry_inconsistent": registry_inconsistent,
        "discoveries_as_source": [
            {
                "discovered_enterprise_number": d.discovered_enterprise_number,
                "reason": d.reason,
                "reason_code": d.reason_code,
                "discovered_at": d.discovered_at.isoformat(),
            }
            for d in discoveries_from
        ],
        "discovered_from": [
            {
                "source_enterprise_number": d.source_enterprise_number,
                "reason": d.reason,
                "discovered_at": d.discovered_at.isoformat(),
            }
            for d in discoveries_to
        ],
    }


def list_enterprises(
    *,
    page: int = 1,
    page_size: int = 50,
    state: str | None = None,
    q: str | None = None,
    sort: str = "recent_scrape",
    light: bool = False,
) -> dict[str, Any]:
    """Page d'entreprises avec état, dernier scrape et registre structuré."""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size

    term = (q or "").strip()
    effective_state = (state or "").strip()
    if not effective_state and not term:
        effective_state = ProcessingState.STRUCTURED.value

    use_light = light or (
        effective_state == ProcessingState.QUEUED_SCRAPE.value and not term
    )

    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        filters = []
        st_enum: ProcessingState | None = None
        if effective_state:
            try:
                st_enum = ProcessingState(effective_state)
                filters.append(EnterpriseProcessingState.state == st_enum)
            except ValueError:
                effective_state = ProcessingState.STRUCTURED.value
                st_enum = ProcessingState.STRUCTURED
                filters.append(EnterpriseProcessingState.state == st_enum)

        if term:
            filters.append(Enterprise.enterprise_number.ilike(f"%{term}%"))

        count_q = (
            select(func.count())
            .select_from(Enterprise)
            .join(
                EnterpriseProcessingState,
                EnterpriseProcessingState.enterprise_number == Enterprise.enterprise_number,
            )
        )
        if filters:
            count_q = count_q.where(*filters)
        total = session.scalar(count_q) or 0

        if use_light:
            base = (
                select(
                    Enterprise.enterprise_number,
                    Enterprise.seed_source,
                    Enterprise.created_at,
                    EnterpriseProcessingState.state,
                    EnterpriseProcessingState.state_since,
                )
                .join(
                    EnterpriseProcessingState,
                    EnterpriseProcessingState.enterprise_number
                    == Enterprise.enterprise_number,
                )
            )
            if filters:
                base = base.where(*filters)
            if sort == "state_since":
                order = EnterpriseProcessingState.state_since.asc()
            else:
                order = Enterprise.enterprise_number.asc()
            rows = session.execute(
                base.order_by(order).offset(offset).limit(page_size)
            ).all()
            items = [
                {
                    "enterprise_number": r.enterprise_number,
                    "seed_source": r.seed_source.value
                    if hasattr(r.seed_source, "value")
                    else str(r.seed_source),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "state": r.state.value
                    if hasattr(r.state, "value")
                    else str(r.state),
                    "state_since": r.state_since.isoformat()
                    if r.state_since
                    else None,
                    "last_scrape_at": None,
                    "raw_doc_count": 0,
                    "snapshot_count": 0,
                    "last_snapshot_at": None,
                    "has_registry": False,
                }
                for r in rows
            ]
        else:
            last_scrape = _last_scrape_subq()
            snapshots = _snapshot_count_subq()
            base = (
                select(
                    Enterprise.enterprise_number,
                    Enterprise.seed_source,
                    Enterprise.created_at,
                    EnterpriseProcessingState.state,
                    EnterpriseProcessingState.state_since,
                    last_scrape.c.last_scrape_at,
                    last_scrape.c.raw_doc_count,
                    snapshots.c.snapshot_count,
                    snapshots.c.last_snapshot_at,
                )
                .join(
                    EnterpriseProcessingState,
                    EnterpriseProcessingState.enterprise_number
                    == Enterprise.enterprise_number,
                )
                .outerjoin(
                    last_scrape,
                    last_scrape.c.enterprise_number == Enterprise.enterprise_number,
                )
                .outerjoin(
                    snapshots,
                    snapshots.c.enterprise_number == Enterprise.enterprise_number,
                )
            )
            if filters:
                base = base.where(*filters)
            if sort == "state_since":
                order = EnterpriseProcessingState.state_since.desc().nullslast()
            elif sort == "number":
                order = Enterprise.enterprise_number.asc()
            else:
                order = last_scrape.c.last_scrape_at.desc().nullslast()
            rows = session.execute(
                base.order_by(order).offset(offset).limit(page_size)
            ).all()
            items = [
                {
                    "enterprise_number": r.enterprise_number,
                    "seed_source": r.seed_source.value
                    if hasattr(r.seed_source, "value")
                    else str(r.seed_source),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "state": r.state.value
                    if hasattr(r.state, "value")
                    else str(r.state),
                    "state_since": r.state_since.isoformat()
                    if r.state_since
                    else None,
                    "last_scrape_at": r.last_scrape_at.isoformat()
                    if r.last_scrape_at
                    else None,
                    "raw_doc_count": int(r.raw_doc_count or 0),
                    "snapshot_count": int(r.snapshot_count or 0),
                    "last_snapshot_at": r.last_snapshot_at.isoformat()
                    if r.last_snapshot_at
                    else None,
                    "has_registry": int(r.snapshot_count or 0) > 0,
                }
                for r in rows
            ]

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "items": items,
        "filter_state": effective_state or None,
        "filter_q": term or None,
        "default_filter_applied": not (state or "").strip() and not term,
        "light_mode": use_light,
    }


def _requeue(
    session: Session,
    number: str,
    matrix: dict[ProcessingState, tuple[ProcessingState, ProcessingState] | None],
) -> ProcessingState:
    row = session.get(EnterpriseProcessingState, number)
    if row is None:
        raise EnterpriseNotFoundError(number)
    current = row.state
    if current in _BUSY:
        msg = f"Entreprise {number} occupée ({current.value})"
        raise EnterpriseActionError(msg)
    step = matrix.get(current)
    if step is None and current not in matrix:
        msg = f"Refile impossible depuis l'état {current.value}"
        raise EnterpriseActionError(msg)
    if step is not None:
        transition_state(session, number, step[0], step[1])
        current = step[1]
    return current


def force_scrape_enterprise(
    enterprise_number: str,
    *,
    worker_id: str = "dashboard-force-scrape",
    wire_bridge: bool = True,
) -> dict[str, Any]:
    """Remet en file si besoin, scrape toutes les sources, enregistre le brut."""
    if wire_bridge:
        wire_storage_events()

    from packages.acquisition.proxy_pool import ProxyPool
    from packages.acquisition.config import get_acquisition_config

    cfg = get_acquisition_config()
    pool = ProxyPool.from_config(cfg)

    engine = get_engine()
    Base.metadata.create_all(engine)

    from packages.storage.paths import normalize_enterprise_number

    number = normalize_enterprise_number(enterprise_number)

    with session_scope() as session:
        if session.get(Enterprise, number) is None:
            raise EnterpriseNotFoundError(number)

        current = _requeue(session, number, _REQUEUE_SCRAPE)
        if current != ProcessingState.QUEUED_SCRAPE:
            msg = f"État inattendu après refile: {current.value}"
            raise EnterpriseActionError(msg)

        transition_state(
            session,
            number,
            ProcessingState.QUEUED_SCRAPE,
            ProcessingState.SCRAPING,
            lock_owner=worker_id,
        )
        session.commit()

        ok = scrape_enterprise(
            session,
            number,
            proxy_pool=pool,
            config=cfg,
            worker_id=worker_id,
        )
        session.commit()

        row = session.get(EnterpriseProcessingState, number)
        final_state = row.state.value if row else "unknown"

    return {
        "enterprise_number": number,
        "success": ok,
        "final_state": final_state,
        "message": "Scrape terminé — en file parse"
        if ok
        else "Scrape partiel ou échec — voir état FAILED_SCRAPE",
    }


def force_parse_enterprise(
    enterprise_number: str,
    *,
    worker_id: str = "dashboard-force-parse",
) -> dict[str, Any]:
    """Re-parse les documents bruts → snapshot registre (STRUCTURED)."""
    from packages.storage.paths import normalize_enterprise_number

    number = normalize_enterprise_number(enterprise_number)
    cfg = get_extraction_config()

    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        if session.get(Enterprise, number) is None:
            raise EnterpriseNotFoundError(number)

        current = _requeue(session, number, _REQUEUE_PARSE)
        if current != ProcessingState.QUEUED_PARSE:
            msg = (
                f"Parse impossible: pas de documents ou état {current.value}. "
                "Lancez d'abord un scrape."
            )
            raise EnterpriseActionError(msg)

        transition_state(
            session,
            number,
            ProcessingState.QUEUED_PARSE,
            ProcessingState.PARSING,
            lock_owner=worker_id,
        )
        session.commit()

        ok = _parse_enterprise(session, number, config=cfg, worker_id=worker_id)
        session.commit()

        row = session.get(EnterpriseProcessingState, number)
        final_state = row.state.value if row else "unknown"

    return {
        "enterprise_number": number,
        "success": ok,
        "final_state": final_state,
        "message": "Registre mis à jour (STRUCTURED)"
        if ok
        else "Échec parse — voir FAILED_PARSE",
    }
