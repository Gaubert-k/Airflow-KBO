# Données du projet — organisation

## Bootstrap automatique (première ouverture du volume `data/`)

Si le dossier est **vierge** (pas de `data/.platform_initialized`, pas de HTML dans `hdfs-stub/`) :

```bash
cd infra && ./scripts/start.sh
```

→ déclenche le DAG **`09_platform_bootstrap`** (ingest + scrape par lots + extract + analytics).  
**Une seule fois** ; les démarrages suivants ignorent ce flux.

Désactiver : `PLATFORM_AUTO_BOOTSTRAP=0` dans `infra/.env`.  
Tout remettre à zéro : `./scripts/reset-pipeline-data.sh` (supprime aussi le marqueur).

---

## Étape 1 — Initialisation CSV (fichiers du prof, ~2 Go)

**Objectif :** déposer les CSV fournis par le prof, puis (une fois **MS-01** codé) les charger dans PostgreSQL (`enterprises` + file `QUEUED_SCRAPE`).  
Les CSV **ne vont pas** sur HDFS : HDFS = pages HTML scrapées plus tard (**MS-02** / **MS-03**).

### 1. Copier les fichiers du prof

Place **tous** les gros CSV ici (dossier ignoré par Git) :

```text
data/input/csv/
  entreprises.csv          ← exemple de nom
  autre_fichier.csv        ← plusieurs fichiers possibles
```

Chemin absolu typique :

`/home/guillaume/Bureau/Airflow TP/data/input/csv/`

**Ne pas** les committer : ils restent sur ta machine seulement (souvent ~2 Go au total).

### 2. Inspecter avant ingestion (manuel)

```bash
wc -l data/input/csv/ton_fichier.csv
head -n 5 data/input/csv/ton_fichier.csv
```

Note le nom de la colonne qui contient le numéro d’entreprise (ou la première colonne si c’est déjà le numéro).

### 3. Petit échantillon pour dev / tests (versionné)

Pour le code et la CI, utilise un extrait léger :

```text
data/seed/csv/sample_enterprises.csv
```

Tu peux en générer un depuis le gros fichier :

```bash
head -n 501 data/input/csv/ton_fichier.csv > data/seed/csv/sample_enterprises.csv
```

(Adapter si la première ligne est un en-tête : garder l’en-tête + 500 lignes.)

### 4. Lancer l’ingestion (**une fois** → base PostgreSQL)

**Airflow (recommandé)** — DAG `01_ingest_csv` : parcourt `data/seed/csv/` + `data/input/csv/`, ingère tous les CSV qui ont une colonne entreprise (`EnterpriseNumber`, `EntityNumber`, …). Ignore `meta.csv`, `code.csv`, etc.

```bash
cd infra && docker compose exec airflow-scheduler airflow dags trigger 01_ingest_csv
```

**CLI locale** (fichier par fichier) :

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
python -m packages.ingestion.cli ingest data/seed/csv/sample_enterprises.csv
python -m packages.ingestion.cli ingest data/input/csv/enterprise.csv
```

Relancer est **idempotent** (pas de doublons). Ensuite : **uniquement** les DAGs scrape (`02`, `02_scrape_by_source`, `03`).

### 5. Lignes invalides

Rejets MS-01 → `data/quarantine/` (également ignoré par Git).

### 6. Vérifier en base

```sql
SELECT COUNT(*) FROM enterprises WHERE seed_source = 'CSV';
SELECT state, COUNT(*) FROM enterprise_processing_state GROUP BY state;
```

### 7. Suite du projet (phase B)

| Après étape 1 | Microservice |
|---------------|--------------|
| File remplie en Postgres | **MS-01** ✓ |
| Scraping HTTP → HDFS | **MS-02** |
| DAG ingest + scrape | **MS-10** |

Le scraping complet de millions de lignes peut prendre très longtemps : valider d’abord sur `data/seed/csv/`, puis scaler.

## Arborescence

| Dossier | Git | Usage |
|---------|-----|--------|
| `data/input/csv/` | ignoré (sauf `.gitkeep` / README) | **CSV du prof (~2 Go)** |
| `data/seed/csv/` | versionné | échantillons dev / tests |
| `data/quarantine/` | ignoré | lignes CSV rejetées |
| `data/hdfs-stub/` | ignoré | brut HTML (**MS-03**) |
| `data/proxies/proxies.txt` | ignoré (généré) | pool HTTP MS-02 (captcha KBO) |

## Acquisition HTTP (MS-02)

Scrape en **connexion directe** (`ACQUISITION_USE_PROXIES=0` dans `infra/.env`).
Si un **captcha** est détecté, la task Airflow du site **échoue tout de suite** (pas de retry) et `finalize_scrape` ne part pas (`all_success`).

## Analytics (MS-08)

Après extraction : `airflow dags trigger 07_analytics_refresh`. L’onglet **Exploitation des données** du dashboard affiche codes postaux, statuts KBO (Actif / Inactif / …) et NACE en français avec pourcentages.
