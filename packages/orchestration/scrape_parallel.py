"""Orchestration scrape par source — prepare / branches / finalize (MS-10)."""

from __future__ import annotations

import logging
from typing import Any

from packages.acquisition.config import get_acquisition_config
from packages.acquisition.sources.registry import get_adapters
from packages.acquisition.worker import (
    finalize_scrape_for_enterprises,
    scrape_source_for_enterprises,
)

DEFAULT_SCRAPE_SOURCES: tuple[str, ...] = ("kbo", "moniteur", "statutes", "bnb")

from packages.acquisition.scrape_policy import (
    SOURCES_NO_PARALLEL,
    effective_parallel_requests_per_site,
)
from packages.persistence.models import Base
from packages.persistence.repositories import claim_enterprises_for_scrape
from packages.persistence.session import get_engine, session_scope
from packages.storage.paths import normalize_enterprise_number

logger = logging.getLogger(__name__)


def parse_enterprise_numbers_param(raw: object) -> list[str] | None:
    """Conf DAG / dashboard : liste, CSV ou chaîne vide."""
    if raw is None or raw == "" or raw == []:
        return None
    if isinstance(raw, list):
        nums = [str(n).strip() for n in raw if str(n).strip()]
        return [normalize_enterprise_number(n) for n in nums] if nums else None
    text = str(raw).strip()
    if not text:
        return None
    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    return [normalize_enterprise_number(p) for p in parts] if parts else None


def parse_parallel_requests_per_site(raw: object, *, default: int = 1) -> int:
    """Nombre max de requêtes HTTP simultanées par site (par task Airflow)."""
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"parallel_requests_per_site invalide: {raw!r}"
        raise ValueError(msg) from exc
    return max(1, min(value, 32))


def parse_sources_param(raw: object) -> list[str]:
    """Conf DAG ``sources`` : CSV optionnel (ex. ``kbo,bnb``)."""
    if raw is None or raw == "" or raw == []:
        return list(DEFAULT_SCRAPE_SOURCES)
    if isinstance(raw, list):
        parts = [str(s).strip().lower() for s in raw if str(s).strip()]
    else:
        text = str(raw).strip().lower()
        if not text:
            return list(DEFAULT_SCRAPE_SOURCES)
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    unknown = [p for p in parts if p not in DEFAULT_SCRAPE_SOURCES]
    if unknown:
        msg = f"Sources inconnues: {unknown} (attendu: {', '.join(DEFAULT_SCRAPE_SOURCES)})"
        raise ValueError(msg)
    return parts


def run_scrape_prepare(
    *,
    limit: int = 10,
    enterprise_numbers: list[str] | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Claim QUEUED_SCRAPE → SCRAPING ; retourne la liste pour XCom / branches."""
    cfg = get_acquisition_config()
    wid = worker_id or cfg.worker_id
    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        claimed = claim_enterprises_for_scrape(
            session,
            limit=limit,
            worker_id=wid,
            enterprise_numbers=enterprise_numbers,
        )
        session.commit()

    if enterprise_numbers and len(claimed) < len(enterprise_numbers):
        skipped = set(enterprise_numbers) - set(claimed)
        logger.warning(
            "Claim partiel: %d/%d — hors file QUEUED_SCRAPE: %s",
            len(claimed),
            len(enterprise_numbers),
            ", ".join(sorted(skipped)[:10]),
        )

    logger.info(
        "Préparation scrape — %d entreprise(s) en SCRAPING (worker=%s)",
        len(claimed),
        wid,
    )
    return {
        "enterprise_numbers": claimed,
        "claimed": len(claimed),
        "requested": len(enterprise_numbers) if enterprise_numbers else None,
    }


def run_scrape_source_branch(
    source: str,
    enterprise_numbers: list[str],
    *,
    wire_bridge: bool = True,
    parallel_requests_per_site: int = 1,
    kbo_use_tor: bool | None = None,
    tor_loop: bool | None = None,
    kbo_direct_first: bool | None = None,
) -> dict[str, Any]:
    """Une task Airflow = un site (kbo, moniteur, statutes, bnb)."""
    if not enterprise_numbers:
        logger.info("[%s] Aucune entreprise à traiter (prepare vide)", source)
        return {
            "source": source,
            "probed": 0,
            "succeeded": 0,
            "failed": 0,
            "enterprises": [],
        }
    parallel = effective_parallel_requests_per_site(source, parallel_requests_per_site)
    return scrape_source_for_enterprises(
        enterprise_numbers,
        source=source,
        wire_persistence_bridge=wire_bridge,
        parallel_requests_per_site=parallel,
        kbo_use_tor=kbo_use_tor,
        tor_loop=tor_loop,
        kbo_direct_first=kbo_direct_first,
    )


def run_scrape_finalize(
    enterprise_numbers: list[str],
    *,
    worker_id: str | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Après les branches parallèles — transition d'état globale."""
    if not enterprise_numbers:
        return {"finalized": 0, "succeeded": 0, "failed": 0, "enterprises": []}

    enabled = sources or list(DEFAULT_SCRAPE_SOURCES)
    adapters = get_adapters(enabled_sources=enabled)

    cfg = get_acquisition_config()
    wid = worker_id or cfg.worker_id
    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        report = finalize_scrape_for_enterprises(
            session,
            enterprise_numbers,
            adapters=adapters,
            worker_id=wid,
        )
        session.commit()
    report["sources"] = enabled
    return report
