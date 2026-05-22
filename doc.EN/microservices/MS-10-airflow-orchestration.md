# MS-10 — Airflow orchestration (thin DAGs, dependencies, scheduling)

## Goal

Express the subject’s requirement: **automatic pipelines**, **dependencies**, and **regular execution**—without burying business logic in DAG files.

## Scope (implemented — phase B+C)

| `dag_id` | File | Role |
|----------|------|------|
| `00_hello` | `hello.py` | MS-00 smoke |
| `01_ingest_csv` | `belgian_ingest_csv.py` | **Once**: all enterprise CSVs |
| `02_scrape_batch` | `belgian_scrape_batch.py` | Claim → scrape (MS-02) |
| `02_scrape_by_source` | `belgian_scrape_by_source.py` | 4 parallel probe tasks |
| `03_pipeline_dev` | `belgian_pipeline_dev.py` | Scrape-only dev |
| `04_extract_batch` | `belgian_extract_stub.py` | MS-04 parse batch |
| `05_discovery_fanout` | `belgian_discovery_stub.py` | MS-06 fan-out |
| `06_lifecycle_refresh` | `belgian_lifecycle_stub.py` | MS-07 daily rescrape selection |
| `07_analytics_refresh` | `belgian_analytics_stub.py` | MS-08 daily aggregates |
| `08_full_pipeline` | `belgian_full_pipeline.py` | `scrape >> extract` |

Glue package: `packages/orchestration/` (`run_ingest_all_csv`, `run_scrape_batch`, `run_scrape_single_source` / `run_source_probe`).

Operational order: `airflow/dags/RUN_ORDER.md`.

Pools: `ingest_pool` (1), `scrape_pool` (2) — create in Airflow UI/CLI before first run.

## Out of scope (remaining gaps vs PDF)

- Exhaustive field extraction for every source (`MS-04` parsers still MVP)
- Production Hadoop cluster (MS-03 uses local filesystem stub)
- Mass scrape of full national CSV at production rate

## Task checklist (programming)

- [x] **T10.1** Callable entrypoints: `packages/orchestration` → MS-01 … MS-08
- [x] **T10.2** Phase B: ingest (once) then scrape; phase C: extract, discovery, lifecycle, analytics
- [x] **T10.3** Pools `ingest_pool` / `scrape_pool` on operators
- [x] **T10.4** `ms10_on_failure_callback` (structured log + metrics snapshot)
- [x] **T10.5** Idempotence documented (`FREEZE.md`, `ACQUISITION_WORKER_ID=airflow-{run_id}`)

## Definition of Done (DoD) — phase B

- [x] Docker Compose runs Airflow 3.2; `01` + scrape DAGs parse without import errors
- [x] Happy path: seed CSV → `01_ingest_csv` → `03_pipeline_dev` or `02_scrape_by_source` on small `limit`
- [x] DAGs remain thin (no `packages.ingestion` / `packages.acquisition` at parse time)

## Freeze outputs

- DAG ids, pool names, `packages/orchestration/FREEZE.md`, `airflow/dags/FREEZE.md`

## Notes

Phase C DAGs use filenames `belgian_*_stub.py` for history only; operational `dag_id` values are `04_extract_batch` … `08_full_pipeline` (no `stub` tag). See `airflow/dags/FREEZE.md`.
