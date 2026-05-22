"""Adaptateurs par source publique (MS-02 complet)."""

from packages.acquisition.sources.bnb import BnbAdapter
from packages.acquisition.sources.kbo import KboAdapter, format_kbo_nummer
from packages.acquisition.sources.moniteur import MoniteurAdapter
from packages.acquisition.sources.registry import ALL_ADAPTERS, default_adapters, get_adapters
from packages.acquisition.sources.statutes import StatutesAdapter

__all__ = [
    "ALL_ADAPTERS",
    "BnbAdapter",
    "KboAdapter",
    "MoniteurAdapter",
    "StatutesAdapter",
    "default_adapters",
    "format_kbo_nummer",
    "get_adapters",
]
