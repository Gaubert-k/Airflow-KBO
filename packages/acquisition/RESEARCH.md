# RESEARCH — MS-02 Acquisition (scraping complet)

Date : 2026-05-20 (v2 — toutes les sources publiques du sujet)

## Sources web consultées

| Source | URL | Usage |
|--------|-----|--------|
| FOD Economie — KBO Public Search | https://economie.fgov.be/nl/themas/ondernemingen/kruispuntbank-van/diensten-voor-iedereen/raadpleging-en-opzoeking-van/kruispuntbank-van | Contexte officiel BCE/KBO |
| Formulaire opzoeking op nummer | https://kbopub.economie.fgov.be/kbopub/zoeknummerform.html | `doc_type=profile` |
| Fiche entité (PDF / brief) | https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html?lang=nl&ondernemingsnummer=0203430576 | `doc_type=enterprise_detail` |
| BNB Consult | https://consult.cbso.nbb.be/consult-enterprise/0203430576 | `source=bnb` |
| Moniteur — recherche PM | https://www.ejustice.just.fgov.be/cgi_tsv/rech.pl?language=nl&btw=0203430576 | `source=moniteur` |
| Moniteur — liste publications (**défaut statuts**, sujet PDF) | https://www.ejustice.just.fgov.be/cgi_tsv/list.pl?language=nl&btw=0203430576 | `source=statutes`, `doc_type=publications_index` |
| notaire.be (**option** `NOTAIRE_STATUTES_URL`) | https://www.notaire.be/.../les-statuts-dune-societe | `doc_type=statutes_notaire_info` |
| ProxyScrape | https://proxyscrape.com/free-proxy-list | Format `host:port` |
| httpbin | https://httpbin.org/ip | Health-check proxy (opt-in) |

## Périmètre MS-02 (aligné sujet / PDF)

| Unité d’acquisition | Implémenté | Jobs / entreprise |
|---------------------|------------|-------------------|
| KBO (recherche + fiche) | oui | 2 |
| Moniteur belge (publications) | oui | 1 |
| Statuts / index publications légales | oui | 1 |
| BNB / Centrale des bilans | oui | 1 |
| **Total** | | **5** requêtes HTTP |

**Mandats / pouvoirs** : pas d’endpoint KBO public stable en 2026 (`toonfunctiesps` → 404) ; données dans le HTML `enterprise_detail` + publications Moniteur.

## Variables d’environnement

| Variable | Défaut | Rôle |
|----------|--------|------|
| `ACQUISITION_MIN_DELAY_S` / `MAX_DELAY_S` | `0.5` / `2.0` | Jitter entre requêtes |
| `ACQUISITION_MAX_RETRIES` | `3` | Retries par job |
| `ACQUISITION_ENABLED_SOURCES` | *(vide = all)* | `kbo,moniteur,statutes,bnb` ou `all` |
| `KBO_PUBLIC_BASE_URL` | `https://kbopub.economie.fgov.be/kbopub/` | Base KBO |
| `BNB_CONSULT_BASE_URL` | `https://consult.cbso.nbb.be/` | Base BNB |
| `MONITEUR_EJUSTICE_BASE_URL` | `https://www.ejustice.just.fgov.be/cgi_tsv/` | Base Moniteur |
| `NOTAIRE_STATUTES_URL` | *(vide)* | Si défini : page notaire.be à la place de `list.pl` |
| `ACQUISITION_PROXY_FILE` / `URLS` | voir v1 | Proxies |
| `ACQUISITION_ALLOW_DIRECT` | `1` | Fallback sans proxy |
| `ACQUISITION_WORKER_ID` | `acquisition-worker-1` | Lock MS-05 |
| `DATABASE_URL` / `HDFS_LOCAL_ROOT` | MS-05 / MS-03 | Infra |

## Politique d’état

- Tous les jobs **STORE** → `QUEUED_PARSE`
- Un échec définitif → `FAILED_SCRAPE`
- Exception worker → `FAILED_SCRAPE`

## Vérification manuelle (scraping complet)

```bash
export DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
export HDFS_LOCAL_ROOT="/chemin/vers/repo/data/hdfs-stub"
./scripts/db-migrate.sh
python -m packages.ingestion.cli ingest data/seed/csv/sample_enterprises.csv
python -m packages.acquisition.cli scrape --limit 1
# Attendu : 5 dossiers sous raw/v1/ (source=kbo×2, moniteur, statutes, bnb)
ls -la "$HDFS_LOCAL_ROOT/raw/v1/source="*/
```

Sous-ensemble : `python -m packages.acquisition.cli scrape --limit 1 --sources kbo`

## Hors périmètre MS-02

- Parsing métier (MS-04), API JSON BNB (SPA), DAG Airflow (MS-10), dashboard (MS-09).
