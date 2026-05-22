"""Registre événementiel — MS-05 s'abonne via register_raw_document_listener."""

from __future__ import annotations

import logging
from collections.abc import Callable

from packages.storage.models import RawDocumentStoredEvent

logger = logging.getLogger(__name__)

_listeners: list[Callable[[RawDocumentStoredEvent], None]] = []


def register_raw_document_listener(
    callback: Callable[[RawDocumentStoredEvent], None],
) -> None:
    _listeners.append(callback)


def clear_raw_document_listeners() -> None:
    """Réservé aux tests."""
    _listeners.clear()


def on_raw_document_stored(event: RawDocumentStoredEvent) -> None:
    for listener in _listeners:
        listener(event)
    logger.debug(
        "Persistance PostgreSQL — BCE %s, source=%s, type=%s, %d octets (hdfs=%s)",
        event.enterprise_number,
        event.source,
        event.doc_type,
        event.size_bytes,
        event.hdfs_dir,
    )
