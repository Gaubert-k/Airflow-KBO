"""Callables MS-10 — délégation aux modules gelés MS-01 / MS-02."""

from __future__ import annotations

from typing import Any


def run_ingest_csv(
    csv_path: str,
    *,
    column: str | None = None,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """Ingère un CSV via ``packages.ingestion.ingest_csv`` (contrat MS-01 gelé)."""
    from packages.ingestion import ingest_csv
    from packages.orchestration.serializers import ingest_report_to_dict

    report = ingest_csv(csv_path, column=column, batch_size=batch_size)
    return ingest_report_to_dict(report)


def run_ingest_all_csv(
    csv_dirs: list[str] | None = None,
    *,
    column: str | None = None,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """Tous les CSV entreprise → base PostgreSQL (lancer une fois, puis scrape uniquement)."""
    from packages.orchestration.ingest_all import run_ingest_all_csv as _run_all

    return _run_all(csv_dirs, column=column, batch_size=batch_size)


def run_scrape_batch(
    *,
    limit: int = 10,
    enterprise_numbers: list[str] | None = None,
    sources: list[str] | None = None,
    wire_bridge: bool = True,
) -> dict[str, Any]:
    """
    Lance un lot de scrape via ``packages.acquisition.worker.scrape_batch``.

    ``wire_bridge`` : appelle ``wire_storage_events()`` (MS-03/05) si True.
    """
    from packages.acquisition.sources.registry import get_adapters
    from packages.acquisition.worker import scrape_batch
    from packages.orchestration.serializers import scrape_report_to_dict

    if wire_bridge:
        from packages.persistence.bridge import wire_storage_events

        wire_storage_events()

    kwargs: dict[str, Any] = {
        "limit": limit,
        "wire_persistence_bridge": False,
    }
    if enterprise_numbers is not None:
        kwargs["enterprise_numbers"] = enterprise_numbers
    if sources is not None:
        kwargs["adapters"] = get_adapters(enabled_sources=sources)

    report = scrape_batch(**kwargs)
    return scrape_report_to_dict(report)


def run_scrape_single_source(
    source: str,
    *,
    enterprise_numbers: list[str],
    wire_bridge: bool = True,
) -> dict[str, Any]:
    """Branche parallèle du DAG ``02_scrape_by_source`` (une source / un site)."""
    return run_scrape_source_branch(
        source,
        enterprise_numbers,
        wire_bridge=wire_bridge,
    )


def run_scrape_prepare(
    *,
    limit: int = 10,
    enterprise_numbers: list[str] | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    from packages.orchestration.scrape_parallel import run_scrape_prepare as _prepare

    return _prepare(
        limit=limit,
        enterprise_numbers=enterprise_numbers,
        worker_id=worker_id,
    )


def run_scrape_finalize(
    enterprise_numbers: list[str],
    *,
    worker_id: str | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    from packages.orchestration.scrape_parallel import run_scrape_finalize as _finalize

    return _finalize(enterprise_numbers, worker_id=worker_id, sources=sources)


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
    from packages.orchestration.scrape_parallel import run_scrape_source_branch as _branch

    return _branch(
        source,
        enterprise_numbers,
        wire_bridge=wire_bridge,
        parallel_requests_per_site=parallel_requests_per_site,
        kbo_use_tor=kbo_use_tor,
        tor_loop=tor_loop,
        kbo_direct_first=kbo_direct_first,
    )


def run_parse_batch(*, limit: int = 10) -> dict[str, Any]:
    from packages.extraction.worker import parse_batch
    from packages.orchestration.serializers import parse_report_to_dict

    report = parse_batch(limit=limit)
    return parse_report_to_dict(report)


def run_discovery_fanout(*, hours: int = 48, limit: int = 50) -> dict[str, Any]:
    from packages.discovery.service import fanout_from_recent_snapshots
    from packages.persistence.models import Base
    from packages.persistence.session import get_engine, session_scope

    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        return fanout_from_recent_snapshots(session, hours=hours, limit=limit)


def run_lifecycle_tick(*, limit: int = 50) -> dict[str, Any]:
    from packages.lifecycle.scheduler import lifecycle_tick
    from packages.orchestration.serializers import lifecycle_report_to_dict
    from packages.persistence.models import Base
    from packages.persistence.session import get_engine, session_scope

    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        report = lifecycle_tick(session, limit=limit)
        session.commit()
    return lifecycle_report_to_dict(report)


def run_analytics_refresh(*, run_id: str | None = None) -> dict[str, Any]:
    from packages.analytics.refresh import analytics_refresh
    from packages.orchestration.serializers import analytics_report_to_dict

    report = analytics_refresh(run_id=run_id)
    return analytics_report_to_dict(report)
