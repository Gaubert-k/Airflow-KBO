"""Workflow d'init complet — uniquement si volume ``data/`` vierge (première ouverture)."""

from __future__ import annotations

import logging
import os
from typing import Any

from packages.orchestration.paths import DEFAULT_CSV_DIRS
from packages.orchestration.scrape_parallel import (
    DEFAULT_SCRAPE_SOURCES,
    run_scrape_finalize,
    run_scrape_prepare,
    run_scrape_source_branch,
)
from packages.platform.volume_bootstrap import (
    is_data_volume_uninitialized,
    mark_data_volume_initialized,
)

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def run_scrape_by_source_cycle(
    *,
    limit: int,
    worker_id: str,
    wire_bridge: bool = True,
    parallel_requests_per_site: int = 5,
    kbo_use_tor: bool = True,
    kbo_direct_first: bool = True,
    tor_loop: bool = False,
) -> dict[str, Any]:
    """Un cycle ``02_scrape_by_source`` : prepare → KBO Tor → 3 sites → finalize."""
    os.environ["ACQUISITION_WORKER_ID"] = worker_id
    prep = run_scrape_prepare(limit=limit, worker_id=worker_id)
    numbers = list(prep.get("enterprise_numbers") or [])
    if not numbers:
        return {"claimed": 0, "sources": {}, "finalize": {}}

    kbo = run_scrape_source_branch(
        "kbo",
        numbers,
        wire_bridge=wire_bridge,
        parallel_requests_per_site=parallel_requests_per_site,
        kbo_use_tor=kbo_use_tor,
        kbo_direct_first=kbo_direct_first,
        tor_loop=tor_loop,
    )
    ok_numbers = list(kbo.get("kbo_ok_numbers") or [])
    secondary = {}
    for source in ("moniteur", "statutes", "bnb"):
        if not ok_numbers:
            secondary[source] = {
                "source": source,
                "probed": 0,
                "skipped": "no_kbo_ok",
            }
            continue
        secondary[source] = run_scrape_source_branch(
            source,
            ok_numbers,
            wire_bridge=wire_bridge,
            parallel_requests_per_site=parallel_requests_per_site,
            kbo_use_tor=False,
        )
    fin = run_scrape_finalize(
        numbers,
        worker_id=worker_id,
        sources=list(DEFAULT_SCRAPE_SOURCES),
    )
    return {
        "claimed": len(numbers),
        "kbo_ok": len(ok_numbers),
        "sources": {"kbo": kbo, **secondary},
        "finalize": fin,
    }


def run_bootstrap_scrape_until_idle(
    *,
    worker_id: str,
    batch_limit: int,
    max_batches: int,
    wire_bridge: bool = True,
    parallel_requests_per_site: int = 5,
) -> dict[str, Any]:
    """Scrape massif par lots jusqu'à file QUEUED_SCRAPE vide (ou plafond de lots)."""
    batches: list[dict[str, Any]] = []
    total_claimed = 0
    batch_index = 0
    safety_cap = max_batches if max_batches > 0 else 10_000

    while batch_index < safety_cap:
        batch_index += 1
        cycle = run_scrape_by_source_cycle(
            limit=batch_limit,
            worker_id=f"{worker_id}-batch-{batch_index}",
            wire_bridge=wire_bridge,
            parallel_requests_per_site=parallel_requests_per_site,
        )
        claimed = int(cycle.get("claimed") or 0)
        batches.append({"batch": batch_index, "claimed": claimed, "kbo_ok": cycle.get("kbo_ok")})
        total_claimed += claimed
        logger.info(
            "Bootstrap scrape lot %d — %d BCE claimées (total cumulé %d)",
            batch_index,
            claimed,
            total_claimed,
        )
        if claimed == 0:
            break
        if max_batches > 0 and batch_index >= max_batches:
            logger.warning(
                "Bootstrap scrape — plafond PLATFORM_BOOTSTRAP_SCRAPE_MAX_BATCHES=%d atteint",
                max_batches,
            )
            break

    return {
        "batches_run": batch_index,
        "enterprises_claimed_total": total_claimed,
        "batches": batches[-20:],
    }


