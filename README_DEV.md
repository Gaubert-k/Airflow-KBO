# Guide développeur — MS-00 (fondations)

> **Guide utilisateur (FR)** : [`GUIDE.md`](../GUIDE.md) · **Vue livrable** : [`README.md`](../README.md) · [`LIVRABLE.md`](../LIVRABLE.md) (matrice PDF).

Ce dépôt organise le travail par microservices (`MS-xx`). **MS-00** pose l’ossature : layout, dépendances figées, Airflow local, DAG `hello`.

## Structure du dépôt

| Dossier | Rôle |
|---------|------|
| `airflow/dags/` | **Uniquement** les DAGs Airflow (orchestration fine, `MS-10`) |
| `packages/` | Code Python importable (`acquisition`, `extraction`, … à venir) |
| `infra/` | Docker Compose et scripts de démarrage |
| `doc.EN/` | Spécifications microservices |
| `doc.EN/contracts/public-interfaces.md` | Contrats inter-services — **ne modifier qu’avec bump documenté** |

### Règle d’import (Airflow)

- **Au parse-time du DAG** : imports Airflow légers uniquement.
- **Dans les callables de tasks** : imports métier (`packages.*`, scraping, etc.).

Voir `airflow/dags/hello.py` pour l’exemple.

## Prérequis

- Docker et Docker Compose v2
- Python 3.11 (optionnel, pour lint/tests locaux)

## Démarrage Airflow (recommandé — Docker)

```bash
# 1. Variables d’environnement
cp /home/guillaume/Bureau/Airflow\ TP/.env.example /home/guillaume/Bureau/Airflow\ TP/infra/.env
# Ajuster AIRFLOW_PROJ_DIR / chemins si besoin

# 2. Lancer la stack
chmod +x /home/guillaume/Bureau/Airflow\ TP/infra/scripts/*.sh
/home/guillaume/Bureau/Airflow\ TP/infra/scripts/start.sh

# Ou manuellement :
cd /home/guillaume/Bureau/Airflow\ TP/infra
export AIRFLOW_UID=$(id -u)
docker compose up -d
```

- **UI** : http://localhost:8080  
- **Identifiants par défaut** : `airflow` / `airflow` (voir `infra/.env`)

### Vérifier le DAG `hello`

```bash
cd /home/guillaume/Bureau/Airflow\ TP/infra
docker compose exec airflow-scheduler airflow dags list | grep hello
docker compose exec airflow-scheduler airflow dags test hello 2025-01-01
```

Déclencher une run manuelle dans l’UI : DAG `hello` → Trigger.

### Arrêt

```bash
/home/guillaume/Bureau/Airflow\ TP/infra/scripts/stop.sh
```

## Dépendances Python (versions figées)

| Fichier | Usage |
|---------|--------|
| `requirements.txt` | Runtime (aligné image `apache/airflow:3.2.1-python3.11`) |
| `requirements-dev.txt` | `ruff`, `pytest` (CI locale ; Airflow via Docker uniquement) |
| `pyproject.toml` | Métadonnées projet et config `ruff` / `pytest` |

Installation locale (hors Docker) :

```bash
cd /home/guillaume/Bureau/Airflow\ TP
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## CI locale (MS-00 T00.3)

```bash
chmod +x /home/guillaume/Bureau/Airflow\ TP/scripts/ci.sh
/home/guillaume/Bureau/Airflow\ TP/scripts/ci.sh
```

## Où implémenter les prochains MS

| MS | Emplacement prévu |
|----|-------------------|
| MS-01 CSV / queue | `packages/ingestion/` — fichiers : `data/input/csv/` (prof, hors Git), `data/seed/csv/` (échantillon) — voir `data/README.md` **étape 1** |
| MS-02 Acquisition | `packages/acquisition/` — KBO, Moniteur, BNB, statuts + CLI `scrape` |
| MS-03 HDFS | `packages/storage/` (stub `HDFS_LOCAL_ROOT`) |
| MS-04 Extraction | `packages/extraction/` — DAG `04_extract_batch` |
| MS-05 Base | `packages/persistence/` + `infra/` |
| MS-06 Discovery | `packages/discovery/` — DAG `05_discovery_fanout` |
| MS-07 Lifecycle | `packages/lifecycle/` — DAG `06_lifecycle_refresh` |
| MS-08 Analytics | `packages/analytics/` — DAG `07_analytics_refresh` |
| MS-09 Dashboard | `packages/dashboard/` — `./scripts/run-dashboard.sh` |
| MS-10 DAGs métier | `airflow/dags/` — voir `airflow/dags/RUN_ORDER.md` |

## MS-03 — Stockage brut HDFS (validé)

Module : `packages/storage/`. Contrat gelé : `packages/storage/FREEZE.md`.

### Variables

| Variable | Rôle |
|----------|------|
| `HDFS_RAW_ROOT` | Racine logique (`hdfs://localhost:9000/raw/v1`) |
| `HDFS_LOCAL_ROOT` | Répertoire local du stub (défaut `{projet}/data/hdfs-stub`) |

