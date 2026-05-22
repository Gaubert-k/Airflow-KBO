"""Parseur KBO — fiche publique enterprise_detail."""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from packages.i18n.nl_fr import translate_snapshot_fields
from packages.storage.paths import normalize_enterprise_number

_ENTERPRISE_IN_URL = re.compile(
    r"(?:ondernemingsnummer|btw|enterprise)[=:](\d{10})",
    re.IGNORECASE,
)
_DIGITS_10 = re.compile(r"\b(\d{10})\b")
_TAG_TEXT = re.compile(r"<td[^>]*class=\"[QR]L\"[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
_STRIP = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    text = _STRIP.sub(" ", unescape(fragment))
    return re.sub(r"\s+", " ", text).strip()


def _field_after_label(html: str, label: str) -> str | None:
    pattern = (
        rf"<td[^>]*class=\"[QR]L\"[^>]*>\s*{re.escape(label)}\s*:?\s*</td>\s*"
        r"<td[^>]*class=\"[QR]L\"[^>]*colspan=\"3\"[^>]*>(.*?)</td>"
    )
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return _clean(match.group(1)) or None


def _extract_managers(html: str) -> list[dict[str, str]]:
    managers: list[dict[str, str]] = []
    role_pattern = (
        r"Bestuurder|Administrateur|Gérant|Zaakvoerder|Voorzitter|Commissaris|"
        r"Burgemeester|Persoon belast met dagelijks bestuur|"
        r"Personne chargée de la gestion journalière|Bourgmestre|"
        r"Personne chargée du gérant|Gérant statutaire"
    )
    for role, name in re.findall(
        rf"<td class=\"[QR]L\"[^>]*>\s*({role_pattern})[^<]*</td>\s*"
        r"<td class=\"[QR]L\"[^>]*>\s*([^<]+?)\s*</td>",
        html,
        re.IGNORECASE,
    ):
        cleaned = _clean(name)
        if cleaned and "geen gegevens" not in cleaned.lower():
            managers.append({"role": role.strip(), "name": cleaned})
    return managers


def _extract_nace(html: str) -> list[dict[str, str]]:
    activities: list[dict[str, str]] = []
    for code, _display, label in re.findall(
        r"nace\.code=([\d.]+)[^\"]*\"[^>]*>([\d.]+)</a>\s*&nbsp;-&nbsp;\s*([^<]+)",
        html,
        re.IGNORECASE,
    ):
        activities.append({"code": code, "label": _clean(label)})
    if not activities:
        for code, label in re.findall(
            r"(\d{2}\.\d{3})\s*</a>\s*&nbsp;-&nbsp;\s*([^<]+)",
            html,
        ):
            activities.append({"code": code, "label": _clean(label)})
    return activities


def _extract_linked_numbers(html: str, source_number: str) -> list[str]:
    found: set[str] = set()
    for match in _ENTERPRISE_IN_URL.finditer(html):
        try:
            found.add(normalize_enterprise_number(match.group(1)))
        except ValueError:
            continue
    for match in _DIGITS_10.finditer(html):
        try:
            num = normalize_enterprise_number(match.group(1))
        except ValueError:
            continue
        if num != source_number:
            found.add(num)
    found.discard(source_number)
    return sorted(found)


def parse_kbo_enterprise_detail(
    html: bytes | str,
    *,
    enterprise_number: str,
    extractor_version: str,
    schema_version: int,
) -> tuple[dict[str, Any], list[str], bool]:
    """Retourne (fields, discovery_candidates, partial)."""
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    number = normalize_enterprise_number(enterprise_number)

    legal_name = _field_after_label(text, "Naam") or _field_after_label(text, "Nom")
    status = _field_after_label(text, "Status") or _field_after_label(text, "Statut")
    legal_form = _field_after_label(text, "Rechtsvorm") or _field_after_label(text, "Forme juridique")
    address = _field_after_label(text, "Adres van de zetel") or _field_after_label(
        text, "Adresse du siège"
    )
    postal_match = re.search(r"\b(\d{4})\b", address or "")

    fields: dict[str, Any] = {
        "enterprise_number": number,
        "legal_name": legal_name,
        "status_label": status,
        "legal_form": legal_form,
        "headquarters_address": address,
        "postal_code": postal_match.group(1) if postal_match else None,
        "managers": _extract_managers(text),
        "vat_activities": _extract_nace(text),
        "financial_notes": _field_after_label(text, "Jaarvergadering")
        or _field_after_label(text, "Assemblée générale"),
        "establishments_count": _field_after_label(
            text, "Aantal vestigingseenheden (VE)"
        )
        or _field_after_label(text, "Nombre d'unités d'établissement (UE)"),
        "entity_links": _extract_linked_numbers(text, number),
    }
    partial = not legal_name
    fields = translate_snapshot_fields(fields)
    return fields, fields.get("entity_links", []), partial
