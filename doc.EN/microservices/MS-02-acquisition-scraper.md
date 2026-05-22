# MS-02 — Acquisition / scraping (download + validate + metadata; no parsing)

## Goal

For each `(enterprise_number, source, doc_type)` job, **download** public documents, **validate** that the response is acceptable, and **hand off bytes** to `MS-03` with mandatory metadata.

## Scope

- HTTP client with timeouts, retries, backoff
- Proxy support + rotation (subject lists external proxy directories; treat as **untrusted** inputs)
- Record metadata fields required by the subject:
  - scraped timestamp
  - source
  - download status
  - HTTP status
  - proxy/IP used
  - attempt count
  - last updated timestamp
- **Never store obvious error pages** as successful raw docs (coordinate exact heuristics with `MS-03`)

## Independent acquisition units

Treat each source separately (separate modules or strategies):

- KBO main enterprise page(s)
- Moniteur publications
- BNB / Centrale des bilans documents
- Statutes / powers / other related docs (as far as publicly accessible)

## Out of scope

- Business field extraction (`MS-04`)
- Database schema (`MS-05`) except lightweight “attempt logs” if you need them before DB exists (prefer metrics + sidecar first)

## Task checklist (programming)

- [ ] **T02.1** Define a `SourceAdapter` interface: `build_urls(enterprise_number) -> list[FetchJob]`
- [ ] **T02.2** Implement `fetch(job) -> FetchResult(bytes|None, http_status, headers, timing_ms)`
- [ ] **T02.3** Implement `validate_fetch(result) -> ValidationDecision(STORE|DROP|RETRY)` with explicit reasons
- [ ] **T02.4** Proxy pool loader + health checks; emit **proxy failure metrics** (`MS-09`)
- [ ] **T02.5** Integrate with `MS-03.put_raw_object` + metadata sidecar writer
- [ ] **T02.6** Update enterprise/document state via `MS-05` repositories (success/fail paths)

## Definition of Done (DoD)

- For at least **one** real public source (KBO page is the easiest first), you can scrape a known enterprise number in dev and store raw bytes on HDFS with metadata.
- HTTP 4xx/5xx never ends up labeled as `RAW_STORED` success.

## Freeze outputs

- Adapter interface + metadata schema + validation reason codes.

## Operational warning

Public sites change; keep HTML validation **narrow** (status codes + content-type + minimal fingerprints), not full DOM assertions, unless you version adapters per site revision.

## Implementation notes (2026-05-20, v2.1)

- **Statutes default:** Moniteur `list.pl` per enterprise (PDF: legal publications). Optional `NOTAIRE_STATUTES_URL` for a fixed notaire.be page (course add-on).
- **KBO validation:** do not treat field-level « Geen gegevens opgenomen in KBO » as a page error (`HTML_ERROR_MARKER` false positive fixed).
- **Powers:** no separate public KBO URL; representational data expected in `enterprise_detail` HTML + Moniteur (see `packages/acquisition/RESEARCH.md`).
