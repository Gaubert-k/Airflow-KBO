"""Tests MS-01 — ingestion CSV (SQLite en mémoire)."""

from __future__ import annotations

from pathlib import Path

import pytest
from packages.ingestion.config import IngestionConfig
from packages.ingestion.ingest import ingest_csv, reset_persistence_for_tests
from packages.persistence.config import PersistenceConfig
from packages.persistence.enums import ProcessingState, SeedSource
from packages.persistence.models import Base, Enterprise
from packages.persistence.session import get_engine, reset_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO_ROOT / "data" / "seed" / "csv" / "sample_enterprises.csv"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def ingest_env(tmp_path: Path) -> tuple[PersistenceConfig, IngestionConfig, sessionmaker[Session]]:
    reset_persistence_for_tests()
    reset_engine()
    cfg = PersistenceConfig(database_url="sqlite:///:memory:")
    engine = get_engine(cfg)
    Base.metadata.create_all(engine)
    iconfig = IngestionConfig(quarantine_dir=tmp_path / "quarantine")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield cfg, iconfig, factory
    reset_engine()


def test_ingest_sample_csv(
    ingest_env: tuple[PersistenceConfig, IngestionConfig, sessionmaker],
) -> None:
    pconfig, iconfig, factory = ingest_env

    report = ingest_csv(
        SAMPLE_CSV,
        persistence_config=pconfig,
        ingestion_config=iconfig,
        batch_size=2,
    )

    assert report.rows_read == 3
    assert report.created == 3
    assert report.already_existed == 0
    assert report.rejected == 0
    assert report.quarantine_path is None

    with factory() as session:
        enterprises = session.scalars(select(Enterprise)).all()
        assert len(enterprises) == 3
        for ent in enterprises:
            assert ent.seed_source == SeedSource.CSV
            assert ent.processing_state is not None
            assert ent.processing_state.state == ProcessingState.QUEUED_SCRAPE


def test_invalid_row_quarantine_no_insert(
    ingest_env: tuple[PersistenceConfig, IngestionConfig, sessionmaker],
    tmp_path: Path,
) -> None:
    pconfig, iconfig, _factory = ingest_env
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "enterprise_number\n0123456789\nnot-valid\n",
        encoding="utf-8",
    )

    report = ingest_csv(
        bad_csv,
        persistence_config=pconfig,
        ingestion_config=iconfig,
    )

    assert report.rows_read == 2
    assert report.created == 1
    assert report.rejected == 1
    assert report.quarantine_path is not None
    assert report.quarantine_path.exists()

    with _factory() as session:
        assert len(session.scalars(select(Enterprise)).all()) == 1


def test_double_ingest_idempotent(
    ingest_env: tuple[PersistenceConfig, IngestionConfig, sessionmaker],
) -> None:
    pconfig, iconfig, factory = ingest_env

    first = ingest_csv(
        SAMPLE_CSV,
        persistence_config=pconfig,
        ingestion_config=iconfig,
    )
    second = ingest_csv(
        SAMPLE_CSV,
        persistence_config=pconfig,
        ingestion_config=iconfig,
    )

    assert first.created == 3
    assert first.already_existed == 0
    assert second.created == 0
    assert second.already_existed == 3

    with factory() as session:
        assert len(session.scalars(select(Enterprise)).all()) == 3
