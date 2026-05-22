"""Parseur générique — métadonnées minimales si pas de parseur dédié."""

from __future__ import annotations

import re
from typing import Any

from packages.storage.paths import normalize_enterprise_number

_TITLE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_SPA_MARKERS = ("<app-root", "ng-version", "data-ng-app")


def _page_title(text: str) -> str | None:
    match = _TITLE.search(text)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def _is_spa_shell(text: str) -> bool:
    lower = text[:8000].lower()
    return any(m in lower for m in _SPA_MARKERS)


def parse_generic_html(
    html: bytes | str,
    *,
    enterprise_number: str,
    source: str,
    doc_type: str,
) -> tuple[dict[str, Any], list[str], bool]:
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    number = normalize_enterprise_number(enterprise_number)
    size = len(text.encode("utf-8"))
    spa = _is_spa_shell(text)
    fields: dict[str, Any] = {
        "enterprise_number": number,
        "source": source,
        "doc_type": doc_type,
        "content_bytes": size,
        "page_title": _page_title(text),
        "parse_status": "spa_shell" if spa else "minimal",
    }
    partial = spa or source in ("bnb", "statutes")
    return fields, [], partial
