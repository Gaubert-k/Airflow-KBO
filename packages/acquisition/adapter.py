"""Interface SourceAdapter — une unité d'acquisition par source."""

from __future__ import annotations

from typing import Protocol

from packages.acquisition.models import FetchJob


class SourceAdapter(Protocol):
    source: str

    def build_urls(self, enterprise_number: str) -> list[FetchJob]:
        """Construit les jobs de téléchargement pour une entreprise."""
        ...
