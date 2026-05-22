# MS-10 — Contrat gelé (v1, phase B+C)

Tag suggéré : `freeze/MS-10-v1`

## Entrées orchestration (`packages/orchestration/`)

| Fonction | Délègue à | Retour |
|----------|-----------|--------|
| `run_ingest_csv(csv_path, *, column=None, batch_size=5000)` | `packages.ingestion.ingest_csv` | `dict` (champs `IngestReport`) |
| `run_ingest_all_csv(csv_dirs=None, …)` | boucle `ingest_csv` sur CSV entreprise | `dict` agrégé (`files`, totaux) |
| `run_scrape_batch(*, limit=10, sources=None, wire_bridge=True)` | `packages.acquisition.worker.scrape_batch` | `dict` (champs `ScrapeReport`) |
| `run_parse_batch(*, limit=10)` | `packages.extraction.worker.parse_batch` | `dict` |
| `run_discovery_fanout(*, hours=48, limit=50)` | `packages.discovery` | `dict` |
| `run_lifecycle_tick(*, limit=50)` | `packages.lifecycle` | `dict` |
| `run_analytics_refresh(*, run_id=None)` | `packages.analytics` | `dict` |

Les modules **MS-01** … **MS-08** ne sont **pas** modifiés par MS-10 (seulement appelés).

## DAGs (`airflow/dags/`)

| `dag_id` | Fichier | Phase | Pool |
|----------|---------|-------|------|
| `01_ingest_csv` | `belgian_ingest_csv.py` | B | `ingest_pool` |
| `02_scrape_batch` | `belgian_scrape_batch.py` | B | `scrape_pool` |
| `02_scrape_by_source` | `belgian_scrape_by_source.py` | B | `scrape_pool` |
| `03_pipeline_dev` | `belgian_pipeline_dev.py` | B | `scrape_pool` |
| `04_extract_batch` | `belgian_extract_stub.py` | C | `scrape_pool` |
| `05_discovery_fanout` | `belgian_discovery_stub.py` | C | — |
| `06_lifecycle_refresh` | `belgian_lifecycle_stub.py` | C | — |
| `07_analytics_refresh` | `belgian_analytics_stub.py` | C | — |
| `08_full_pipeline` | `belgian_full_pipeline.py` | C | `scrape_pool` (`scrape >> extract`) |

`schedule=None` pour les DAGs manuels ; `06` et `07` sont planifiés quotidiennement.

### Règle d'import (MS-00)

- Parse-time DAG : imports Airflow légers uniquement.
- Pas d'import `packages.ingestion` / `packages.acquisition` au niveau module des DAGs phase B.
- Logique métier : callables → `packages.orchestration.*`.

## Pools Airflow

| Pool | Slots | Usage |
|------|-------|--------|
| `ingest_pool` | 1 | Tâche `ingest` |
| `scrape_pool` | 2 | Tâches `scrape` / `extract` |

Création manuelle ou UI : Admin → Pools.

## Chemins conteneur (Docker)

| Rôle | Chemin |
|------|--------|
| CSV seed | `/opt/airflow/data/seed/csv/sample_enterprises.csv` |
| CSV volumineux | `/opt/airflow/data/input/csv/<fichier>.csv` |
| Proxies | `/opt/airflow/data/proxies/proxies.txt` (défaut MS-02) |

## Idempotence (T10.5)

- **Ingest** : ré-exécuter le même CSV est idempotent côté DB (`already_existed`).
- **Scrape** : `ACQUISITION_WORKER_ID=airflow-{run_id}` ; chaque artefact HDFS reçoit un nouveau `run_id` (MS-03).

## Bump de contrat

`doc.EN/contracts/public-interfaces.md` + tag `freeze/MS-10-v2`.
