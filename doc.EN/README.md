# Airflow Group Project — Delivery Guide (English)

This folder turns **AIRFLOW_Group_project.pdf** into a **sequential, AI-friendly build plan**. Each block is a **bounded microservice** (clear inputs, outputs, and interfaces). After you **validate** a block, you treat its public contract as **frozen** and only fix regressions via adapters—not by rewriting the frozen module.

## Current progress (repo)

| MS | Status | Notes |
|----|--------|--------|
| MS-00 | Done | Airflow Docker, `00_hello` |
| MS-03 | Done | HDFS stub + `store_raw_bundle` |
| MS-05 | Done | PostgreSQL schema + states |
| MS-01 | Done | CSV ingest + `01_ingest_csv` (all enterprise CSVs, once) |
| MS-02 | Done | KBO / Moniteur / statutes / BNB adapters; validation fix v2.1 |
| **MS-10** | **Phase B+C done** | DAGs `00`–`08` (scrape, extract, discovery, lifecycle, analytics) |
| MS-04 | Done | `packages/extraction/`, DAG `04_extract_batch` |
| MS-06 | Done | `packages/discovery/`, DAG `05_discovery_fanout` |
| MS-07 | Done | `packages/lifecycle/`, DAG `06_lifecycle_refresh` (daily) |
| MS-08 | Done | `packages/analytics/`, DAG `07_analytics_refresh` (daily) |
| MS-09 | Done | `packages/monitoring/`, `packages/dashboard/` + `scripts/run-dashboard.sh` |

**Run order (operators):** `../airflow/dags/RUN_ORDER.md` (French, numbered `00`–`08`).

**French summary for professors:** `../README.md`, traceability matrix `../LIVRABLE.md`.

**Subject alignment:** `reference/project-brief.md`, `reference/requirements-traceability.md`.

## How to use this with an AI (recommended workflow)

1. Pick **exactly one** microservice file (e.g. `microservices/MS-02-acquisition-scraper.md`).
2. Paste the file content (or path) into the chat and say: *implement only MS-02; do not touch MS-01 or MS-00*.
3. Complete the **Definition of Done (DoD)** checklist in that file.
4. Run the **freeze ritual** in `workflow/freeze-policy.md` (tag commit, lock interface).
5. Move to the next microservice in `roadmap/execution-order.md`.

## Documents in this folder

| Path | Purpose |
|------|---------|
| `reference/project-brief.md` | English restatement of the assignment (traceable to the PDF). |
| `reference/requirements-traceability.md` | PDF requirements → owning microservice. |
| `roadmap/execution-order.md` | **Strict build order** and dependency graph. |
| `workflow/freeze-policy.md` | Rules for “validate then never rework unless contract changes”. |
| `contracts/public-interfaces.md` | Cross-service contracts (events, tables, paths, APIs). |
| `microservices/MS-*.md` | Per-service scope, tasks, DoD, and integration notes. |
| `microservices/INDEX.md` | Ordered list of MS files. |

## Important note on “microservices”

The subject describes **functional domains**, not a mandatory Kubernetes layout. Here, a **microservice** means a **module with a hard boundary**: you can still deploy it as libraries + Airflow operators, or later split into HTTP services if your course requires it. The value is **independent validation** and **stable interfaces**.

## Source of truth

The authoritative subject is: `../AIRFLOW_Group_project.pdf`.
