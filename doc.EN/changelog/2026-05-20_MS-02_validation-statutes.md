# 2026-05-20 — MS-02 validation v2.1 + statutes default

## MS-02 (non-breaking adapter behaviour)

- **KBO:** `validate_fetch` no longer drops pages containing « Geen gegevens opgenomen in KBO » (field placeholder). Page-level markers only (`geen onderneming`, etc.).
- **Statutes:** default URL = Moniteur `list.pl` per BCE (PDF). `NOTAIRE_STATUTES_URL` optional for notaire.be.

## MS-10 (docs only)

- Documented phase B DAG ids (`01`–`03`, `02_scrape_by_source`) in `MS-10-airflow-orchestration.md`, `doc.EN/README.md`, `INDEX.md`.

## Operator action

- After pull: re-run `02_scrape_batch` or `02_scrape_by_source` — KBO success rate should improve.
- Leave `NOTAIRE_STATUTES_URL` unset unless the professor requires notaire.be explicitly.