### Exemple (Python)

```python
from packages.storage import store_raw_bundle, read_raw_bundle

meta = {
    "scraped_at": "2026-05-20T12:00:00+00:00",
    "source": "kbo",
    "download_status": "SUCCESS",
    "http_status": 200,
    "proxy_or_ip": "direct",
    "attempt_count": 1,
    "last_updated_at": "2026-05-20T12:00:00+00:00",
    "content_type": "text/html",
}
html = b"<!DOCTYPE html><html>...</html>"
stored = store_raw_bundle(
    source="kbo",
    enterprise_number="0123456789",
    doc_type="profile",
    content=html,
    metadata=meta,
    run_id="demo-run-1",
)
content, sidecar = read_raw_bundle(stored.hdfs_dir)
assert content == html
```

## MS-01 — Ingestion CSV & file d'attente

Module : `packages/ingestion/`. Contrat gelé : `packages/ingestion/FREEZE.md`.  
Workflow données (étape 1) : `data/README.md`.

### Variables

| Variable | Rôle |
|----------|------|
| `DATABASE_URL` | PostgreSQL métier (`belgian_companies`) — requis |
| `INGESTION_QUARANTINE_DIR` | Répertoire des lignes rejetées (défaut `{projet}/data/quarantine`) |

### CLI

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
./scripts/db-migrate.sh
python -m packages.ingestion.cli ingest data/seed/csv/sample_enterprises.csv
python -m packages.ingestion.cli ingest data/input/csv/ton_fichier.csv --column enterprise_number
```

Re-ingérer le même fichier est **idempotent** (`already_existed` augmente, pas de doublon).  
Les gros CSV du prof vont dans `data/input/csv/` (hors Git, ~2 Go).

### Exemple (Python)

```python
from packages.ingestion import ingest_csv

report = ingest_csv("data/seed/csv/sample_enterprises.csv")
assert report.created >= 1
```

## MS-02 — Acquisition / scraping

Module : `packages/acquisition/`. Contrat gelé : `packages/acquisition/FREEZE.md`.  
Recherche et plan : `packages/acquisition/RESEARCH.md`.

### Variables

| Variable | Rôle |
|----------|------|
| `ACQUISITION_MIN_DELAY_S` / `ACQUISITION_MAX_DELAY_S` | Délai aléatoire entre requêtes (défaut 0.5–2 s) |
| `ACQUISITION_MAX_RETRIES` | Tentatives par job (défaut 3) |
| `ACQUISITION_PROXY_FILE` | Fichier `host:port` (défaut `data/proxies/proxies.txt`, gitignored) |
| `ACQUISITION_PROXY_URLS` | URLs de listes proxies, séparées par `,` |
| `ACQUISITION_ALLOW_DIRECT` | `1` = autoriser requêtes sans proxy si pool vide |
| `ACQUISITION_PROXY_HEALTHCHECK` | `1` = sonde httpbin en arrière-plan (désactivé en CI) |
| `ACQUISITION_WORKER_ID` | Identifiant worker pour `claim_enterprises_for_scrape` |
| `DATABASE_URL` | PostgreSQL métier (MS-05) |
| `HDFS_LOCAL_ROOT` / `HDFS_RAW_ROOT` | Stockage brut MS-03 |

### CLI

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
export HDFS_LOCAL_ROOT="/chemin/vers/projet/data/hdfs-stub"
./scripts/db-migrate.sh
python -m packages.ingestion.cli ingest data/seed/csv/sample_enterprises.csv
python -m packages.acquisition.cli scrape --limit 3
# 5 URLs par entreprise (kbo×2, moniteur, statutes, bnb) ; KBO seul : --sources kbo
# Optionnel : persister raw_documents
python -m packages.acquisition.cli scrape --limit 3 --wire-bridge
```

Politique d’état v1 : succès → `QUEUED_PARSE` ; échec / exception → `FAILED_SCRAPE`.  
**Scraping complet par défaut** (5 jobs / entreprise) :

| Source | `doc_type` | Description |
|--------|------------|-------------|
| `kbo` | `profile` | Formulaire recherche par numéro |
| `kbo` | `enterprise_detail` | Fiche publique (`toonondernemingps.html`) |
| `moniteur` | `publication_search` | Recherche publications (eJustice) |
| `statutes` | `publications_index` | Index publications / actes |
| `bnb` | `consult_profile` | Consultation Centrale des bilans |

Numéro de test seed : `0203430576`. Sous-ensemble : `--sources kbo` ou `ACQUISITION_ENABLED_SOURCES=kbo,bnb`.

### Orchestration Airflow (hors périmètre DAG v1)

Les DAGs métier (`MS-10`) appelleront `packages.acquisition.worker.scrape_batch` depuis des callables de tâches, pas au parse-time du DAG. Voir `airflow/dags/hello.py` pour la règle d’import.

### Exemple (Python)

