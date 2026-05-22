"""Fusion des documents parsés en un registre ``enterprise_detail`` lisible."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from packages.i18n.nl_fr import translate_snapshot_fields

_KBO_PRIMARY = "enterprise_detail"
_KBO_SKIP = "profile"
_IDENTITY_KEYS = (
    "enterprise_number",
    "legal_name",
    "status_label",
    "legal_form",
    "headquarters_address",
    "postal_code",
    "managers",
    "vat_activities",
    "financial_notes",
    "establishments_count",
    "entity_links",
)


def _pick_kbo_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    kbo = [d for d in documents if d.get("source") == "kbo"]
    if not kbo:
        return None
    for preferred in (_KBO_PRIMARY,):
        for doc in kbo:
            if doc.get("doc_type") == preferred:
                return doc
    for doc in kbo:
        if doc.get("doc_type") != _KBO_SKIP:
            return doc
    return kbo[0]


def _auxiliary_label(source: str, doc_type: str) -> str:
    labels = {
        ("bnb", "consult_profile"): "BNB — Centrale des bilans",
        ("statutes", "publications_index"): "Statuts — Moniteur (index)",
        ("statutes", "statutes_notaire_info"): "Statuts — notaire.be",
        ("moniteur", "publication_search"): "Moniteur belge",
    }
    return labels.get((source, doc_type), f"{source} / {doc_type}")


def _auxiliary_summary(fields: dict[str, Any], *, partial: bool) -> str:
    if fields.get("parse_status") == "spa_shell":
        title = fields.get("page_title") or "Application web"
        return f"{title} — contenu chargé côté navigateur (extraction limitée)"
    if partial:
        return "Document partiel ou sans données structurées exploitables"
    if fields.get("result_link_count") is not None:
        n = fields.get("result_link_count", 0)
        return f"{n} lien(s) de publication détecté(s)"
    return "Document enregistré"


def consolidate_parsed_documents(
    enterprise_number: str,
    parsed_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Produit un payload snapshot avec ``enterprise_detail`` consolidé.

    ``documents`` conserve la trace parse (analytics, sources brutes repliables).
    """
    detail: dict[str, Any] = {"enterprise_number": enterprise_number}
    other_sources: list[dict[str, Any]] = []

    kbo_doc = _pick_kbo_document(parsed_documents)
    if kbo_doc:
        fields = translate_snapshot_fields(dict(kbo_doc.get("fields") or {}))
        for key in _IDENTITY_KEYS:
            if fields.get(key) is not None:
                detail[key] = fields[key]

    moniteur_docs = [
        d
        for d in parsed_documents
        if d.get("source") == "moniteur" and d.get("doc_type") == "publication_search"
    ]
    if moniteur_docs:
        mf = dict(moniteur_docs[0].get("fields") or {})
        detail["moniteur"] = {
            "result_link_count": mf.get("result_link_count"),
            "publication_count_hint": mf.get("publication_count_hint"),
            "publications_preview": mf.get("publications_preview") or [],
            "partial": moniteur_docs[0].get("partial", False),
        }

    skip_keys = {
        ("kbo", _KBO_SKIP),
        ("kbo", _KBO_PRIMARY),
        ("moniteur", "publication_search"),
    }
    for doc in parsed_documents:
        key = (doc.get("source"), doc.get("doc_type"))
        if key in skip_keys:
            continue
        if doc.get("source") == "kbo":
            continue
        fields = doc.get("fields") or {}
        partial = bool(doc.get("partial"))
        other_sources.append(
            {
                "source": doc.get("source"),
                "doc_type": doc.get("doc_type"),
                "label": _auxiliary_label(doc.get("source", ""), doc.get("doc_type", "")),
                "partial": partial,
                "summary": _auxiliary_summary(fields, partial=partial),
                "page_title": fields.get("page_title"),
                "content_bytes": fields.get("content_bytes"),
            }
        )

    if other_sources:
        detail["other_sources"] = other_sources

    any_partial = any(d.get("partial") for d in parsed_documents)
    kbo_partial = bool(kbo_doc and kbo_doc.get("partial"))
    detail["registry_complete"] = bool(detail.get("legal_name")) and not kbo_partial

    return {
        "parsed_at": datetime.now(UTC).isoformat(),
        "enterprise_number": enterprise_number,
        "enterprise_detail": detail,
        "documents": parsed_documents,
        "consolidation": {
            "kbo_doc_type": kbo_doc.get("doc_type") if kbo_doc else None,
            "document_count": len(parsed_documents),
            "any_partial": any_partial,
        },
    }
