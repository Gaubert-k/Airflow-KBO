"""Worker scrape — intégration MS-03 + MS-05."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from packages.acquisition.adapter import SourceAdapter
from packages.acquisition.config import AcquisitionConfig, get_acquisition_config
from packages.acquisition.source_labels import source_label
from packages.acquisition.fetch import fetch, polite_delay
from packages.acquisition.metrics import (
    record_scrape_attempt,
    record_scrape_failure,
    record_scrape_success,
)
from packages.acquisition.models import (
    CaptchaBlockedError,
    FetchJob,
    REASON_CAPTCHA_SUSPECT,
    ValidationAction,
)
from packages.acquisition.proxy_pool import ProxyPool
from packages.acquisition.tor_strategy import (
    KboEgressLane,
    KboTorLaneCoordinator,
    build_kbo_lanes,
    is_kbo_rate_or_captcha,
    is_tor_escalation_reason,
)
from packages.acquisition.sources.registry import default_adapters
from packages.acquisition.validate import validate_fetch
from packages.persistence.enums import ProcessingState
from packages.persistence.models import Base, RawDocument
from packages.persistence.repositories import (
    claim_enterprises_for_scrape,
    transition_state,
)
from packages.persistence.exceptions import StateTransitionError
from packages.persistence.session import get_engine, session_scope
from packages.storage.raw_store import store_raw_bundle

logger = logging.getLogger(__name__)

DEFAULT_ADAPTERS: tuple[SourceAdapter, ...] = default_adapters()


@dataclass
class ScrapeReport:
    claimed: int
    succeeded: int
    failed: int
    enterprises: list[str]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _build_metadata(
    job: FetchJob,
    *,
    http_status: int,
    proxy_or_ip: str,
    attempt_count: int,
    download_status: str,
) -> dict:
    now = _utc_now_iso()
    return {
        "scraped_at": now,
        "source": job.source,
        "download_status": download_status,
        "http_status": http_status,
        "proxy_or_ip": proxy_or_ip,
        "attempt_count": attempt_count,
        "last_updated_at": now,
        "content_type": "text/html",
        "url": job.url,
        "doc_type": job.doc_type,
    }


def _max_fetch_attempts(config: AcquisitionConfig, proxy_pool: ProxyPool) -> int:
    return config.max_retries


def _process_job(
    job: FetchJob,
    proxy_pool: ProxyPool,
    config: AcquisitionConfig,
    *,
    egress_lane: KboEgressLane | None = None,
    raise_on_captcha: bool | None = None,
) -> tuple[bool, str]:
    """Retourne (succès, reason_code)."""
    record_scrape_attempt(job.source)
    last_reason = "unknown"
    max_attempts = _max_fetch_attempts(config, proxy_pool)
    abort_on_captcha = (
        raise_on_captcha if raise_on_captcha is not None else egress_lane is None
    )

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            polite_delay(config, source=job.source)

        if egress_lane is not None:
            result = fetch(
                job,
                proxy_pool,
                config=config,
                attempt_count=attempt,
                force_proxy_url=egress_lane.proxy_url,
                force_proxy_label=egress_lane.name,
            )
        else:
            result = fetch(job, proxy_pool, config=config, attempt_count=attempt)
        decision = validate_fetch(result)
        last_reason = decision.reason_code

        if decision.reason_code == REASON_CAPTCHA_SUSPECT:
            logger.warning(
                "[%s] BCE %s — captcha / blocage (%s) → %s",
                source_label(job.source),
                job.enterprise_number,
                egress_lane.name if egress_lane else "direct",
                result.final_url or job.url,
            )
            record_scrape_failure(job.source, reason=REASON_CAPTCHA_SUSPECT)
            if abort_on_captcha:
                raise CaptchaBlockedError(
                    f"Captcha sur {job.source} (BCE {job.enterprise_number}) — scrape interrompu"
                )
            return False, decision.reason_code

        if decision.action == ValidationAction.STORE:
            meta = _build_metadata(
                job,
                http_status=int(result.http_status or 0),
                proxy_or_ip=result.proxy_or_ip,
                attempt_count=attempt,
                download_status="SUCCESS",
            )
            stored = store_raw_bundle(
                source=job.source,
                enterprise_number=job.enterprise_number,
                doc_type=job.doc_type,
                content=result.body or b"",
                metadata=meta,
            )
            logger.info(
                "[%s] BCE %s — document brut enregistré (%s, HTTP %s, %d octets) → %s",
                source_label(job.source),
                job.enterprise_number,
                job.doc_type,
                int(result.http_status or 0),
                stored.size_bytes,
                job.url,
            )
            record_scrape_success(job.source)
            return True, decision.reason_code

        if decision.action == ValidationAction.DROP:
            logger.warning(
                "[%s] BCE %s — rejet (%s) %s raison=%s",
                source_label(job.source),
                job.enterprise_number,
                job.doc_type,
                job.url,
                decision.reason_code,
            )
            record_scrape_failure(job.source, reason=decision.reason_code)
            return False, decision.reason_code

        # RETRY — boucle continue

    record_scrape_failure(job.source, reason=last_reason)
    return False, last_reason


def scrape_enterprise(
    session: Session,
    enterprise_number: str,
    *,
    adapters: Sequence[SourceAdapter] = DEFAULT_ADAPTERS,
    proxy_pool: ProxyPool | None = None,
    config: AcquisitionConfig | None = None,
    worker_id: str | None = None,
) -> bool:
    """
    Scrape une entreprise déjà en état SCRAPING.

    Succès : SCRAPING → QUEUED_PARSE. Échec : SCRAPING → FAILED_SCRAPE.
    """
    cfg = config or get_acquisition_config()
    pool = proxy_pool or ProxyPool.from_config(cfg)
    wid = worker_id or cfg.worker_id

    jobs: list[FetchJob] = []
    for adapter in adapters:
        jobs.extend(adapter.build_urls(enterprise_number))

    if not jobs:
        transition_state(
            session,
            enterprise_number,
            ProcessingState.SCRAPING,
            ProcessingState.FAILED_SCRAPE,
            lock_owner=wid,
            lock_until=None,
        )
        return False

    all_ok = True
    try:
        for index, job in enumerate(jobs):
            if index > 0:
                polite_delay(cfg, source=job.source)
            ok, reason = _process_job(job, pool, cfg)
            if not ok:
                all_ok = False
                logger.warning(
                    "scrape job failed",
                    extra={
                        "enterprise_number": enterprise_number,
                        "source": job.source,
                        "reason": reason,
                    },
                )
    except Exception:
        logger.exception("unrecoverable scrape error for %s", enterprise_number)
        try:
            transition_state(
                session,
                enterprise_number,
                ProcessingState.SCRAPING,
                ProcessingState.FAILED_SCRAPE,
                lock_owner=wid,
                lock_until=None,
            )
        except Exception:
            logger.exception("failed to mark FAILED_SCRAPE for %s", enterprise_number)
        return False

    if all_ok:
        transition_state(
            session,
            enterprise_number,
            ProcessingState.SCRAPING,
            ProcessingState.QUEUED_PARSE,
            lock_owner=wid,
            lock_until=None,
        )
        return True

    transition_state(
        session,
        enterprise_number,
        ProcessingState.SCRAPING,
        ProcessingState.FAILED_SCRAPE,
        lock_owner=wid,
        lock_until=None,
    )
    return False


def _scrape_one_enterprise_for_source(
    number: str,
    *,
    adapter: SourceAdapter,
    source: str,
    proxy_pool: ProxyPool,
    cfg: AcquisitionConfig,
    egress_lane: KboEgressLane | None = None,
    existing_success: frozenset[tuple[str, str]] | None = None,
    raise_on_captcha: bool | None = None,
) -> dict:
    """Scrape toutes les URLs d'une source pour un numéro BCE (séquentiel par entreprise)."""
    jobs = adapter.build_urls(number)
    if not jobs:
        logger.warning(
            "[%s] BCE %s — aucune URL à récupérer",
            source_label(source),
            number,
        )
        return {
            "enterprise_number": number,
            "source": source,
            "ok": False,
            "reason": "no_jobs",
        }

    job_ok = True
    last_reason = "unknown"
    fetched_any = False
    delay_before_next_fetch = False
    for job in jobs:
        if (
            existing_success is not None
            and (number, job.doc_type) in existing_success
        ):
            logger.info(
                "[%s] BCE %s — déjà en SUCCESS (%s), requête ignorée",
                source_label(source),
                number,
                job.doc_type,
            )
            last_reason = "already_stored"
            continue

        if delay_before_next_fetch:
            polite_delay(cfg, source=source)
        ok, reason = _process_job(
            job,
            proxy_pool,
            cfg,
            egress_lane=egress_lane,
            raise_on_captcha=raise_on_captcha
            if raise_on_captcha is not None
            else (False if egress_lane else None),
        )
        fetched_any = True
        delay_before_next_fetch = True
        last_reason = reason
        if not ok:
            job_ok = False
            if egress_lane and is_tor_escalation_reason(reason):
                break

    if not fetched_any and last_reason == "already_stored":
        return {
            "enterprise_number": number,
            "source": source,
            "ok": True,
            "reason": "already_stored",
        }

    return {
        "enterprise_number": number,
        "source": source,
        "ok": job_ok,
        "reason": last_reason,
    }


