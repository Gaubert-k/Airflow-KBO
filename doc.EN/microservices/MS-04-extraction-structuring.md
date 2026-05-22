# MS-04 — Extraction & structuring (HTML in → structured facts out)

## Goal

Read validated raw HTML from `MS-03`, extract the structured fields required by the subject, and output **schema-versioned** structured records for loading into `MS-05`.

## Scope

- Parsers per `source` / `doc_type` (separate modules)
- Robustness: tolerant parsing, explicit “partial extraction” flags
- Versioning: `extractor_version` + `schema_version` on outputs

## Subject extraction targets (minimum checklist)

- General company information
- Managers / representatives
- Entrepreneurial capacities / qualities / authorizations (as present in sources)
- VAT activities
- Financial data (as available)
- Links between entities (critical for `MS-06`)
- Establishments
- Publications and associated documents metadata

## Out of scope

- Scraping (`MS-02`)
- Analytics aggregations (`MS-08`)

## Task checklist (programming)

- [x] **T04.1** Models + `schema_version` on snapshots (`packages/extraction/models.py`)
- [x] **T04.2** `parse_batch` / KBO parser (`packages/extraction/parsers/kbo.py`) — **partial** vs full PDF field list
- [ ] **T04.3** Golden-file unit tests per source (fixtures not exhaustive)
- [x] **T04.4** Discovery candidates inline + `MS-06` fan-out DAG
- [x] **T04.5** Persistence via `enterprise_snapshots` + state transitions (`FAILED_PARSE`)

## Definition of Done (DoD)

- [x] At least one doc type produces non-empty structured records (KBO `enterprise_detail` on real/scraped HTML).
- [x] Parse failures are classified and observable (`FAILED_PARSE`).
- [ ] Full PDF extraction checklist (managers, VAT, financials, establishments, …) for all sources.

## Freeze outputs

- Output schema version + extractor interface.
