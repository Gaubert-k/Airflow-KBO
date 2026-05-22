"""Adaptateur BNB / Centrale des bilans — consultation publique."""

from __future__ import annotations

from packages.acquisition.models import FetchJob
from packages.acquisition.sources.common import bnb_base_url, make_job, normalized_number


class BnbAdapter:
    """
    Portail ``consult.cbso.nbb.be`` — page de consultation par numéro d'entreprise.

    Réponse : shell HTML (SPA) ; le brut est stocké tel quel (extraction MS-04).
    """

    source = "bnb"

    def build_urls(self, enterprise_number: str) -> list[FetchJob]:
        number = normalized_number(enterprise_number)
        base = bnb_base_url().rstrip("/")
        url = f"{base}/consult-enterprise/{number}"
        return [
            make_job(
                url=url,
                source=self.source,
                doc_type="consult_profile",
                enterprise_number=number,
            )
        ]
