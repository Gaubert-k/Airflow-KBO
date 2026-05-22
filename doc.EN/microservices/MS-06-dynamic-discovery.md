# MS-06 — Dynamic discovery (graph expansion + provenance + enqueue)

## Goal

When structured extraction finds **links between entities**, automatically:

- enqueue newly discovered enterprise numbers into the processing queue
- persist provenance: **source enterprise**, **discovered enterprise**, **reason**
- distinguish **CSV seed** vs **DISCOVERED** enterprises (`MS-05`)

## Scope

- Candidate extraction from `MS-04` output (preferred) *or* re-scan stored graphs (avoid duplication)
- Deduplication: if enterprise already exists, still optionally record a new discovery edge if meaningful
- “Reason codes” stable enough for analytics (`SHARED_ADDRESS`, `SUBSIDIARY_LINK`, `ROLE_IN_STATUTES`, …—adapt to reality)

## Out of scope

- Scraping implementation (`MS-02`)
- Full graph analytics UI (`MS-09` may visualize later)

## Task checklist (programming)

- [ ] **T06.1** Implement `record_discovery(source, discovered, reason, evidence_ref)`
- [ ] **T06.2** Implement `enqueue_if_new(discovered) -> EnqueueDecision`
- [ ] **T06.3** Ensure idempotency: repeated parses do not create infinite duplicate queue rows
- [ ] **T06.4** Airflow hook: after successful parse task, run discovery transaction in same business flow (or separate task with idempotency key)

## Definition of Done (DoD)

- A controlled fixture containing a second enterprise number produces a new queued enterprise + provenance row.

## Freeze outputs

- Provenance record shape + reason code taxonomy (extensible).
