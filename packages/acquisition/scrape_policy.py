"""Politique de scrape par site — parallélisme et délais inter-requêtes."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Statuts (Moniteur / notaire) : parallèle → ban rapide ; pas de pause entre requêtes.
SOURCES_NO_PARALLEL: frozenset[str] = frozenset({"statutes"})
SOURCES_NO_INTER_REQUEST_DELAY: frozenset[str] = frozenset({"statutes"})
# Ne pas re-télécharger si raw_documents a déjà SUCCESS pour (BCE, doc_type).
SOURCES_SKIP_IF_ALREADY_STORED: frozenset[str] = frozenset({"statutes"})
# ejustice : direct uniquement ; captcha / 429 → arrêt gracieux (pas de Tor — timeouts inutiles).
SOURCES_GRACEFUL_STOP_ON_BLOCK: frozenset[str] = frozenset({"statutes"})
# Tor réservé au KBO (sites .fgov.be KBO). Vide pour statuts.
SOURCES_TOR_ESCALATION_ON_ERROR: frozenset[str] = frozenset()


def skip_inter_request_delay(source: str) -> bool:
    """Pas de jitter MS-02 entre requêtes pour cette source (séquentiel conservé)."""
    return source in SOURCES_NO_INTER_REQUEST_DELAY


def skip_if_already_stored(source: str) -> bool:
    return source in SOURCES_SKIP_IF_ALREADY_STORED


def use_tor_escalation_on_error(source: str) -> bool:
    return source in SOURCES_TOR_ESCALATION_ON_ERROR


def graceful_stop_on_block(source: str) -> bool:
    """Captcha / rate-limit : arrêter le run sans échec Airflow (partiel accepté)."""
    return source in SOURCES_GRACEFUL_STOP_ON_BLOCK


def effective_parallel_requests_per_site(source: str, requested: int) -> int:
    """Applique les plafonds par site (ex. statuts toujours séquentiel)."""
    capped = max(1, min(int(requested), 32))
    if source in SOURCES_NO_PARALLEL:
        if capped > 1:
            logger.info(
                "[%s] Parallèle interdit pour ce site — forcé à 1 requête (param=%d)",
                source,
                capped,
            )
        return 1
    return capped
