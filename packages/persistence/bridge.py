"""Pont MS-03 → MS-05 (écouteurs raw document)."""

from __future__ import annotations

import logging

from packages.persistence.repositories import insert_raw_document_from_event
from packages.persistence.session import session_scope
from packages.storage.models import RawDocumentStoredEvent
from packages.storage.registry import register_raw_document_listener

logger = logging.getLogger(__name__)

_wired = False


def _on_raw_stored(event: RawDocumentStoredEvent) -> None:
    try:
        with session_scope() as session:
            insert_raw_document_from_event(session, event)
    except Exception:
        logger.exception(
            "failed to persist raw document registry row",
            extra={"enterprise_number": event.enterprise_number, "run_id": event.run_id},
        )
        raise


def wire_storage_events() -> None:
    """Enregistre l'écouteur MS-03 (idempotent)."""
    global _wired
    if _wired:
        return
    register_raw_document_listener(_on_raw_stored)
    _wired = True


def reset_storage_bridge() -> None:
    """Tests uniquement."""
    global _wired
    _wired = False
