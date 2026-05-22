# MS-01 — Contrat gelé (v1)

Tag suggéré : `freeze/MS-01-v1`

## API publique (Python)

- `ingest_csv(path, *, column=None, batch_size=5000) -> IngestReport`
- `IngestReport` : `rows_read`, `created`, `already_existed`, `rejected`, `quarantine_path`, `source_file`, `duration_seconds`

## CLI

```bash
python -m packages.ingestion.cli ingest <path.csv> [--column NAME] [--batch-size N]
```

## Normalisation

Réutilise **`normalize_enterprise_number`** de `packages.storage.paths` (10 chiffres, sans préfixe BE ni ponctuation).

## Persistance (MS-05 gelé)

- `upsert_enterprise(..., SeedSource.CSV, initial_state=ProcessingState.QUEUED_SCRAPE)`
- Pas de modification du schéma MS-05

## Quarantaine

Fichiers sous `data/quarantine/` (ou `INGESTION_QUARANTINE_DIR`) :
`{timestamp}_{source_basename}.quarantine.csv` avec colonnes `line_number`, `raw_value`, `reason`, `source_file`.

## Bump de contrat

Toute évolution documentée dans `doc.EN/contracts/public-interfaces.md` + tag `freeze/MS-01-v2`.