def _scrape_one_bce_tor_lanes(
    number: str,
    *,
    adapter: SourceAdapter,
    source: str,
    cfg: AcquisitionConfig,
    coordinator: KboTorLaneCoordinator,
    proxy_pool: ProxyPool,
    existing_success: frozenset[tuple[str, str]] | None = None,
) -> dict:
    """
    Une BCE : lane courante partagée ; captcha / 429 → bascule vers la Tor suivante.
    """
    while True:
        lane = coordinator.current_lane()
        outcome = _scrape_one_enterprise_for_source(
            number,
            adapter=adapter,
            source=source,
            proxy_pool=proxy_pool,
            cfg=cfg,
            egress_lane=lane,
            existing_success=existing_success,
        )
        if outcome.get("ok"):
            return outcome
        reason = str(outcome.get("reason", ""))
        if not is_tor_escalation_reason(reason):
            return outcome
        if coordinator.escalate_on_captcha():
            polite_delay(cfg, source=source)
            continue
        if coordinator.restart_loop_cycle():
            polite_delay(cfg, source=source)
            continue
        return {
            **outcome,
            "ok": False,
            "reason": "tor_lanes_exhausted",
        }


def _scrape_one_bce_kbo_tor_lanes(
    number: str,
    *,
    adapter: SourceAdapter,
    cfg: AcquisitionConfig,
    coordinator: KboTorLaneCoordinator,
    proxy_pool: ProxyPool,
) -> dict:
    return _scrape_one_bce_tor_lanes(
        number,
        adapter=adapter,
        source="kbo",
        cfg=cfg,
        coordinator=coordinator,
        proxy_pool=proxy_pool,
    )


