"""Adaptateur Moniteur belge (eJustice) — publications personnes morales."""

from __future__ import annotations

from packages.acquisition.models import FetchJob
from packages.acquisition.sources.common import make_job, moniteur_page, normalized_number


class MoniteurAdapter:
    """
    Recherche des actes publiés au Moniteur pour un numéro d'entreprise (BCE).

    ``rech.pl`` : résultats de recherche (HTML) liés au numéro ``btw``.
    """

    source = "moniteur"

    def build_urls(self, enterprise_number: str) -> list[FetchJob]:
        number = normalized_number(enterprise_number)
        return [
            make_job(
                url=moniteur_page(
                    "rech.pl",
                    {
                        "language": "fr",
                        "btw": number,
                    },
                ),
                source=self.source,
                doc_type="publication_search",
                enterprise_number=number,
            )
        ]
