# MS-01 — CSV ingestion & work queue (enterprise intake)

## Goal

Read **one or more CSV files** containing Belgian enterprise numbers and populate the processing queue without duplicating chaos.

## CSV file locations (repo layout)

| Path | Git | Purpose |
|------|-----|---------|
| `data/input/csv/` | **ignored** | Professor init files (~2 GB total) — copy here |
| `data/seed/csv/` | tracked | Small samples (`sample_enterprises.csv`) for dev/CI |
| `data/quarantine/` | ignored | Invalid rows rejected at ingest |

See **`data/README.md`** (French) for **step 1** workflow before running `ingest_csv`.

## Scope

- CSV parsing (delimiter detection optional), encoding handling
- Normalize enterprise numbers to **10-digit** canonical form
- Deduplicate within batch and against DB
- Mark enterprises as `seed_source = CSV` (distinct from discovered)

## Out of scope

- Downloading HTML (`MS-02`)
- Parsing HTML (`MS-04`)

## Task checklist (programming)

- [ ] **T01.1** CLI or Airflow task: `ingest_csv(path) -> IngestReport`
- [ ] **T01.2** Validation rules: reject invalid numbers, log bad rows to a quarantine file/table
- [ ] **T01.3** Transactional batch insert into `enterprises` + initial state `NEW` or `QUEUED_SCRAPE` (pick one policy)
- [ ] **T01.4** Idempotency: re-running the same CSV should not create duplicates

## Definition of Done (DoD)

- Given a sample CSV, enterprises appear in DB exactly once and are schedulable.
- Invalid rows never silently become “valid enterprises”.

## Integration notes

- `MS-06` inserts enterprises with `seed_source = DISCOVERED` via the same repository APIs.

## Freeze outputs

- Canonical normalization function + ingest report format.
