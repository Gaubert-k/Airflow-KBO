"""SDK métriques MS-09 — mémoire + table pipeline_events."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from sqlalchemy import func, select

from packages.acquisition.metrics import snapshot as acquisition_snapshot
from packages.persistence.enums import ProcessingState
from packages.persistence.models import (
    AnalyticsActivityRank,
    AnalyticsPostalSummary,
    AnalyticsStateSummary,
    Base,
    EnterpriseDiscovery,
    EnterpriseProcessingState,
    PipelineEvent,
)
from packages.persistence.session import get_engine, session_scope

_lock = Lock()
_parse_success = 0
_parse_failures: Counter[str] = Counter()


def record_parse_success() -> None:
    with _lock:
        global _parse_success
        _parse_success += 1


def record_parse_failure(reason: str) -> None:
    with _lock:
        _parse_failures[reason] += 1


def emit_event(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Persiste un événement append-only (best-effort)."""
    data = payload or {}
    try:
        engine = get_engine()
        Base.metadata.create_all(engine)
        with session_scope() as session:
            session.add(
                PipelineEvent(
                    event_type=event_type,
                    payload=data,
                    created_at=datetime.now(UTC),
                )
            )
    except Exception:
        pass


def _queue_depths(session) -> dict[str, int]:
    rows = session.execute(
        select(EnterpriseProcessingState.state, func.count())
        .group_by(EnterpriseProcessingState.state)
    )
    return {state.value if hasattr(state, "value") else str(state): count for state, count in rows}


def _performance_summary(acq: dict[str, dict[str, int]], parse_stats: dict) -> dict[str, Any]:
    attempts = sum(acq.get("scrape_attempts", {}).values())
    successes = sum(acq.get("scrape_success", {}).values())
    failures = sum(acq.get("scrape_failures", {}).values())
    proxy_failures = sum(acq.get("proxy_failures", {}).values())
    parse_ok = parse_stats.get("success", 0)
    parse_fail = sum(parse_stats.get("failures", {}).values())
    scrape_rate = round(100.0 * successes / attempts, 1) if attempts else None
    parse_total = parse_ok + parse_fail
    parse_rate = round(100.0 * parse_ok / parse_total, 1) if parse_total else None
    return {
        "scrape_attempts": attempts,
        "scrape_successes": successes,
        "scrape_failures": failures,
        "scrape_success_rate_pct": scrape_rate,
        "proxy_failures": proxy_failures,
        "parse_successes": parse_ok,
        "parse_failures": parse_fail,
        "parse_success_rate_pct": parse_rate,
    }


def get_analytics_snapshot(*, postal_limit: int = 15, activity_limit: int = 12) -> dict[str, Any]:
    """Agrégats MS-08 pour le dashboard (libellés FR, pourcentages)."""
    from packages.analytics.labels import business_status_label, format_nace_code
    from packages.i18n.nl_fr import translate_nl_to_fr

    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        postal_rows = list(
            session.execute(
                select(AnalyticsPostalSummary)
                .order_by(AnalyticsPostalSummary.enterprise_count.desc())
                .limit(postal_limit)
            ).scalars()
        )
        state_rows = list(
            session.execute(
                select(AnalyticsStateSummary).order_by(
                    AnalyticsStateSummary.enterprise_count.desc()
                )
            ).scalars()
        )
        activity_rows = list(
            session.execute(
                select(AnalyticsActivityRank)
                .order_by(AnalyticsActivityRank.enterprise_count.desc())
                .limit(activity_limit)
            ).scalars()
        )

    refreshed_at = None
    for block in (postal_rows, state_rows, activity_rows):
        if block:
            refreshed_at = block[0].refreshed_at.isoformat()
            break

    total_enterprises = sum(r.enterprise_count for r in state_rows)
    if total_enterprises <= 0:
        total_enterprises = sum(r.enterprise_count for r in postal_rows)

    def pct(n: int) -> float | None:
        if total_enterprises <= 0:
            return None
        return round(100.0 * n / total_enterprises, 1)

    postal = [
        {
            "postal_code": r.postal_code,
            "enterprise_count": r.enterprise_count,
            "share_pct": pct(r.enterprise_count),
        }
        for r in postal_rows
    ]
    states = [
        {
            "business_status": r.business_status,
            "status_label_fr": business_status_label(r.business_status),
            "enterprise_count": r.enterprise_count,
            "share_pct": pct(r.enterprise_count),
        }
        for r in state_rows
    ]
    activities = []
    for r in activity_rows:
        label = r.activity_label
        if isinstance(label, str):
            label = translate_nl_to_fr(label) or label
        activities.append(
            {
                "nace_code": r.nace_code,
                "nace_display": format_nace_code(r.nace_code),
                "activity_label": label,
                "enterprise_count": r.enterprise_count,
                "share_pct": pct(r.enterprise_count),
            }
        )

    return {
        "refreshed_at": refreshed_at,
        "total_enterprises": total_enterprises,
        "postal": postal,
        "states": states,
        "activities": activities,
        "empty": not postal and not states and not activities,
        "help": (
            "Données issues des snapshots structurés (après extraction). "
            "Statuts dérivés du libellé KBO. Relancer le DAG 07_analytics_refresh après de nouveaux lots."
        ),
    }


