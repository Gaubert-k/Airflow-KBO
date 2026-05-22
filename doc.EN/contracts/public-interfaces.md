# Public interfaces — cross-service contracts (draft to refine during MS-00)

This file is the **single negotiation surface** between microservices. Update it **only** during the owning milestone or via a documented **contract bump**.

## Identifiers

- **`enterprise_number`**: Belgian company number as **10 digits** string (normalize `BE` prefixes, dots, spaces).

## Processing states (suggested enum)

These are **platform states**, not legal KBO statuses:

- `NEW` — known, not yet scheduled for scraping
- `QUEUED_SCRAPE` — eligible for acquisition
- `SCRAPING` — acquisition in progress
- `RAW_STORED` — at least one validated raw document stored for the latest attempt
- `QUEUED_PARSE` — raw available for extraction
- `PARSING`
- `STRUCTURED` — structured load succeeded for current generation
- `FAILED_SCRAPE` / `FAILED_PARSE` / `FAILED_VALIDATE`

(You may split per document type; keep it explicit in `MS-05`.)

## HDFS layout (frozen in MS-03 v1)

- Root URI: `HDFS_RAW_ROOT` (default `hdfs://localhost:9000/raw/v1`)
- Object directory:
  - `raw/v1/source={kbo|moniteur|bnb|...}/enterprise_number={NNNNNNNNNN}/doc_type={...}/run_id={uuid}/`
  - `document.bin` (bytes) **or** `document.html` (name recorded in sidecar as `document_name`)
  - `metadata.json` (sidecar, `schema_version: 1`)
- Idempotency key for writes: `(enterprise_number, source, doc_type, run_id)`
- Dev stub: filesystem under `HDFS_LOCAL_ROOT` maps `hdfs://` paths (see `packages/storage/FREEZE.md`)

## Raw metadata sidecar (`metadata.json`)

Minimum fields (from subject):

- `scraped_at` (UTC ISO-8601)
- `source` (string)
- `download_status` (enum: `SUCCESS`, `FAILED`, `SKIPPED`, …)
- `http_status` (int)
- `proxy_or_ip` (string; redact secrets)
- `attempt_count` (int)
- `last_updated_at` (UTC ISO-8601; meaning: last time this metadata record was updated)

Recommended extra fields (engineering practicality):

- `content_type`
- `sha256` of raw bytes
- `url`
- `doc_type`
- `schema_version`

## Discovery provenance record

When `MS-06` enqueues a discovered enterprise:

- `source_enterprise_number`
- `discovered_enterprise_number`
- `reason` (machine-readable code + optional human text)
- `discovered_at`
- `discovery_generation` (monotonic id optional)

## Phase C tables (MS-07 / MS-08 / MS-09)

- `enterprise_lifecycle_history` — append-only business status snapshots
- `pipeline_events` — supervision events (`emit_event`)
- `analytics_postal_summary`, `analytics_state_summary`, `analytics_activity_rank`

## Metrics events (for `MS-09`)

Keep metrics **append-friendly** (DB table or Prometheus counters). Minimum counters/gauges:

- scrape attempts / successes / failures by `source`
- parse attempts / successes / failures
- proxy failures
- queue depth by state
- end-to-end latency histograms (optional)

## Airflow integration style

- DAG files only orchestrate; heavy logic lives in importable Python packages per `MS-xx`.
- Idempotency keys: `(enterprise_number, source, doc_type, run_id)` for raw writes.