def run_bootstrap_extract_until_idle(
    *,
    batch_limit: int,
    max_batches: int,
) -> dict[str, Any]:
    from packages.orchestration import run_parse_batch

    batches: list[dict[str, Any]] = []
    total_parsed = 0
    batch_index = 0
    safety_cap = max_batches if max_batches > 0 else 10_000

    while batch_index < safety_cap:
        batch_index += 1
        report = run_parse_batch(limit=batch_limit)
        claimed = int(report.get("claimed") or 0)
        succeeded = int(report.get("succeeded") or 0)
        batches.append(report)
        total_parsed += succeeded
        logger.info(
            "Bootstrap extract lot %d — claim=%d succès=%d",
            batch_index,
            claimed,
            succeeded,
        )
        if claimed == 0:
            break
        if max_batches > 0 and batch_index >= max_batches:
            break

    return {
        "batches_run": batch_index,
        "parsed_total": total_parsed,
        "last_batch": batches[-1] if batches else {},
    }


def run_platform_bootstrap(
    *,
    worker_id: str = "platform-bootstrap",
    csv_dirs: list[str] | None = None,
    ingest_batch_size: int = 50_000,
    scrape_batch_limit: int | None = None,
    scrape_max_batches: int | None = None,
    extract_batch_limit: int | None = None,
    extract_max_batches: int | None = None,
    parallel_requests_per_site: int = 5,
    wire_bridge: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """
    Init complète : ingest CSV → scrape massif → extract → analytics.

    No-op si le volume a déjà été initialisé (sauf ``force=True``).
    """
    if not force and not is_data_volume_uninitialized():
        return {
            "skipped": True,
            "reason": "data_volume_already_initialized",
        }

    from packages.orchestration import run_analytics_refresh, run_ingest_all_csv

    scrape_batch = scrape_batch_limit if scrape_batch_limit is not None else _env_int(
        "PLATFORM_BOOTSTRAP_SCRAPE_BATCH", 2000
    )
    scrape_max = scrape_max_batches if scrape_max_batches is not None else _env_int(
        "PLATFORM_BOOTSTRAP_SCRAPE_MAX_BATCHES", 0
    )
    extract_batch = extract_batch_limit if extract_batch_limit is not None else _env_int(
        "PLATFORM_BOOTSTRAP_EXTRACT_BATCH", 2000
    )
    extract_max = extract_max_batches if extract_max_batches is not None else _env_int(
        "PLATFORM_BOOTSTRAP_EXTRACT_MAX_BATCHES", 0
    )
    parallel = parallel_requests_per_site

    logger.warning(
        "=== BOOTSTRAP PREMIER DÉMARRAGE — ingest + scrape massif + extract "
        "(scrape_batch=%d, scrape_max_batches=%s) ===",
        scrape_batch,
        scrape_max if scrape_max > 0 else "illimité (jusqu'à file vide)",
    )

    dirs = csv_dirs or list(DEFAULT_CSV_DIRS)
    ingest = run_ingest_all_csv(dirs, batch_size=ingest_batch_size)
    scrape = run_bootstrap_scrape_until_idle(
        worker_id=worker_id,
        batch_limit=scrape_batch,
        max_batches=scrape_max,
        wire_bridge=wire_bridge,
        parallel_requests_per_site=parallel,
    )
    extract = run_bootstrap_extract_until_idle(
        batch_limit=extract_batch,
        max_batches=extract_max,
    )
    analytics = run_analytics_refresh(run_id=f"{worker_id}-analytics")

    summary = {
        "skipped": False,
        "ingest": ingest,
        "scrape": scrape,
        "extract": extract,
        "analytics": analytics,
        "config": {
            "scrape_batch_limit": scrape_batch,
            "scrape_max_batches": scrape_max,
            "extract_batch_limit": extract_batch,
            "extract_max_batches": extract_max,
            "parallel_requests_per_site": parallel,
        },
    }
    mark_data_volume_initialized(summary)
    return summary
