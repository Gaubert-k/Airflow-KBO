# Microservice index (build order)

Read `../roadmap/execution-order.md` for the full graph.

| Order | ID | File | Phase B status |
|---:|---|---|----------------|
| 1 | MS-00 | `MS-00-platform-foundation.md` | Done |
| 2 | MS-03 | `MS-03-hdfs-raw-storage.md` | Done |
| 3 | MS-05 | `MS-05-database-persistence.md` | Done |
| 4 | MS-01 | `MS-01-csv-ingestion-queue.md` | Done |
| 5 | MS-02 | `MS-02-acquisition-scraper.md` | Done (validation v2.1) |
| 6 | **MS-10** | `MS-10-airflow-orchestration.md` | **Done (phase B+C)** |
| 7 | MS-04 | `MS-04-extraction-structuring.md` | Done — KBO + Moniteur parsers, `04_extract_batch` |
| 8 | MS-06 | `MS-06-dynamic-discovery.md` | Done — `05_discovery_fanout` |
| 9 | MS-07 | `MS-07-lifecycle-freshness.md` | Done — `06_lifecycle_refresh` |
| 10 | MS-08 | `MS-08-analytics.md` | Done — `07_analytics_refresh` |
| 11 | MS-09 | `MS-09-monitoring-dashboard.md` | Done — FastAPI `:8090` |

**Airflow runbook:** `../../airflow/dags/RUN_ORDER.md`
