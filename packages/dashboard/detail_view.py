"""Vue structurée fiche entreprise pour le dashboard (à partir du snapshot ou legacy).

Langue d'affichage par défaut : français (valeurs NL normalisées via ``translate_snapshot_fields``).
"""

from __future__ import annotations

import json
from typing import Any

from packages.i18n.nl_fr import translate_snapshot_fields

_IDENTITY_FIELDS = (
    ("legal_name", "Dénomination"),
    ("status_label", "Statut"),
    ("legal_form", "Forme juridique"),
    ("enterprise_number", "Numéro BCE"),
    ("establishments_count", "Établissements"),
    ("financial_notes", "Assemblée / notes"),
)


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _success_raw_documents(
    raw_documents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [d for d in (raw_documents or []) if d.get("download_status") == "SUCCESS"]


def _pending_parse_summary(
    *,
    raw_documents: list[dict[str, Any]] | None,
    latest_snapshot: dict[str, Any] | None = None,
    reason: str = "no_snapshot",
) -> dict[str, Any]:
    success = _success_raw_documents(raw_documents)
    sources: list[dict[str, str]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for doc in success:
        key = (doc.get("source"), doc.get("doc_type"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "source": str(key[0] or ""),
                "doc_type": str(key[1] or ""),
                "label": f"{key[0]} / {key[1]}",
            }
        )
    out: dict[str, Any] = {
        "has_data": False,
        "pending_parse": True,
        "reason": reason,
        "raw_sources": sources,
        "raw_doc_count": len(success),
    }
    if latest_snapshot:
        out["snapshot_at"] = latest_snapshot.get("snapshot_at")
        out["schema_version"] = latest_snapshot.get("schema_version")
    return out


def registry_summary_has_content(summary: dict[str, Any] | None) -> bool:
    """True si le résumé peut afficher identité / siège (pas vide ni en attente de parse)."""
    if not summary:
        return False
    if summary.get("empty") or summary.get("pending_parse"):
        return False
    return bool(summary.get("has_data"))


def _identity_from_fields(fields: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, label in _IDENTITY_FIELDS:
        val = fields.get(key)
        if val is not None and str(val).strip():
            rows.append({"label": label, "value": str(val)})
    return rows


def _view_from_consolidated(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload.get("enterprise_detail") or {}
    if not isinstance(detail, dict):
        detail = {}
    detail = translate_snapshot_fields(detail)
    moniteur = detail.get("moniteur") or {}
    return {
        "has_data": bool(detail.get("legal_name") or detail.get("headquarters_address")),
        "registry_complete": detail.get("registry_complete", False),
        "parsed_at": payload.get("parsed_at"),
        "identity": _identity_from_fields(detail),
        "headquarters": {
            "address": detail.get("headquarters_address"),
            "postal_code": detail.get("postal_code"),
        },
        "managers": detail.get("managers") or [],
        "activities": detail.get("vat_activities") or [],
        "moniteur": {
            "partial": moniteur.get("partial", True),
            "result_link_count": moniteur.get("result_link_count"),
            "publications_preview": moniteur.get("publications_preview") or [],
        }
        if moniteur
        else None,
        "other_sources": detail.get("other_sources") or [],
        "raw_documents_parsed": payload.get("documents") or [],
    }


def _view_from_legacy_documents(payload: dict[str, Any]) -> dict[str, Any]:
    documents = payload.get("documents") or []
    kbo_fields: dict[str, Any] = {}
    moniteur_block: dict[str, Any] | None = None
    other: list[dict[str, Any]] = []

    has_detail = any(
        d.get("source") == "kbo" and d.get("doc_type") == "enterprise_detail"
        for d in documents
    )
    for doc in documents:
        source = doc.get("source")
        doc_type = doc.get("doc_type")
        fields = doc.get("fields") or {}
        partial = bool(doc.get("partial"))
        if source == "kbo":
            if doc_type == "profile" and has_detail:
                continue
            if doc_type in ("enterprise_detail", "profile") and not kbo_fields:
                kbo_fields = fields
            continue
        if source == "moniteur" and doc_type == "publication_search":
            moniteur_block = {
                "partial": partial,
                "result_link_count": fields.get("result_link_count"),
                "publications_preview": fields.get("publications_preview") or [],
            }
            continue
        if partial and fields.get("title_fragment"):
            summary = "Document partiel (aperçu HTML omis)"
        elif partial:
            summary = "Document partiel"
        else:
            summary = fields.get("page_title") or "Document parsé"
        other.append(
            {
                "source": source,
                "doc_type": doc_type,
                "label": f"{source} / {doc_type}",
                "partial": partial,
                "summary": summary,
            }
        )

    detail_proxy = translate_snapshot_fields(
        {**kbo_fields, "moniteur": moniteur_block, "other_sources": other}
    )
    view = _view_from_consolidated(
        {
            "parsed_at": payload.get("parsed_at"),
            "enterprise_detail": detail_proxy,
            "documents": documents,
        }
    )
    view["legacy_snapshot"] = True
    return view


def build_structured_summary(
    *,
    latest_snapshot: dict[str, Any] | None,
    raw_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Résumé pour le front : sections Identité, Siège, etc."""
    success_raw = _success_raw_documents(raw_documents)

    if not latest_snapshot:
        if success_raw:
            return _pending_parse_summary(
                raw_documents=raw_documents,
                reason="no_snapshot",
            )
        return None

    payload = _normalize_payload(latest_snapshot.get("payload"))
    if payload.get("enterprise_detail") is not None:
        view = _view_from_consolidated(payload)
    elif payload.get("documents"):
        view = _view_from_legacy_documents(payload)
    else:
        if success_raw:
            return _pending_parse_summary(
                raw_documents=raw_documents,
                latest_snapshot=latest_snapshot,
                reason="legacy_payload",
            )
        return {
            "has_data": False,
            "empty": True,
            "legacy_snapshot": True,
            "snapshot_at": latest_snapshot.get("snapshot_at"),
            "schema_version": latest_snapshot.get("schema_version"),
        }

    view["snapshot_at"] = latest_snapshot.get("snapshot_at")
    view["schema_version"] = latest_snapshot.get("schema_version")

    if not view.get("has_data") and success_raw:
        view["pending_parse"] = True
        view["reason"] = "incomplete_registry"
        view["raw_sources"] = _pending_parse_summary(
            raw_documents=raw_documents,
        )["raw_sources"]
        view["raw_doc_count"] = len(success_raw)

    return view
