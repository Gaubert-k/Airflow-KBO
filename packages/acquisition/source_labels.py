"""Libellés lisibles pour les logs Airflow / dashboard."""

from __future__ import annotations

SOURCE_LABELS: dict[str, str] = {
    "kbo": "KBO (Banque-Carrefour des Entreprises)",
    "moniteur": "Moniteur belge (SPF Justice)",
    "statutes": "Statuts / notaire (e-notaire)",
    "bnb": "BNB (Banque Nationale de Belgique)",
}


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)
