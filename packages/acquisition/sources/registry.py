"""Registre des adaptateurs MS-02 — scraping complet par défaut."""

from __future__ import annotations

import os
from collections.abc import Sequence

from packages.acquisition.adapter import SourceAdapter
from packages.acquisition.sources.bnb import BnbAdapter
from packages.acquisition.sources.kbo import KboAdapter
from packages.acquisition.sources.moniteur import MoniteurAdapter
from packages.acquisition.sources.statutes import StatutesAdapter

# Ordre stable : KBO → Moniteur → statuts → BNB (courtoisie inter-sites)
ALL_ADAPTERS: tuple[SourceAdapter, ...] = (
    KboAdapter(),
    MoniteurAdapter(),
    StatutesAdapter(),
    BnbAdapter(),
)

_ADAPTER_BY_NAME: dict[str, SourceAdapter] = {
    adapter.source: adapter for adapter in ALL_ADAPTERS
}


def parse_enabled_sources(raw: str | None = None) -> tuple[str, ...]:
    """
    ``ACQUISITION_ENABLED_SOURCES`` : CSV de sources (`kbo`, `moniteur`, `bnb`, `statutes`).

    Vide ou ``all`` → toutes les sources.
    """
    value = (raw if raw is not None else os.environ.get("ACQUISITION_ENABLED_SOURCES", "")).strip()
    if not value or value.lower() == "all":
        return tuple(a.source for a in ALL_ADAPTERS)
    return tuple(s.strip().lower() for s in value.split(",") if s.strip())


def get_adapters(
    *,
    enabled_sources: Sequence[str] | None = None,
) -> tuple[SourceAdapter, ...]:
    names = tuple(enabled_sources) if enabled_sources is not None else parse_enabled_sources()
    selected: list[SourceAdapter] = []
    for name in names:
        adapter = _ADAPTER_BY_NAME.get(name)
        if adapter is None:
            msg = f"unknown acquisition source: {name!r} (known: {sorted(_ADAPTER_BY_NAME)})"
            raise ValueError(msg)
        selected.append(adapter)
    return tuple(selected)


def default_adapters() -> tuple[SourceAdapter, ...]:
    return get_adapters()
