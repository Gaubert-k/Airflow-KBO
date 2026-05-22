"""Session SQLAlchemy — engine singleton."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from packages.persistence.config import PersistenceConfig, get_persistence_config

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(config: PersistenceConfig | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is None:
        cfg = config or get_persistence_config()
        _engine = create_engine(cfg.database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_session_factory(config: PersistenceConfig | None = None) -> sessionmaker[Session]:
    get_engine(config)
    assert _session_factory is not None
    return _session_factory


def reset_engine() -> None:
    """Réinitialise le singleton (tests uniquement)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope(config: PersistenceConfig | None = None) -> Generator[Session, None, None]:
    factory = get_session_factory(config)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
