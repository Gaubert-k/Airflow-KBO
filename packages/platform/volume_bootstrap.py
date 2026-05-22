"""Détection premier démarrage — volume ``data/`` vide (bootstrap une seule fois)."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MARKER_RELATIVE = Path("data") / ".platform_initialized"
HDFS_RAW_RELATIVE = Path("data") / "hdfs-stub" / "raw" / "v1"


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def marker_path(repo_root: Path | None = None) -> Path:
    return (repo_root or find_repo_root()) / MARKER_RELATIVE


def hdfs_raw_root(repo_root: Path | None = None) -> Path:
    return (repo_root or find_repo_root()) / HDFS_RAW_RELATIVE


def hdfs_has_scraped_documents(repo_root: Path | None = None) -> bool:
    """True si au moins un document brut HTML est présent dans le stub HDFS."""
    root = hdfs_raw_root(repo_root)
    if not root.is_dir():
        return False
    try:
        next(root.rglob("document.html"))
        return True
    except StopIteration:
        return False


def count_enterprises_in_db() -> int | None:
    """Compte les entreprises en base ; None si DB inaccessible."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return None
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) FROM enterprises")).scalar()
        return int(row or 0)
    except Exception as exc:
        logger.debug("count enterprises skipped: %s", exc)
        return None


def is_data_volume_uninitialized(repo_root: Path | None = None) -> bool:
    """
    Premier démarrage : pas de marqueur, pas de HTML scrapé, pas d'entreprises en base.

    Si le marqueur manque mais que des données existent déjà (volume Postgres conservé),
    on ne relance pas le bootstrap massif.
    """
    root = repo_root or find_repo_root()
    if marker_path(root).is_file():
        return False
    if hdfs_has_scraped_documents(root):
        logger.info(
            "Bootstrap ignoré — HTML présent dans %s sans marqueur",
            hdfs_raw_root(root),
        )
        return False
    entreprises = count_enterprises_in_db()
    if entreprises is not None and entreprises > 0:
        logger.info(
            "Bootstrap ignoré — %d entreprise(s) déjà en base (volume Postgres existant)",
            entreprises,
        )
        return False
    return True


def mark_data_volume_initialized(
    summary: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> Path:
    """Écrit le marqueur après bootstrap réussi (ne pas appeler si échec partiel)."""
    path = marker_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_at": datetime.now(UTC).isoformat(),
        "summary": summary,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Volume data initialisé — marqueur %s", path)
    return path


def read_initialization_marker(repo_root: Path | None = None) -> dict[str, Any] | None:
    path = marker_path(repo_root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
