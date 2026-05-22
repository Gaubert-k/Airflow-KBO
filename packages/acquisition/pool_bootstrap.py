"""Préparation du pool de proxies avant un scrape."""

from __future__ import annotations

import logging

from packages.acquisition.config import AcquisitionConfig
from packages.acquisition.proxy_pool import ProxyPool

logger = logging.getLogger(__name__)


def prepare_proxy_pool(config: AcquisitionConfig) -> ProxyPool:
    """Charge, teste (optionnel) et valide le pool avant acquisition."""
    pool = ProxyPool.from_config(config)
    total = len(pool)
    if total and config.proxy_filter_at_start and not config.allow_direct:
        ok = pool.filter_working_sync(config)
        logger.info(
            "Test proxies (probe %s, timeout %.0fs) : %d/%d joignables",
            config.proxy_probe_url,
            config.proxy_probe_timeout_s,
            ok,
            total,
        )
        if ok == 0:
            msg = (
                f"Aucun proxy HTTP fonctionnel (0/{total}) vers {config.proxy_probe_url}. "
                "La liste scripts/proxies-pool.txt contient surtout des entrées mortes — "
                "mettez à jour data/proxies/proxies.txt avec de vrais proxies HTTP(S), "
                "ou définissez ACQUISITION_ALLOW_DIRECT=1 pour le dev (connexion directe)."
            )
            raise RuntimeError(msg)
    elif total and config.allow_direct:
        logger.info(
            "%d proxies chargés — filtrage ignoré (ACQUISITION_ALLOW_DIRECT=1, connexion directe si besoin)",
            total,
        )
    elif total:
        logger.info(
            "Pool proxies : %d entrées (filtrage au démarrage désactivé)",
            total,
        )
    return pool
