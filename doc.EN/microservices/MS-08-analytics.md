# MS-08 — Analytics & business exploitation (periodic aggregates)

## Goal

Automatically and periodically produce analytical outputs listed in the subject:

- lists of enterprises by postal code
- groupings by activity
- financial rankings (as data allows)
- evolution statistics
- open/closed indicators
- temporal analyses

## Scope

- SQL-based transformations (preferred if using Postgres) **or** Spark jobs (only if course requires distributed compute)
- Materialized tables/views refreshed on a schedule (`MS-10`)

## Out of scope

- Real-time operational dashboard (`MS-09`) — analytics may feed it, but should not be mixed concerns

## Task checklist (programming)

- [ ] **T08.1** Define `analytics_refresh(run_id) -> RefreshReport`
- [ ] **T08.2** Implement MVP aggregates that work even with partial data (NULL-safe)
- [ ] **T08.3** Add data quality guards: if upstream freshness is bad, surface “stale analytics” flag
- [ ] **T08.4** Document each metric: definition, numerator/denominator, time window

## Definition of Done (DoD)

- Scheduled run produces at least 3 distinct analytical artifacts persisted as tables or files (teacher-visible).

## Freeze outputs

- Metric definitions + table names + refresh cadence.
