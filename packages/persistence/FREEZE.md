# FREEZE — MS-05 Database persistence v1

Tag suggéré : `freeze/MS-05-v1`

## Tables gelées

- `enterprises`
- `enterprise_processing_state`
- `raw_documents`
- `enterprise_snapshots` (append-only)
- `enterprise_discoveries`

## Énumérations gelées

- `seed_source` : `CSV`, `DISCOVERED`
- `processing_state` : voir `doc.EN/contracts/public-interfaces.md`
- `raw_document_status` : `STORED`, `FAILED`, `SKIPPED`

## Fonctions / repositories gelés

- `upsert_enterprise(session, number, seed_source)`
- `transition_state(session, number, from_state, to_state, lock_owner=..., lock_until=...)`
- `claim_enterprises_for_scrape(session, limit=..., worker_id=..., lock_seconds=...)`
- `insert_raw_document_record(...)` — clé idempotence `(enterprise_number, source, doc_type, run_id)`
- `append_snapshot(session, number, payload, schema_version=...)`
- `record_discovery(session, source_enterprise_number, discovered_enterprise_number, reason, ...)`

## Événements

- Consomme `RawDocumentStoredEvent` (MS-03) via `wire_storage_events()`.

## Bump de contrat

Toute modification de colonne / enum → `doc.EN/changelog/` + mise à jour `public-interfaces.md` avant code.
