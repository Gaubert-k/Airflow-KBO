"""Historique statuts métier (append-only, pas de DELETE)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.persistence.models import EnterpriseLifecycleHistory, EnterpriseSnapshot


def _map_status_label(label: str | None) -> str:
    if not label:
        return "UNKNOWN"
    low = label.lower()
    if "actief" in low or "actif" in low:
        return "ACTIVE"
    if "inactief" in low or "inactif" in low:
        return "INACTIVE"
    if "stop" in low or "radi" in low or "cess" in low:
        return "STRUCK_OFF"
    if "fus" in low or "merge" in low:
        return "MERGED"
    return "UNKNOWN"


def record_business_status_from_snapshot(session: Session, enterprise_number: str) -> bool:
    """Dérive le statut depuis le dernier snapshot KBO et l'append à l'historique."""
    snap = session.scalars(
        select(EnterpriseSnapshot)
        .where(EnterpriseSnapshot.enterprise_number == enterprise_number)
        .order_by(EnterpriseSnapshot.snapshot_at.desc())
        .limit(1)
    ).first()
    if snap is None:
        return False

    kbo_fields = _kbo_fields_from_payload(snap.payload)
    status_label = kbo_fields.get("status_label") if kbo_fields else None
    business_status = _map_status_label(status_label)
    payload: dict[str, Any] = {
        "status_label": status_label,
        "legal_form": kbo_fields.get("legal_form") if kbo_fields else None,
    }
    return append_business_status(session, enterprise_number, business_status, payload)


def _kbo_fields_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload.get("enterprise_detail")
    if isinstance(detail, dict) and detail.get("status_label") is not None:
        return detail
    has_detail = any(
        d.get("source") == "kbo" and d.get("doc_type") == "enterprise_detail"
        for d in payload.get("documents", [])
    )
    for doc in payload.get("documents", []):
        if doc.get("source") != "kbo":
            continue
        if has_detail and doc.get("doc_type") == "profile":
            continue
        fields = doc.get("fields") or {}
        if fields:
            return fields
    return detail if isinstance(detail, dict) else {}


def append_business_status(
    session: Session,
    enterprise_number: str,
    business_status: str,
    payload: dict[str, Any],
) -> bool:
    """Idempotent sur (enterprise, status, jour) — évite doublons journaliers."""
    today = datetime.now(UTC).date()
    existing = session.scalars(
        select(EnterpriseLifecycleHistory)
        .where(
            EnterpriseLifecycleHistory.enterprise_number == enterprise_number,
            EnterpriseLifecycleHistory.business_status == business_status,
        )
        .order_by(EnterpriseLifecycleHistory.recorded_at.desc())
        .limit(1)
    ).first()
    if existing and existing.recorded_at.date() == today:
        return False

    row = EnterpriseLifecycleHistory(
        enterprise_number=enterprise_number,
        business_status=business_status,
        payload=payload,
        recorded_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return True
