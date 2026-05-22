# MS-00 — Platform foundation (runtime, repo layout, standards)

## Goal

Create a **stable engineering baseline** so every later microservice can be implemented without thrashing tooling.

## Scope

- Repository layout (suggested):
  - `airflow/dags/` — only orchestration (`MS-10`)
  - `packages/` — importable Python modules per domain (`acquisition`, `extraction`, …)
  - `infra/` — compose / helm / scripts (as required by course)
- Shared tooling: formatter/linter (optional), `Makefile` or `taskfile` (optional)
- Configuration: `.env.example` (no secrets), environment variable naming convention
- Logging: structured logs (JSON) recommended
- **Local dev story**: how to run Airflow + dependencies on one machine

## Out of scope

- Business parsing rules (`MS-04`)
- Proxy sourcing specifics beyond placeholders (`MS-02`)

## Task checklist (programming)

- [ ] **T00.1** Choose dependency packaging (`pip-tools`, `uv`, `poetry`) and pin versions.
- [ ] **T00.2** Add `README_DEV.md` (French or English—your choice) with exact startup commands.
- [ ] **T00.3** Add baseline CI script: `lint`, `unit tests`, `import smoke` (even if empty initially).
- [ ] **T00.4** Define Python import boundaries: DAGs must not import heavy scraping libs globally at parse time (Airflow best practice).
- [ ] **T00.5** Add `contracts/public-interfaces.md` maintenance rule to contributor docs.

## Definition of Done (DoD)

- A new developer can start Airflow and run an empty “hello” DAG.
- Environment variables are documented in `.env.example`.
- The repo has a clear place for **each** `MS-xx` implementation to land.

## Freeze outputs

- Folder conventions + config keys + logging format.
