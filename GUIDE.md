# Guide utilisateur — Plateforme entreprises belges

Document principal en **français**. Pour le développement technique : [`README_DEV.md`](README_DEV.md).

## En bref

| Étape | Outil | Résultat |
|-------|--------|----------|
| 0. Premier démarrage (volume `data/` vide) | Auto → DAG `09_platform_bootstrap` | Ingest + scrape massif + extract + marqueur `.platform_initialized` |
| 1. Charger les numéros BCE | DAG `01_ingest_csv` | Millions d’entreprises en file `QUEUED_SCRAPE` (sauter si 09 déjà passé) |
| 2. Scraper les sites publics | DAG **`02_scrape_by_source`** | HTML en HDFS + `raw_documents` |
| 3. Structurer les données | DAG `04_extract_batch` ou bouton **Parser** | Registre entreprise (fiche FR) |
| 4. Agrégats | DAG `07_analytics_refresh` | Onglet Analytics du dashboard |
| 5. Superviser | Dashboard **:8090** | Files, détail entreprise, lancement DAGs |

**Démo rapide (tout-en-un)** : DAG `08_full_pipeline` avec `{"limit": 5, "wire_bridge": true}`.

---

## États d’une entreprise

```
QUEUED_SCRAPE → SCRAPING → QUEUED_PARSE → PARSING → STRUCTURED
       ↓              ↓                         ↓
 FAILED_SCRAPE                    FAILED_PARSE
```

| État (UI) | Signification | Action |
|-----------|---------------|--------|
| File scrape | En attente de scrape | DAG `02_scrape_by_source` |
| Scrape en cours | Claim par un worker | Attendre la fin du DAG |
| File parse | Bruts OK, pas encore structuré | **Parser** ou DAG `04` |
| Structuré | Snapshot registre en base | Ouvrir **Détail** |
| Échec scrape / parse | Erreur | Relancer scrape ou parse |

---

## Scrape : KBO Tor puis 3 sites

Utilisez **`02_scrape_by_source`** (pas `02_scrape_batch` pour le quotidien).

```
prepare_claim  →  scrape_kbo  →  scrape_moniteur ─┐
                              →  scrape_statutes ─┼─ en parallèle (direct)
                              →  scrape_bnb  ─┘
               →  finalize_scrape
```

Le KBO passe par **Tor** : une requête en **IP directe** (principale), puis dès le **premier captcha** bascule **immédiate** vers `tor1`, puis `tor2`, puis `tor3` (pour tout le run, pas « tout le lot en direct d’abord »). Le paramètre `limit` est **global** (nombre de BCE claimées au prepare). Les autres sites ne traitent que les BCE où le KBO a réussi.

| Site | Task Airflow | Contenu |
|------|----------------|---------|
| KBO | `scrape_kbo` | Fiche entreprise (FR) |
| Moniteur belge | `scrape_moniteur` | Publications |
| Statuts | `scrape_statutes` | Index publications |
| BNB | `scrape_bnb` | Profil consult |

**Depuis le dashboard**

1. Onglet **Entreprises** → filtre « File scrape ».
2. Cochez des numéros BCE (ou laissez vide pour un lot `limit`).
3. **DAG scrape (Airflow)** ou onglet **DAGs** → **Lancer**.

**Conf exemple**

```json
{
  "limit": 25,
  "wire_bridge": true,
  "sources": "kbo,moniteur,statutes,bnb",
  "parallel_requests_per_site": 5,
  "kbo_use_tor": true,
  "kbo_direct_first": true,
  "tor_loop": false,
  "enterprise_numbers": "0203430576,0123456789"
}
```

`parallel_requests_per_site` : requêtes HTTP simultanées **par site** dans chaque task (max **32**). **Statuts** : toujours **1** (séquentiel) ; **direct uniquement** (pas de Tor — ejustice ne répond pas via Tor) ; **sans** pause entre requêtes ; **keep-alive** ; **skip** des BCE déjà en `SUCCESS` ; captcha/429 → **arrêt gracieux** (task en succès, partiel accepté).  
`kbo_use_tor` / `kbo_direct_first` / `tor_loop` : stratégie KBO (voir ci-dessous).

