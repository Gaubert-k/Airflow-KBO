# MS-07 — Lifecycle management (freshness, rescrape, status transitions, no hard deletes)

## Goal

Keep data current over time and comply with:

- periodic revalidation / rescrape (subject example: **at least every ~14 days**)
- status changes: inactive, struck off, merged, legal form changes
- **never delete** closed/struck-off companies; retain historical documents and snapshots

## Scope

- Scheduler queries: select enterprises whose `last_successful_scrape_at` (or equivalent) is older than policy
- “Due work” emission: mark `QUEUED_SCRAPE` / create a work item table (choose one)
- Legal/business status extraction inputs come from structured snapshots (`MS-04`/`MS-05`), but lifecycle owns **interpretation policy** (version it)

## Out of scope

- Raw download mechanics (`MS-02`)
- Parsing rules (`MS-04`)

## Task checklist (programming)

- [ ] **T07.1** Define freshness policy config: `max_age_days = 14` (example), per-source overrides optional
- [ ] **T07.2** Implement `select_due_enterprises(limit) -> list[enterprise_number]`
- [ ] **T07.3** Implement state machine transitions for business statuses (`ACTIVE`, `INACTIVE`, `STRUCK_OFF`, `MERGED`, …) with **append-only history**
- [ ] **T07.4** Implement “merged into” / “successor” references without deleting old keys
- [ ] **T07.5** Wire into `MS-10` as a scheduled DAG

## Definition of Done (DoD)

- A synthetic enterprise with an old timestamp becomes eligible for rescrape automatically.
- Marking an enterprise as closed does **not** remove historical rows from DB/HDFS registry.

## Freeze outputs

- Freshness policy keys + lifecycle history table schema.
