# MS-09 — Supervision & real-time monitoring dashboard

## Goal

Provide the subject’s **admin + monitoring** view: near real-time visibility into pipeline health and business flow.

## Minimum dashboard panels (from subject)

- enterprises currently scraping (in-flight)
- current pipeline stage per enterprise (or per work item)
- fully processed enterprises
- pending enterprises
- dynamically discovered enterprises (counts + recent list)
- scraping errors
- parsing errors
- validation errors
- proxy/IP failures
- global performance (throughput, latency, success rate)

## Scope options (pick one for speed)

- **Option A (fastest)**: Grafana + Prometheus + exporters (Airflow statsd/metrics; custom counters from services)
- **Option B**: Small web app (FastAPI + SSE) reading a `metrics` / `events` table populated by tasks
- **Option C**: Airflow UI + custom admin pages (only if course expects it)

## Out of scope

- Implementing scraping/parsing logic

## Task checklist (programming)

- [ ] **T09.1** Choose event/metrics storage and implement a minimal SDK used by `MS-02` and `MS-04`: `emit_event(type, payload)`
- [ ] **T09.2** Build dashboards/queries for each bullet above (placeholders allowed initially, but wired to real counters)
- [ ] **T09.3** Add RBAC/auth stub if exposed beyond localhost (even basic token)

## Definition of Done (DoD)

- When a scrape fails vs succeeds, the dashboard changes within a minute without manual DB queries.
- You can answer: “how many enterprises are waiting?” from the UI.

## Freeze outputs

- Event schema + dashboard JSON (if Grafana) or routes (if web app).
