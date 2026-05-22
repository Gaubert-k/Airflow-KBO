"""Adaptateur statuts — index Moniteur (sujet PDF) ; notaire.be optionnel (consigne TP)."""

from __future__ import annotations

import os

from packages.acquisition.models import FetchJob
from packages.acquisition.sources.common import make_job, moniteur_page, normalized_number


class StatutesAdapter:
    """
    Défaut : publications légales par BCE (Moniteur ``list.pl``) — aligné sujet PDF.

    Option : définir ``NOTAIRE_STATUTES_URL`` pour une page fixe notaire.be (démo / consigne prof).
    """

    source = "statutes"

    def build_urls(self, enterprise_number: str) -> list[FetchJob]:
        number = normalized_number(enterprise_number)
        notaire_url = os.environ.get("NOTAIRE_STATUTES_URL", "").strip()
        if notaire_url:
            return [
                make_job(
                    url=notaire_url,
                    source=self.source,
                    doc_type="statutes_notaire_info",
                    enterprise_number=number,
                )
            ]
        return [
            make_job(
                url=moniteur_page(
                    "list.pl",
                    {"language": "fr", "btw": number},
                ),
                source=self.source,
                doc_type="publications_index",
                enterprise_number=number,
            )
        ]
