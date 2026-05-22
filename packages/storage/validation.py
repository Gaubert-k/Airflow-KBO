"""Validation à la frontière stockage (coordination MS-02 / MS-03)."""

from __future__ import annotations

import re
from typing import Any

from packages.storage.exceptions import InvalidRawContentError, MetadataValidationError

_REQUIRED_METADATA = frozenset(
    {
        "scraped_at",
        "source",
        "download_status",
        "http_status",
        "proxy_or_ip",
        "attempt_count",
        "last_updated_at",
    },
)

_ERROR_MARKERS = (
    re.compile(r"<title[^>]*>\s*404", re.I),
    re.compile(r"page\s+not\s+found", re.I),
    re.compile(r"erreur\s+404", re.I),
    re.compile(r"access\s+denied", re.I),
    re.compile(r"service\s+unavailable", re.I),
)

_MIN_HTML_BYTES = 64


def validate_metadata_sidecar(metadata: dict[str, Any], *, schema_version: int) -> dict[str, Any]:
    missing = _REQUIRED_METADATA - set(metadata.keys())
    if missing:
        msg = f"metadata.json missing required fields: {sorted(missing)}"
        raise MetadataValidationError(msg)
    enriched = dict(metadata)
    enriched.setdefault("schema_version", schema_version)
    return enriched


def reject_invalid_raw_content(
    content: bytes,
    *,
    metadata: dict[str, Any] | None = None,
    content_type: str | None = None,
) -> None:
    """
    Refuse de persister du contenu manifestement invalide.

    Règles alignées MS-02 : statut HTTP, download_status, marqueurs HTML d'erreur.
    """
    if not content:
        raise InvalidRawContentError("raw content is empty")

    meta = metadata or {}
    download_status = str(meta.get("download_status", "")).upper()
    if download_status and download_status != "SUCCESS":
        raise InvalidRawContentError(
            f"download_status is {download_status!r}, expected SUCCESS for storage"
        )

    http_status = meta.get("http_status")
    if http_status is not None:
        try:
            code = int(http_status)
        except (TypeError, ValueError) as exc:
            raise InvalidRawContentError(f"invalid http_status: {http_status!r}") from exc
        if code >= 400:
            raise InvalidRawContentError(f"http_status {code} indicates failure, not storable")

    is_html = (
        (content_type and "html" in content_type.lower())
        or content.lstrip()[:15].lower().startswith(b"<!doctype html")
        or content.lstrip()[:6].lower().startswith(b"<html")
    )
    if not is_html:
        return

    if len(content) < _MIN_HTML_BYTES:
        raise InvalidRawContentError("HTML payload too small to be a valid document")

    text = content.decode("utf-8", errors="replace")
    for pattern in _ERROR_MARKERS:
        if pattern.search(text):
            raise InvalidRawContentError(
                f"HTML matches error marker pattern: {pattern.pattern}"
            )
