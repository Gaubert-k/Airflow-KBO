# Freeze policy — “validate, then do not touch”

This project is large; the anti-chaos strategy is **contract-first** delivery.

## What “frozen” means

After a microservice reaches **DoD = done**, you freeze:

1. **Public interfaces** it exposes (function signatures, CLI entrypoints, REST routes, DB tables it owns, Kafka topics, HDFS paths—whatever you chose).
2. **Data contracts** (JSON schema version, column names, enum values for statuses).
3. **Behavioral guarantees** documented in its `MS-*.md` file (e.g., “never persists HTTP 404 body as raw doc”).

## What is allowed after freeze

- **Bugfixes** that preserve the contract (same inputs → same outputs).
- **Performance** improvements without observable contract changes.
- **Security** patches.
- **Adapter layers** when upstream changes (website HTML changes): prefer updating parsers behind a stable `extract_v3()` boundary, not rewriting the whole acquisition service.

## What is not allowed after freeze (without a formal “contract bump”)

- Renaming DB columns/tables owned by a frozen service.
- Changing HDFS layout for raw objects without versioning (`/raw/v1/...` vs `/raw/v2/...`).
- Silently changing meaning of statuses (`SCRAPED`, `PARSED`, …).

## Contract bump procedure (intentional rework)

1. Increment a **schema version** (`schema_version`, `contract_version`).
2. Write a short migration note: `doc.EN/changelog/YYYY-MM-DD_contract-bump_MS-xx.md`
3. Update `contracts/public-interfaces.md` first, then adjust exactly one owner service.

## Minimal “freeze ritual” (git-light)

If you use git, after DoD:

- Create a tag like `freeze/MS-02-v1`
- Optionally add a `FREEZE.md` in that module folder pointing to the tag

If you do **not** use git, export a zip of the module folder and store it as an artifact.

## Definition conflicts

If the PDF and your frozen contract disagree, **the PDF wins**, but you still apply a **contract bump** rather than stealth edits.