def get_recent_pipeline_events(*, limit: int = 30) -> list[dict[str, Any]]:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        rows = session.scalars(
            select(PipelineEvent)
            .order_by(PipelineEvent.created_at.desc())
            .limit(limit)
        ).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "payload": row.payload,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def get_recent_discoveries(*, limit: int = 15) -> list[dict[str, Any]]:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        rows = session.scalars(
            select(EnterpriseDiscovery)
            .order_by(EnterpriseDiscovery.discovered_at.desc())
            .limit(limit)
        ).all()
    return [
        {
            "source_enterprise_number": row.source_enterprise_number,
            "discovered_enterprise_number": row.discovered_enterprise_number,
            "reason": row.reason,
            "reason_code": row.reason_code,
            "discovered_at": row.discovered_at.isoformat(),
        }
        for row in rows
    ]


def get_supervision_snapshot() -> dict[str, Any]:
    """Vue agrégée pour le dashboard MS-09."""
    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        queue = _queue_depths(session)
        discovered_total = session.scalar(
            select(func.count()).select_from(EnterpriseDiscovery)
        ) or 0
        in_flight = (
            queue.get(ProcessingState.SCRAPING.value, 0)
            + queue.get(ProcessingState.PARSING.value, 0)
        )
        pending = (
            queue.get(ProcessingState.QUEUED_SCRAPE.value, 0)
            + queue.get(ProcessingState.QUEUED_PARSE.value, 0)
            + queue.get(ProcessingState.NEW.value, 0)
        )
        structured = queue.get(ProcessingState.STRUCTURED.value, 0)
        scrape_errors = queue.get(ProcessingState.FAILED_SCRAPE.value, 0)
        parse_errors = queue.get(ProcessingState.FAILED_PARSE.value, 0)

    with _lock:
        parse_stats = {
            "success": _parse_success,
            "failures": dict(_parse_failures),
        }

    acq = acquisition_snapshot()
    with session_scope() as session:
        recent_discoveries_rows = session.scalars(
            select(EnterpriseDiscovery)
            .order_by(EnterpriseDiscovery.discovered_at.desc())
            .limit(10)
        ).all()
        recent_events_rows = session.scalars(
            select(PipelineEvent)
            .order_by(PipelineEvent.created_at.desc())
            .limit(20)
        ).all()
    recent_discoveries = [
        {
            "source_enterprise_number": row.source_enterprise_number,
            "discovered_enterprise_number": row.discovered_enterprise_number,
            "reason": row.reason,
            "reason_code": row.reason_code,
            "discovered_at": row.discovered_at.isoformat(),
        }
        for row in recent_discoveries_rows
    ]
    recent_events = [
        {
            "id": row.id,
            "event_type": row.event_type,
            "payload": row.payload,
            "created_at": row.created_at.isoformat(),
        }
        for row in recent_events_rows
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "queue_by_state": queue,
        "in_flight": in_flight,
        "pending": pending,
        "fully_structured": structured,
        "discovered_total": discovered_total,
        "scrape_errors": scrape_errors,
        "parse_errors": parse_errors,
        "validation_errors": queue.get(ProcessingState.FAILED_VALIDATE.value, 0),
        "acquisition_metrics": acq,
        "parse_metrics": parse_stats,
        "performance": _performance_summary(acq, parse_stats),
        "recent_discoveries": recent_discoveries,
        "recent_events": recent_events,
    }
