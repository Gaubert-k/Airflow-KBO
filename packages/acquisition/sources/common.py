"""Helpers partagés — construction d'URLs par numéro d'entreprise (10 chiffres)."""

from __future__ import annotations

import os
from urllib.parse import urlencode

from packages.acquisition.models import FetchJob
from packages.storage.paths import normalize_enterprise_number

DEFAULT_KBO_BASE = "https://kbopub.economie.fgov.be/kbopub/"
# Langue par défaut des pages KBO publiques (affichage dashboard en français).
KBO_DEFAULT_LANG = "fr"
DEFAULT_BNB_BASE = "https://consult.cbso.nbb.be/"
DEFAULT_MONITEUR_BASE = "https://www.ejustice.just.fgov.be/cgi_tsv/"


def _base_url(env_name: str, default: str) -> str:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    return raw if raw.endswith("/") else f"{raw}/"


def kbo_base_url() -> str:
    return _base_url("KBO_PUBLIC_BASE_URL", DEFAULT_KBO_BASE)


def bnb_base_url() -> str:
    return _base_url("BNB_CONSULT_BASE_URL", DEFAULT_BNB_BASE)


def moniteur_base_url() -> str:
    return _base_url("MONITEUR_EJUSTICE_BASE_URL", DEFAULT_MONITEUR_BASE)


def normalized_number(enterprise_number: str) -> str:
    return normalize_enterprise_number(enterprise_number)


def kbo_formatted_nummer(enterprise_number: str) -> str:
    """10 chiffres → XXXX.XXX.XXX (paramètre `nummer` du formulaire KBO)."""
    digits = normalized_number(enterprise_number)
    return f"{digits[0:4]}.{digits[4:7]}.{digits[7:10]}"


def make_job(
    *,
    url: str,
    source: str,
    doc_type: str,
    enterprise_number: str,
) -> FetchJob:
    return FetchJob(
        url=url,
        source=source,
        doc_type=doc_type,
        enterprise_number=normalized_number(enterprise_number),
    )


def kbo_page(path: str, params: dict[str, str]) -> str:
    """Construit une URL sous ``KBO_PUBLIC_BASE_URL`` (ex. ``toonondernemingps.html``)."""
    base = kbo_base_url()
    path = path.lstrip("/")
    query = urlencode(params)
    return f"{base}{path}?{query}" if query else f"{base}{path}"


def moniteur_page(script: str, params: dict[str, str]) -> str:
    base = moniteur_base_url()
    script = script.lstrip("/")
    query = urlencode(params)
    return f"{base}{script}?{query}" if query else f"{base}{script}"
