"""Point d'entrée parse(raw, metadata)."""

from __future__ import annotations

from typing import Any

from packages.extraction.config import ExtractionConfig, get_extraction_config
from packages.extraction.models import ParseResult, ParsedDocument
from packages.extraction.parsers.generic import parse_generic_html
from packages.extraction.parsers.kbo import parse_kbo_enterprise_detail
from packages.extraction.parsers.moniteur import parse_moniteur_publication_search


def parse_raw_document(
    content: bytes,
    metadata: dict[str, Any],
    *,
    config: ExtractionConfig | None = None,
) -> ParseResult:
    """Parse un document brut + sidecar metadata."""
    cfg = config or get_extraction_config()
    source = str(metadata.get("source", "unknown"))
    doc_type = str(metadata.get("doc_type", "unknown"))
    enterprise_number = str(metadata.get("enterprise_number") or metadata.get("ondernemingsnummer", ""))
    if not enterprise_number:
        return ParseResult(ok=False, reason_code="missing_enterprise_number")

    try:
        if source == "kbo" and doc_type in ("enterprise_detail", "profile"):
            fields, candidates, partial = parse_kbo_enterprise_detail(
                content,
                enterprise_number=enterprise_number,
                extractor_version=cfg.extractor_version,
                schema_version=cfg.schema_version,
            )
        elif source == "moniteur" and doc_type == "publication_search":
            fields, candidates, partial = parse_moniteur_publication_search(
                content,
                enterprise_number=enterprise_number,
                doc_type=doc_type,
            )
        else:
            fields, candidates, partial = parse_generic_html(
                content,
                enterprise_number=enterprise_number,
                source=source,
                doc_type=doc_type,
            )
    except Exception:
        return ParseResult(ok=False, reason_code="parse_exception")

    if not fields:
        return ParseResult(ok=False, reason_code="empty_fields")

    document = ParsedDocument(
        enterprise_number=fields.get("enterprise_number", enterprise_number),
        source=source,
        doc_type=doc_type,
        extractor_version=cfg.extractor_version,
        schema_version=cfg.schema_version,
        partial=partial,
        fields=fields,
        discovery_candidates=candidates,
    )
    return ParseResult(ok=True, reason_code="ok", document=document)