```python
from packages.acquisition import KboAdapter, fetch, validate_fetch
from packages.acquisition.proxy_pool import ProxyPool

job = KboAdapter().build_urls("0203430576")[0]
pool = ProxyPool(entries=[], allow_direct=True)
decision = validate_fetch(fetch(job, pool))
```

## MS-05 — Persistance PostgreSQL

Module : `packages/persistence/`. Contrat gelé : `packages/persistence/FREEZE.md`.

### Base métier (Docker)

La stack crée `belgian_companies` (utilisateur `app` / mot de passe `app`) en plus de la base Airflow.

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
./scripts/db-migrate.sh
```

### Exemple

```python
from packages.persistence import ProcessingState, SeedSource, upsert_enterprise, transition_state
from packages.persistence.session import session_scope

with session_scope() as session:
    upsert_enterprise(session, "0123456789", SeedSource.CSV)
    transition_state(session, "0123456789", ProcessingState.NEW, ProcessingState.QUEUED_SCRAPE)
```

Pont optionnel MS-03 : `from packages.persistence.bridge import wire_storage_events` puis `wire_storage_events()`.

## MS-04 — Extraction / structuration

Module : `packages/extraction/`. DAG : `04_extract_batch` ou `08_full_pipeline` (après scrape).

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
./scripts/db-migrate.sh
# Après scrape avec wire_bridge :
python -c "from packages.extraction import parse_batch; print(parse_batch(limit=3))"
```

États : `QUEUED_PARSE` → `PARSING` → `STRUCTURED` (ou `FAILED_PARSE`). Snapshots dans `enterprise_snapshots`.

## MS-06 — Découverte dynamique

Module : `packages/discovery/`. Provenance : table `enterprise_discoveries`. Enqueue : `QUEUED_SCRAPE` pour numéros `DISCOVERED`.

## MS-07 — Cycle de vie

Variable : `LIFECYCLE_MAX_AGE_DAYS` (défaut 14). Historique : `enterprise_lifecycle_history` (append-only).

## MS-08 — Analytics

Tables : `analytics_postal_summary`, `analytics_state_summary`, `analytics_activity_rank`. DAG planifié quotidiennement.

## MS-09 — Supervision & dashboard web

Interface de **supervision temps quasi réel** (sujet : files, erreurs scrape/parse/validation, proxies, performance, analytics MS-08, événements récents). Orchestration : lien vers **Airflow UI**.

### Prérequis

| Variable | Rôle |
|----------|------|
| `DATABASE_URL` | PostgreSQL métier (`belgian_companies`) — **requis** pour compteurs et analytics |
| `DASHBOARD_TOKEN` | Optionnel — si défini, envoyer `Authorization: Bearer <token>` sur les API |
| `AIRFLOW_UI_URL` | Lien header (défaut `http://localhost:8080`) |

La base doit être migrée (`./scripts/db-migrate.sh`). Pour des panneaux analytics non vides, exécuter au moins une fois le DAG `07_analytics_refresh` (ou `08_full_pipeline`) après extraction.

### Lancer le dashboard

**Docker Compose (recommandé)** — service `dashboard` dans `infra/docker-compose.yml` :

```bash
cd infra && docker compose up -d --build dashboard
# ou depuis la racine : ./scripts/run-dashboard.sh
```

**Local** (si Postgres sur `localhost:5432` sans le service Docker) :

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
pip install -r requirements-dashboard.txt
./scripts/run-dashboard.sh
```

- **UI** : http://127.0.0.1:8090/ (rafraîchissement auto ~15 s)
- **API** : `GET /api/supervision`, `GET /api/analytics`, `GET /api/events?limit=30`, `GET /api/health`
- **Fichiers** : `packages/dashboard/static/` (`index.html`, `style.css`, `app.js`), logique API `packages/dashboard/app.py`, agrégats `packages/monitoring/events.py`

### Langue d'affichage (français)

- **Acquisition** : KBO `lang=fr` (`packages/acquisition/sources/kbo.py`), Moniteur/statuts `language=fr`.
- **Extraction / dashboard** : mapping NL→FR dans `packages/i18n/nl_fr.py` (`translate_snapshot_fields`) — statut, forme juridique, rôles, libellés NACE courants. Les snapshots déjà en NL restent lisibles sans re-scrape.
- **Nom officiel** (`legal_name`) : conservé tel quel (souvent multilingue).

### Stack Airflow + dashboard (démo)

1. `cd infra && docker compose up -d` → Airflow http://localhost:8080 + dashboard http://127.0.0.1:8090
2. Ingestion / scrape / parse via DAGs (`airflow/dags/RUN_ORDER.md`)
3. Supervision : service `dashboard` (port **8090**) ou `./scripts/run-dashboard.sh`

### Tests

```bash
pytest tests/test_dashboard_ms09.py -q
```

## Contrats publics

Toute évolution d’interface inter-services passe par `doc.EN/contracts/public-interfaces.md` avec mention de version / bump dans le changelog ou la PR.
