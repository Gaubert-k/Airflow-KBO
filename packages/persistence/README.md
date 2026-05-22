# MS-05 — Persistance PostgreSQL

Schéma MVP, migrations Alembic et repositories. Contrat gelé : `FREEZE.md`.

## Variables

| Variable | Défaut | Rôle |
|----------|--------|------|
| `DATABASE_URL` | `postgresql://app:app@localhost:5432/belgian_companies` | Connexion base métier |

Avec Docker (`infra/docker-compose.yml`), la base `belgian_companies` est créée au premier démarrage Postgres (`infra/postgres/init-app-db.sql`).

## Migrations

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
chmod +x scripts/db-migrate.sh
./scripts/db-migrate.sh
```

## Matrice de propriété (qui écrit quoi)

| Table | Propriétaire écriture | Lecteurs |
|-------|----------------------|----------|
| `enterprises` | **MS-01** (seed CSV), **MS-06** (DISCOVERED via `record_discovery`) | MS-02, MS-04, MS-07, MS-09 |
| `enterprise_processing_state` | **MS-01** (enqueue), **MS-02** (scrape), **MS-04** (parse), **MS-07** (lifecycle) | MS-09, MS-10 |
| `raw_documents` | **MS-05** (écouteur MS-03) ou **MS-02** direct | MS-04, MS-09 |
| `enterprise_snapshots` | **MS-04** / loaders (`append_snapshot`) | MS-07, MS-08, MS-09 |
| `enterprise_discoveries` | **MS-06** (`record_discovery`) | MS-01, MS-09 |

## API publique

```python
from packages.persistence import (
    ProcessingState,
    SeedSource,
    append_snapshot,
    insert_raw_document_record,
    record_discovery,
    transition_state,
    upsert_enterprise,
)
from packages.persistence.bridge import wire_storage_events

wire_storage_events()  # optionnel : persiste raw_documents à chaque store MS-03
```

## Pont MS-03

`wire_storage_events()` enregistre un listener sur `register_raw_document_listener` et appelle `insert_raw_document_from_event`. L’entreprise doit déjà exister (MS-01 / MS-06).
