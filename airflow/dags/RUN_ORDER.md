# Ordre d’exécution des DAGs

Préfixe `00`–`08` pour le tri dans l’UI Airflow. **Parcours détaillé :** [`../../GUIDE.md`](../../GUIDE.md).

## Parcours recommandé

```text
09_platform_bootstrap  (AUTO une fois si volume data/ vide — ingest + scrape massif + extract)
        ↓
01_ingest_csv          (une fois, ou inclus dans 09)
        ↓
02_scrape_by_source    (KBO Tor → 3 sites sur BCE KBO OK)  ← DAG principal
        ↓
04_extract_batch       (structuration)
        ↓
07_analytics_refresh   (agrégats dashboard)
```

**Démo courte :** `08_full_pipeline` (scrape par source + extract) puis `07_analytics_refresh`.

## Phase A — smoke

| `dag_id` | Rôle |
|----------|------|
| `00_hello` | Vérifier Airflow après `docker compose up` |

## Bootstrap automatique (premier `docker compose up`)

Si **`data/.platform_initialized`** est absent **et** aucun HTML dans `data/hdfs-stub/raw/` **et** base vide :

- `infra/scripts/start.sh` déclenche **`09_platform_bootstrap`**
- Chaîne : ingest CSV (`seed` + `input`) → scrape par lots (défaut 2000 BCE/lot, jusqu'à file vide) → extract → analytics
- À la fin : marqueur `data/.platform_initialized` (ne se relance plus)

Variables : `PLATFORM_AUTO_BOOTSTRAP=0` pour désactiver ; `PLATFORM_BOOTSTRAP_SCRAPE_BATCH`, `PLATFORM_BOOTSTRAP_SCRAPE_MAX_BATCHES`.

Reset complet : `./scripts/reset-pipeline-data.sh` supprime le marqueur + HDFS.

## Phase B — ingestion & scrape

| `dag_id` | Rôle | Quand |
|----------|------|--------|
| `09_platform_bootstrap` | Init auto volume vide | **Premier démarrage** uniquement |
| `01_ingest_csv` | CSV → PostgreSQL | **Une fois** (~3,6 M) ou via 09 |
| **`02_scrape_by_source`** | **prepare → KBO → 3 tasks → finalize** | **Scrape standard** |
| `02_scrape_batch` | 1 task, tout séquentiel | Legacy / debug uniquement |
| `03_pipeline_dev` | Ingest + scrape dev | Tests locaux |

### `02_scrape_by_source` (à privilégier)

Tasks : `prepare_claim` → `scrape_kbo` → `scrape_moniteur` | `scrape_statutes` | `scrape_bnb` → `finalize_scrape`.

**KBO** : IP directe puis `tor1`→`tor2`→`tor3` ; **premier captcha = bascule immédiate** (pas un lot entier sur direct). `limit` = max BCE **globales** au prepare.  
**Moniteur / statuts / BNB** : direct, uniquement les BCE où KBO a réussi (`kbo_ok_numbers`).

Params : `limit`, `wire_bridge`, `sources`, `enterprise_numbers`, `kbo_use_tor`, `kbo_direct_first`, `tor_loop`, `parallel_requests_per_site`.

Infra : `docker compose up -d` démarre aussi `tor1`, `tor2`, `tor3`. Variables : `ACQUISITION_USE_TOR`, `ACQUISITION_TOR_PROXIES`.

## Phase C — structuration & analytics

| `dag_id` | Rôle |
|----------|------|
| `04_extract_batch` | `QUEUED_PARSE` → snapshots structurés |
| `05_discovery_fanout` | Liens découverte → nouvelles entreprises |
| `06_lifecycle_refresh` | Rescrape si > 14 jours |
| `07_analytics_refresh` | Tables `analytics_*` |
| `08_full_pipeline` | Scrape par source + extract (petit lot) |

## Exemples CLI

```bash
cd infra
docker compose exec -T airflow-scheduler airflow dags trigger 02_scrape_by_source \
  --conf '{"limit":10,"wire_bridge":true,"sources":"kbo,moniteur,statutes,bnb","kbo_use_tor":true,"kbo_direct_first":true,"tor_loop":false}'

docker compose exec -T airflow-scheduler airflow dags trigger 04_extract_batch \
  --conf '{"limit":10}'

docker compose exec -T airflow-scheduler airflow dags trigger 08_full_pipeline \
  --conf '{"limit":5,"wire_bridge":true}'
```

**Prérequis parse :** scrape avec `wire_bridge=true` pour remplir `raw_documents`.

## Supervision

Dashboard : `./scripts/run-dashboard.sh` → http://127.0.0.1:8090/
