"""Parseur Moniteur belge (eJustice) — page recherche publications."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from packages.storage.paths import normalize_enterprise_number

_STRIP = re.compile(r"<[^>]+>")
_BTW_INPUT = re.compile(
    r'<input[^>]+name=["\']btw["\'][^>]+value=["\'](\d{10})["\']',
    re.IGNORECASE,
)
_RESULT_LINK = re.compile(r"rech_res\.pl|article\.pl|numac=", re.IGNORECASE)
_PUBLICATION_ROW = re.compile(
    r"<tr[^>]*>.*?</tr>",
    re.DOTALL | re.IGNORECASE,
)


def _clean(fragment: str) -> str:
    text = _STRIP.sub(" ", unescape(fragment))
    return re.sub(r"\s+", " ", text).strip()


def parse_moniteur_publication_search(
    html: bytes | str,
    *,
    enterprise_number: str,
    doc_type: str,
) -> tuple[dict[str, Any], list[str], bool]:
    """Extrait numéro BCE et indices de résultats depuis la page Moniteur."""
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    number = normalize_enterprise_number(enterprise_number)

    btw_match = _BTW_INPUT.search(text)
    if btw_match:
        try:
            number = normalize_enterprise_number(btw_match.group(1))
        except ValueError:
            pass

    result_links = len(_RESULT_LINK.findall(text))
    rows = [
        _clean(row)
        for row in _PUBLICATION_ROW.findall(text)
        if "numac" in row.lower() or "publication" in row.lower()
    ]
    publications_preview = [r[:240] for r in rows[:5] if len(r) > 20]

    fields: dict[str, Any] = {
        "enterprise_number": number,
        "source": "moniteur",
        "doc_type": doc_type,
        "search_form_present": "sampleform" in text or 'name="btw"' in text,
        "result_link_count": result_links,
        "publications_preview": publications_preview,
        "publication_count_hint": len(publications_preview),
    }
    partial = result_links == 0 and not publications_preview
    return fields, [], partial