`enterprise_numbers` : chaîne CSV (pas un tableau JSON).

---

## Détail entreprise (dashboard)

- **Détail** : identité, siège, dirigeants, NACE, Moniteur — en **français** (traduction NL→FR si données anciennes).
- **Documents bruts** : preuve du scrape (4 sources).
- Si message « prêt pour parse » : cliquer **Parser** alors que des bruts SUCCESS existent.

---

## URLs

| Service | URL | Identifiants |
|---------|-----|--------------|
| Airflow | http://localhost:8080 | `airflow` / `airflow` |
| Dashboard | http://127.0.0.1:8090 | — |

---

## Pools Airflow (Docker)

Créés au `docker compose up` via `airflow/scripts/init_pools.sh` :

| Pool | Slots | Usage |
|------|-------|--------|
| `ingest_pool` | 1 | Ingest CSV |
| `scrape_pool` | 2 | prepare / finalize / extract |
| `scrape_parallel_pool` | 4 | KBO + 3 branches secondaires |

---

## Captcha KBO et Tor

KBO peut rediriger vers `captchaform.html` après trop de requêtes. Le flux principal utilise **3 conteneurs Tor** (`tor1`, `tor2`, `tor3` dans `infra/docker-compose.yml`), pas des listes de proxies HTTP gratuits.

```bash
cd infra && docker compose up -d   # démarre postgres, tor1–tor3, Airflow
```

Variables (déjà dans `docker-compose`, surcharge via `infra/.env`) :

```bash
ACQUISITION_USE_TOR=1
ACQUISITION_TOR_PROXIES=socks5h://tor1:9050,socks5h://tor2:9050,socks5h://tor3:9050
ACQUISITION_KBO_DIRECT_FIRST=1
ACQUISITION_HTTP_TIMEOUT_S=60
```

Comportement : captcha / 403 / 429 sur la lane courante → **bascule immédiate** vers la Tor suivante pour toutes les BCE encore en file ; si les 3 Tor sont épuisées → task KBO en erreur (`CaptchaBlockedError`). Param DAG `tor_loop=true` : nouveau cycle direct→tor après **10 min minimum** (`ACQUISITION_TOR_LOOP_MIN_INTERVAL_S=600`).

**Usage responsable** : petits lots (`limit` raisonnable), pas de spam massif.

Les anciennes listes `data/proxies/proxies.txt` restent optionnelles (`ACQUISITION_USE_PROXIES=1`) mais ne sont plus le chemin recommandé pour le TP.

## Dépannage

| Problème | Cause probable | Solution |
|----------|----------------|----------|
| Captcha KBO / task bloquée | Trop de requêtes / Tor bloqué | Vérifier `tor1–3` up, `kbo_direct_first`, réduire `parallel_requests_per_site` |
| Pas de registre malgré « Structuré » | Snapshot absent ou ancien format | **Parser** ou DAG `04` |
| DAG 400 `enterprise_numbers` | Tableau JSON envoyé | CSV : `"n1,n2"` |
| 2 sites à la fois seulement | Ancien pool 2 slots | Vérifier `scrape_parallel_pool` = 4 |
| Texte en néerlandais | Données scrapées en `nl` | Re-scrape (URLs en `fr` par défaut) ou traduction à l’affichage |
| HDFS permission denied | Fichiers créés par UID Airflow | `chmod -R a+rwX data/hdfs-stub` |

---

## Fichiers utiles

| Fichier | Rôle |
|---------|------|
| [`airflow/dags/RUN_ORDER.md`](airflow/dags/RUN_ORDER.md) | Liste des DAGs |
| [`LIVRABLE.md`](LIVRABLE.md) | Matrice sujet PDF ↔ preuves |
| [`data/README.md`](data/README.md) | CSV prof / ingest |
| [`scripts/demo-e2e.sh`](scripts/demo-e2e.sh) | Démo automatique |
