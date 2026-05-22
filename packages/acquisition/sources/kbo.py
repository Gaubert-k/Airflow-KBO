"""Adaptateur KBO Public Search — fiche entreprise (sujet PDF)."""

from __future__ import annotations

import os

from packages.acquisition.models import FetchJob
from packages.acquisition.sources.common import (
    KBO_DEFAULT_LANG,
    kbo_formatted_nummer,
    kbo_page,
    make_job,
    normalized_number,
)


def _kbo_include_profile() -> bool:
    return os.environ.get("KBO_INCLUDE_PROFILE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class KboAdapter:
    """
    Sources KBO publiques pour un numéro d'entreprise.

    Par défaut : uniquement ``enterprise_detail`` (fiche complète).

    - ``profile`` (formulaire recherche) : optionnel via ``KBO_INCLUDE_PROFILE=true``.
    """

    source = "kbo"

    def build_urls(self, enterprise_number: str) -> list[FetchJob]:
        number = normalized_number(enterprise_number)
        jobs: list[FetchJob] = []
        if _kbo_include_profile():
            formatted = kbo_formatted_nummer(number)
            jobs.append(
                make_job(
                    url=kbo_page(
                        "zoeknummerform.html",
                        {"lang": KBO_DEFAULT_LANG, "nummer": formatted},
                    ),
                    source=self.source,
                    doc_type="profile",
                    enterprise_number=number,
                )
            )
        jobs.append(
            make_job(
                url=kbo_page(
                    "toonondernemingps.html",
                    {"lang": KBO_DEFAULT_LANG, "ondernemingsnummer": number},
                ),
                source=self.source,
                doc_type="enterprise_detail",
                enterprise_number=number,
            )
        )
        return jobs


# Rétrocompat tests / imports
format_kbo_nummer = kbo_formatted_nummer
