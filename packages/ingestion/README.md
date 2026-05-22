# MS-01 — Ingestion CSV & file d'attente

Charge des numéros d'entreprise belges depuis un CSV vers PostgreSQL (`enterprises` + état `QUEUED_SCRAPE`).

## API

```python
from packages.ingestion import IngestReport, ingest_csv

report = ingest_csv("data/seed/csv/sample_enterprises.csv")
print(report.created, report.already_existed)
```

## CLI

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
./scripts/db-migrate.sh
python -m packages.ingestion.cli ingest data/seed/csv/sample_enterprises.csv
python -m packages.ingestion.cli ingest data/input/csv/ton_fichier.csv --column enterprise_number --batch-size 5000
```

## Comportement

- Lecture en **flux** (compatible fichiers ~2 Go sous `data/input/csv/`)
- Délimiteur `,` ou `;` (auto), encodage UTF-8 avec repli latin-1
- Colonne entreprise : alias connus ou **première colonne**
- Normalisation : `packages.storage.paths.normalize_enterprise_number`
- Lignes invalides → `data/quarantine/` (horodaté + nom du fichier source)
- Idempotence : re-ingestion sans doublon (`created` / `already_existed`)

## Variables

| Variable | Rôle |
|----------|------|
| `DATABASE_URL` | PostgreSQL métier (MS-05) |
| `INGESTION_QUARANTINE_DIR` | Répertoire de quarantaine (défaut `{projet}/data/quarantine`) |

Contrat gelé : `FREEZE.md`.
