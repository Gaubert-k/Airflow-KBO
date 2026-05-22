# MS-10 — DAGs Airflow (gel phase B+C)

Tag : `freeze/MS-10-v1`

Contrat détaillé : `packages/orchestration/FREEZE.md`

## Fichiers DAG

| # | Fichier | `dag_id` | Phase |
|---|---------|----------|-------|
| 00 | `hello.py` | `00_hello` | A |
| 01 | `belgian_ingest_csv.py` | `01_ingest_csv` | B |
| 02 | `belgian_scrape_batch.py` | `02_scrape_batch` | B |
| 02b | `belgian_scrape_by_source.py` | `02_scrape_by_source` | B |
| 03 | `belgian_pipeline_dev.py` | `03_pipeline_dev` | B |
| 04 | `belgian_extract_stub.py` | `04_extract_batch` | C |
| 05 | `belgian_discovery_stub.py` | `05_discovery_fanout` | C |
| 06 | `belgian_lifecycle_stub.py` | `06_lifecycle_refresh` | C |
| 07 | `belgian_analytics_stub.py` | `07_analytics_refresh` | C |
| 08 | `belgian_full_pipeline.py` | `08_full_pipeline` | C |

> Les fichiers `*_stub.py` sont des noms historiques ; les `dag_id` opérationnels sont `04_*` … `08_*` (plus de tag `stub`).

Ordre d’exécution : `airflow/dags/RUN_ORDER.md`

## Pools (à créer dans Airflow)

- `ingest_pool` — 1 slot
- `scrape_pool` — 2 slots (prepare / finalize / batch / extract)
- `scrape_parallel_pool` — **4 slots** (branches `scrape_kbo` … `scrape_bnb` en même temps)
