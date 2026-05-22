# MS-05 — Persistence (database schema, migrations, ownership)

## Goal

Provide a **durable system of record** for enterprises, raw document registry, structured facts, discovery provenance, and historical lifecycle snapshots.

## Scope

- DB choice: PostgreSQL is a common “adapted DB”; if course mandates else, keep the same **logical model**.
- Migrations (Alembic/Flyway/etc.)
- Table ownership boundaries (who writes what)

## Suggested logical tables (minimum viable → expand)

**Queue / identity**

- `enterprises` — `enterprise_number` PK, `seed_source` (`CSV` vs `DISCOVERED`), created_at
- `enterprise_processing_state` — current state enum + timestamps + lock owner (optional)

**Raw**

- `raw_documents` — links to hdfs path, hash, doc_type, source, scraped_at, http_status, attempts, status

**Structured (versioned)**

- `enterprise_snapshots` — append-only rows for “what we believed at time T” (supports never-delete closed companies)
- normalized subtables as needed (people, establishments, VAT activities, financial statements) — can arrive after MVP

**Discovery**

- `enterprise_discoveries` — source, discovered, reason, discovered_at

## Out of scope

- Airflow DAG definitions (`MS-10`)
- Scraping (`MS-02`)

## Task checklist (programming)

- [x] **T05.1** Implement migrations creating MVP tables listed above.
- [x] **T05.2** Implement repositories:
  - `upsert_enterprise(number, seed_source)`
  - `transition_state(number, from, to)` with optimistic locking or row locks
  - `insert_raw_document_record(...)`
  - `append_snapshot(...)` (no hard delete for “closed”)
- [x] **T05.3** Add indexes for queue polling (`WHERE state = ... ORDER BY ... FOR UPDATE SKIP LOCKED` pattern optional)
- [x] **T05.4** Document which MS writes each table (`ownership matrix` in module README)

## Definition of Done (DoD)

- You can represent: seed enterprise, discovered enterprise + provenance, raw doc registry row, append-only snapshot.
- Schema changes go through migrations only.

## Freeze outputs

- Table names + enums + writer ownership.
