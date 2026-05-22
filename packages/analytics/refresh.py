"""Rafraîchissement tables analytiques depuis snapshots structurés."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from packages.i18n.nl_fr import translate_nl_to_fr
from packages.lifecycle.status import _kbo_fields_from_payload, _map_status_label
from packages.monitoring.events import emit_event
from packages.persistence.models import (
    AnalyticsActivityRank,
    AnalyticsPostalSummary,
    AnalyticsStateSummary,
    Base,
    EnterpriseSnapshot,
)
from packages.persistence.session import get_engine, session_scope


@dataclass
class RefreshReport:
    run_id: str
    postal_rows: int = 0
    state_rows: int = 0
    activity_rows: int = 0
    stale_flag: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


def _collect_from_snapshot(snap: EnterpriseSnapshot) -> tuple[str | None, list[tuple[str, str | None]]]:
    """Code postal et activités NACE (code, libellé) depuis un snapshot."""
    payload = snap.payload or {}
    postal: str | None = None
    activities: list[tuple[str, str | None]] = []

    detail = payload.get("enterprise_detail")
    if isinstance(detail, dict):
        if detail.get("postal_code"):
            postal = str(detail["postal_code"])
        for act in detail.get("vat_activities") or []:
            if isinstance(act, dict) and act.get("code"):
                code = str(act["code"]).strip()
                label = act.get("label")
                if isinstance(label, str):
                    label = translate_nl_to_fr(label) or label
                activities.append((code, label if isinstance(label, str) else None))
        return postal, activities

    for doc in payload.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        if doc.get("source") == "kbo" and doc.get("doc_type") == "profile":
            continue
        fields = doc.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        if not postal and fields.get("postal_code"):
            postal = str(fields["postal_code"])
        for act in fields.get("vat_activities") or []:
            if isinstance(act, dict) and act.get("code"):
                code = str(act["code"]).strip()
                label = act.get("label")
                if isinstance(label, str):
                    label = translate_nl_to_fr(label) or label
                activities.append((code, label if isinstance(label, str) else None))
    return postal, activities


def analytics_refresh(*, run_id: str | None = None) -> RefreshReport:
    """Produit les agrégats MS-08 (codes postaux, statuts KBO, activités NACE)."""
    rid = run_id or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    engine = get_engine()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    postal: dict[str, int] = {}
    activities: dict[str, tuple[str | None, int]] = {}
    status_counts: dict[str, set[str]] = {}
    stale = False

    with session_scope() as session:
        snapshots = list(session.scalars(select(EnterpriseSnapshot)))
        if not snapshots:
            stale = True

        for snap in snapshots:
            number = snap.enterprise_number
            kbo = _kbo_fields_from_payload(snap.payload or {})
            status = _map_status_label(
                kbo.get("status_label") if isinstance(kbo.get("status_label"), str) else None
            )
            status_counts.setdefault(status, set()).add(number)

            pc, acts = _collect_from_snapshot(snap)
            if pc:
                postal[pc] = postal.get(pc, 0) + 1
            for nace, label in acts:
                prev = activities.get(nace, (label, 0))
                activities[nace] = (label or prev[0], prev[1] + 1)

        session.execute(delete(AnalyticsPostalSummary))
        for pc, count in sorted(postal.items(), key=lambda x: (-x[1], x[0])):
            session.add(
                AnalyticsPostalSummary(
                    postal_code=pc,
                    enterprise_count=count,
                    refreshed_at=now,
                )
            )

        session.execute(delete(AnalyticsStateSummary))
        for status, numbers in sorted(
            status_counts.items(), key=lambda x: -len(x[1])
        ):
            session.add(
                AnalyticsStateSummary(
                    business_status=status,
                    enterprise_count=len(numbers),
                    refreshed_at=now,
                )
            )

        session.execute(delete(AnalyticsActivityRank))
        for nace, (label, count) in sorted(
            activities.items(), key=lambda x: x[1][1], reverse=True
        )[:100]:
            session.add(
                AnalyticsActivityRank(
                    nace_code=nace,
                    activity_label=label,
                    enterprise_count=count,
                    refreshed_at=now,
                )
            )

    total = len(snapshots)
    report = RefreshReport(
        run_id=rid,
        postal_rows=len(postal),
        state_rows=len(status_counts),
        activity_rows=len(activities),
        stale_flag=stale,
        metrics={
            "snapshot_count": total,
            "with_postal_code": sum(postal.values()),
            "with_nace_activity": sum(c for _, c in activities.values()),
            "status_breakdown": {k: len(v) for k, v in status_counts.items()},
        },
    )
    emit_event(
        "analytics_refresh",
        {
            "run_id": rid,
            "postal_rows": report.postal_rows,
            "activity_rows": report.activity_rows,
            "stale": stale,
            "snapshot_count": total,
        },
    )
    return report
