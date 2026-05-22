"""Sondes par source — fetch sans transition d'état (tasks Airflow parallèles)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from packages.acquisition.config import get_acquisition_config
from packages.acquisition.fetch import polite_delay
from packages.acquisition.proxy_pool import ProxyPool
from packages.acquisition.sources.registry import get_adapters
from packages.acquisition.worker import _process_job
from packages.persistence.enums import ProcessingState
from packages.persistence.models import Base, EnterpriseProcessingState
from packages.persistence.session import get_engine, session_scope

logger = logging.getLogger(__name__)


def _list_queued_scrape(session, *, limit: int) -> list[str]:
    stmt = (
        select(EnterpriseProcessingState.enterprise_number)
        .where(EnterpriseProcessingState.state == ProcessingState.QUEUED_SCRAPE)
        .order_by(EnterpriseProcessingState.state_since)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def run_source_probe(
    source: str,
    *,
    limit: int = 10,
    wire_bridge: bool = True,
) -> dict[str, Any]:
    """
    Teste une source sur des entreprises ``QUEUED_SCRAPE`` sans les claim.

    Permet plusieurs tasks Airflow en parallèle (kbo / moniteur / …) sur la même file.
    """
    if wire_bridge:
        from packages.persistence.bridge import wire_storage_events

        wire_storage_events()

    adapters = get_adapters(enabled_sources=[source])
    if not adapters:
        msg = f"Unknown or disabled source: {source}"
        raise ValueError(msg)
    adapter = adapters[0]

    cfg = get_acquisition_config()
    pool = ProxyPool.from_config(cfg)
    engine = get_engine()
    Base.metadata.create_all(engine)

    with session_scope() as session:
        numbers = _list_queued_scrape(session, limit=limit)

    outcomes: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for index, number in enumerate(numbers):
        if index > 0:
            polite_delay(cfg, source=source)
        jobs = adapter.build_urls(number)
        if not jobs:
            failed += 1
            outcomes.append(
                {
                    "enterprise_number": number,
                    "ok": False,
                    "reason": "no_jobs",
                    "urls": [],
                }
            )
            continue

        job_ok = True
        reasons: list[str] = []
        urls: list[str] = []
        for job_index, job in enumerate(jobs):
            if job_index > 0:
                polite_delay(cfg, source=source)
            urls.append(job.url)
            ok, reason = _process_job(job, pool, cfg)
            reasons.append(reason)
            if not ok:
                job_ok = False

        if job_ok:
            succeeded += 1
        else:
            failed += 1
        outcomes.append(
            {
                "enterprise_number": number,
                "ok": job_ok,
                "reason": reasons[-1] if reasons else "unknown",
                "urls": urls,
            }
        )
        logger.info(
            "source probe",
            extra={
                "source": source,
                "enterprise_number": number,
                "ok": job_ok,
                "reason": reasons[-1] if reasons else None,
            },
        )

    return {
        "source": source,
        "mode": "probe",
        "queued_scrape_seen": len(numbers),
        "probed": len(outcomes),
        "succeeded": succeeded,
        "failed": failed,
        "enterprises": outcomes,
    }