def _scrape_kbo_tor_passes(
    enterprise_numbers: Sequence[str],
    *,
    adapter: SourceAdapter,
    cfg: AcquisitionConfig,
    tor_loop: bool,
    kbo_direct_first: bool | None,
    parallel_requests_per_site: int,
) -> dict:
    """KBO : direct puis tor1→tor2→tor3 ; premier captcha = bascule immédiate pour tout le run."""
    from dataclasses import replace

    if kbo_direct_first is not None:
        cfg = replace(cfg, kbo_direct_first=kbo_direct_first)

    lanes = build_kbo_lanes(cfg)
    coordinator = KboTorLaneCoordinator(
        lanes=lanes,
        tor_loop=tor_loop,
        tor_loop_min_interval_s=cfg.tor_loop_min_interval_s,
    )
    numbers = list(enterprise_numbers)
    direct_pool = ProxyPool(entries=[], allow_direct=True)
    concurrency = max(1, min(int(parallel_requests_per_site), 32))

    logger.info(
        "[KBO] %d entreprise(s) (limite globale prepare), parallèle=%d, lanes=%s",
        len(numbers),
        concurrency,
        [lane.name for lane in lanes],
    )

    outcomes: list[dict] = []
    if concurrency <= 1:
        for index, number in enumerate(numbers):
            if index > 0:
                polite_delay(cfg)
            outcomes.append(
                _scrape_one_bce_kbo_tor_lanes(
                    number,
                    adapter=adapter,
                    cfg=cfg,
                    coordinator=coordinator,
                    proxy_pool=direct_pool,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_map = {
                executor.submit(
                    _scrape_one_bce_kbo_tor_lanes,
                    number,
                    adapter=adapter,
                    cfg=cfg,
                    coordinator=coordinator,
                    proxy_pool=direct_pool,
                ): number
                for number in numbers
            }
            by_number: dict[str, dict] = {}
            for future in as_completed(future_map):
                number = future_map[future]
                try:
                    by_number[number] = future.result()
                except Exception:
                    logger.exception("[KBO] BCE %s — erreur scrape Tor", number)
                    by_number[number] = {
                        "enterprise_number": number,
                        "source": "kbo",
                        "ok": False,
                        "reason": "worker_error",
                    }
            outcomes = [by_number[n] for n in numbers if n in by_number]

    captcha_fail = [o for o in outcomes if o.get("reason") == "tor_lanes_exhausted"]
    if captcha_fail and not tor_loop:
        raise CaptchaBlockedError(
            f"KBO bloqué après lanes {coordinator.lanes_used()} — "
            f"{len(captcha_fail)}/{len(outcomes)} BCE en échec captcha"
        )

    succeeded = sum(1 for o in outcomes if o.get("ok"))
    kbo_ok = [o["enterprise_number"] for o in outcomes if o.get("ok")]

    return {
        "source": "kbo",
        "source_label": source_label("kbo"),
        "parallel_requests_per_site": concurrency,
        "probed": len(outcomes),
        "succeeded": succeeded,
        "failed": len(outcomes) - succeeded,
        "enterprises": outcomes,
        "kbo_ok_numbers": kbo_ok,
        "tor_lanes_used": coordinator.lanes_used(),
        "loop_cycles": coordinator.loop_cycles,
    }


def _scrape_statutes_direct_passes(
    enterprise_numbers: Sequence[str],
    *,
    adapter: SourceAdapter,
    cfg: AcquisitionConfig,
    existing_success: frozenset[tuple[str, str]] | None = None,
) -> dict:
    """
    Statuts : IP directe uniquement (pas de Tor sur ejustice).

    Captcha / 429 : arrêt immédiat du run, task Airflow en succès (résultat partiel OK).
    """
    numbers = list(enterprise_numbers)
    src = "statutes"
    direct_pool = ProxyPool(entries=[], allow_direct=True)

    logger.info(
        "[%s] %d entreprise(s), direct uniquement (arrêt gracieux si blocage)",
        source_label(src),
        len(numbers),
    )

    outcomes: list[dict] = []
    stopped_early = False
    stop_reason: str | None = None

    for index, number in enumerate(numbers):
        if index > 0:
            polite_delay(cfg, source=src)
        outcome = _scrape_one_enterprise_for_source(
            number,
            adapter=adapter,
            source=src,
            proxy_pool=direct_pool,
            cfg=cfg,
            existing_success=existing_success,
            raise_on_captcha=False,
        )
        outcomes.append(outcome)
        reason = str(outcome.get("reason", ""))
        if is_tor_escalation_reason(reason):
            logger.warning(
                "[%s] Blocage (%s) sur BCE %s — arrêt du run (succès Airflow, partiel accepté)",
                source_label(src),
                reason,
                number,
            )
            stopped_early = True
            stop_reason = reason
            break

    succeeded = sum(1 for o in outcomes if o.get("ok"))
    failed = len(outcomes) - succeeded
    skipped_stored = sum(1 for o in outcomes if o.get("reason") == "already_stored")

    return {
        "source": src,
        "source_label": source_label(src),
        "parallel_requests_per_site": 1,
        "probed": len(outcomes),
        "succeeded": succeeded,
        "failed": failed,
        "skipped_already_stored": skipped_stored,
        "enterprises": outcomes,
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "pending_not_processed": len(numbers) - len(outcomes),
    }


def scrape_source_for_enterprises(
    enterprise_numbers: Sequence[str],
    *,
    source: str,
    config: AcquisitionConfig | None = None,
    wire_persistence_bridge: bool = False,
    parallel_requests_per_site: int = 1,
    proxy_pool: ProxyPool | None = None,
    kbo_use_tor: bool | None = None,
    tor_loop: bool | None = None,
    kbo_direct_first: bool | None = None,
) -> dict:
    """
    Scrape une source (kbo, moniteur, …) pour des entreprises déjà en SCRAPING.

    Utilisé par les tasks Airflow parallèles du DAG ``02_scrape_by_source``.
    """
    from packages.acquisition.sources.registry import get_adapters

    cfg = config or get_acquisition_config()
    if wire_persistence_bridge:
        from packages.persistence.bridge import wire_storage_events

        wire_storage_events()

    adapters = get_adapters(enabled_sources=[source])
    if not adapters:
        msg = f"Unknown source: {source}"
        raise ValueError(msg)
    adapter = adapters[0]
    from packages.acquisition.scrape_policy import (
        effective_parallel_requests_per_site,
        graceful_stop_on_block,
        skip_if_already_stored,
    )
    from packages.persistence.repositories import fetch_success_raw_keys_for_source
    from packages.persistence.session import session_scope

    concurrency = effective_parallel_requests_per_site(source, parallel_requests_per_site)
    numbers = list(enterprise_numbers)

    existing_success: frozenset[tuple[str, str]] | None = None
    if skip_if_already_stored(source) and numbers:
        with session_scope() as session:
            existing_success = fetch_success_raw_keys_for_source(
                session,
                enterprise_numbers=numbers,
                source=source,
            )
        if existing_success:
            logger.info(
                "[%s] %d couple(s) BCE/doc_type déjà SUCCESS — pas de re-téléchargement",
                source_label(source),
                len(existing_success),
            )

    use_tor = kbo_use_tor if kbo_use_tor is not None else cfg.use_tor
    if source == "kbo" and use_tor:
        return _scrape_kbo_tor_passes(
            numbers,
            adapter=adapter,
            cfg=cfg,
            tor_loop=tor_loop if tor_loop is not None else cfg.tor_loop,
            kbo_direct_first=kbo_direct_first,
            parallel_requests_per_site=concurrency,
        )

    if source == "statutes" and graceful_stop_on_block(source):
        return _scrape_statutes_direct_passes(
            numbers,
            adapter=adapter,
            cfg=cfg,
            existing_success=existing_success,
        )

    logger.info(
        "[%s] %d entreprise(s), %d requête(s) en parallèle vers le site",
        source_label(source),
        len(numbers),
        concurrency,
    )

    shared_pool = proxy_pool if proxy_pool is not None else ProxyPool.from_config(cfg)

    def _run_one(number: str) -> dict:
        return _scrape_one_enterprise_for_source(
            number,
            adapter=adapter,
            source=source,
            proxy_pool=shared_pool,
            cfg=cfg,
            existing_success=existing_success,
        )

    outcomes: list[dict] = []
    if concurrency <= 1:
        for index, number in enumerate(numbers):
            if index > 0:
                polite_delay(cfg, source=source)
            outcomes.append(_run_one(number))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_map = {executor.submit(_run_one, n): n for n in numbers}
            by_number: dict[str, dict] = {}
            for future in as_completed(future_map):
                number = future_map[future]
                try:
                    by_number[number] = future.result()
                except CaptchaBlockedError:
                    raise
                except Exception:
                    logger.exception(
                        "[%s] BCE %s — erreur scrape parallèle",
                        source_label(source),
                        number,
                    )
                    by_number[number] = {
                        "enterprise_number": number,
                        "source": source,
                        "ok": False,
                        "reason": "worker_error",
                    }
            outcomes = [by_number[n] for n in numbers if n in by_number]

    succeeded = sum(1 for o in outcomes if o.get("ok"))
    failed = len(outcomes) - succeeded
    skipped_stored = sum(1 for o in outcomes if o.get("reason") == "already_stored")

    return {
        "source": source,
        "source_label": source_label(source),
        "parallel_requests_per_site": concurrency,
        "probed": len(outcomes),
        "succeeded": succeeded,
        "failed": failed,
        "skipped_already_stored": skipped_stored,
        "enterprises": outcomes,
    }


def finalize_scrape_for_enterprises(
    session: Session,
    enterprise_numbers: Sequence[str],
    *,
    adapters: Sequence[SourceAdapter] = DEFAULT_ADAPTERS,
    worker_id: str | None = None,
) -> dict:
    """SCRAPING → QUEUED_PARSE ou FAILED_SCRAPE selon couverture des sources demandées."""
    from sqlalchemy import func, select

    wid = worker_id or get_acquisition_config().worker_id
    required = list(adapters)
    required_count = len(required)

    succeeded = 0
    failed = 0
    details: list[dict] = []

    for number in enterprise_numbers:
        missing: list[str] = []
        for adapter in adapters:
            src = adapter.source
            count = session.scalar(
                select(func.count())
                .select_from(RawDocument)
                .where(
                    RawDocument.enterprise_number == number,
                    RawDocument.source == src,
                    RawDocument.download_status == "SUCCESS",
                )
            )
            if not count:
                missing.append(src)

        try:
            if not missing:
                transition_state(
                    session,
                    number,
                    ProcessingState.SCRAPING,
                    ProcessingState.QUEUED_PARSE,
                    lock_owner=wid,
                    lock_until=None,
                )
                succeeded += 1
                details.append({"enterprise_number": number, "ok": True})
                logger.info(
                    "BCE %s — scrape terminé (%d/%d sources) → file parse",
                    number,
                    required_count,
                    required_count,
                )
            else:
                transition_state(
                    session,
                    number,
                    ProcessingState.SCRAPING,
                    ProcessingState.FAILED_SCRAPE,
                    lock_owner=wid,
                    lock_until=None,
                )
                failed += 1
                details.append(
                    {
                        "enterprise_number": number,
                        "ok": False,
                        "missing_sources": missing,
                    }
                )
                logger.warning(
                    "BCE %s — scrape incomplet, sources manquantes: %s",
                    number,
                    ", ".join(source_label(s) for s in missing),
                )
        except StateTransitionError as exc:
            failed += 1
            details.append(
                {"enterprise_number": number, "ok": False, "error": str(exc)}
            )
            logger.warning("BCE %s — finalisation impossible: %s", number, exc)

    return {
        "finalized": len(enterprise_numbers),
        "succeeded": succeeded,
        "failed": failed,
        "enterprises": details,
    }


def scrape_batch(
    *,
    limit: int = 10,
    enterprise_numbers: list[str] | None = None,
    adapters: Sequence[SourceAdapter] = DEFAULT_ADAPTERS,
    config: AcquisitionConfig | None = None,
    wire_persistence_bridge: bool = False,
) -> ScrapeReport:
    """
    Claim QUEUED_SCRAPE → scrape → transitions.

    ``wire_persistence_bridge`` : enregistre raw_documents via MS-05 (optionnel).
    """
    cfg = config or get_acquisition_config()
    if wire_persistence_bridge:
        from packages.persistence.bridge import wire_storage_events

        wire_storage_events()

    engine = get_engine()
    Base.metadata.create_all(engine)

    proxy_pool = ProxyPool.from_config(cfg)
    succeeded = 0
    failed = 0
    enterprises: list[str] = []

    with session_scope() as session:
        claimed = claim_enterprises_for_scrape(
            session,
            limit=limit,
            worker_id=cfg.worker_id,
            enterprise_numbers=enterprise_numbers,
        )
        session.commit()

        for number in claimed:
            enterprises.append(number)
            try:
                ok = scrape_enterprise(
                    session,
                    number,
                    adapters=adapters,
                    proxy_pool=proxy_pool,
                    config=cfg,
                )
                session.commit()
                if ok:
                    succeeded += 1
                else:
                    failed += 1
            except Exception:
                logger.exception("batch scrape error for %s", number)
                session.rollback()
                failed += 1

    return ScrapeReport(
        claimed=len(claimed),
        succeeded=succeeded,
        failed=failed,
        enterprises=enterprises,
    )
