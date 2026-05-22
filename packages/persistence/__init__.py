"""MS-05 — Persistance PostgreSQL (schéma, migrations, repositories)."""

from packages.persistence.enums import ProcessingState, RawDocumentStatus, SeedSource
from packages.persistence.exceptions import (
    EnterpriseNotFoundError,
    PersistenceError,
    StateTransitionError,
)
from packages.persistence.repositories import (
    append_snapshot,
    claim_enterprises_for_parse,
    claim_enterprises_for_scrape,
    insert_raw_document_from_event,
    insert_raw_document_record,
    record_discovery,
    transition_state,
    upsert_enterprise,
)

__all__ = [
    "EnterpriseNotFoundError",
    "PersistenceError",
    "ProcessingState",
    "RawDocumentStatus",
    "SeedSource",
    "StateTransitionError",
    "append_snapshot",
    "claim_enterprises_for_parse",
    "claim_enterprises_for_scrape",
    "insert_raw_document_from_event",
    "insert_raw_document_record",
    "record_discovery",
    "transition_state",
    "upsert_enterprise",
]
