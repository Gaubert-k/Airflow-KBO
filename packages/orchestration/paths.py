"""Chemins par défaut dans les conteneurs Airflow (MS-10)."""

from __future__ import annotations

DEFAULT_SEED_CSV = "/opt/airflow/data/seed/csv/sample_enterprises.csv"
DEFAULT_SEED_CSV_DIR = "/opt/airflow/data/seed/csv"
DEFAULT_INPUT_CSV_DIR = "/opt/airflow/data/input/csv"

# Ordre : seed (dev) puis input (fichiers prof) — une seule passe DAG 01
DEFAULT_CSV_DIRS: tuple[str, ...] = (
    DEFAULT_SEED_CSV_DIR,
    DEFAULT_INPUT_CSV_DIR,
)
