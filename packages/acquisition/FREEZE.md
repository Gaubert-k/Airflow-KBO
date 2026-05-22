# FREEZE — MS-02 Acquisition v2 (scraping complet)

Tag suggéré : `freeze/MS-02-v2`

## Interfaces stables

### `SourceAdapter`

- `build_urls(enterprise_number: str) -> list[FetchJob]`
- Champs `FetchJob` : `url`, `source`, `doc_type`, `enterprise_number`

### `fetch(job, proxy_pool) -> FetchResult`

Champs : `body`, `http_status`, `headers`, `timing_ms`, `proxy_or_ip` (ou `"direct"`), `attempt_count`.

### `validate_fetch(result) -> ValidationDecision`

- `ValidationAction` : `STORE` | `DROP` | `RETRY`
- `reason_code` stables : `HTTP_404`, `HTTP_4XX`, `HTTP_5XX`, `HTTP_OTHER`, `HTTP_2XX`, `EMPTY_BODY`, `HTML_ERROR_MARKER`, `CAPTCHA_SUSPECT`, `PROXY_TUNNEL_FAILED`, `FETCH_ERROR`, `CONTENT_TYPE_MISMATCH`

## Sources implémentées (défaut : toutes)

| `source` | Adaptateur | `doc_type` | URL (pattern) |
|----------|------------|------------|----------------|
| `kbo` | `KboAdapter` | `profile` | `{KBO}/zoeknummerform.html?lang=nl&nummer=XXXX.XXX.XXX` |
| `kbo` | `KboAdapter` | `enterprise_detail` | `{KBO}/toonondernemingps.html?lang=nl&ondernemingsnummer={10digits}` |
| `moniteur` | `MoniteurAdapter` | `publication_search` | `{MONITEUR}/rech.pl?language=nl&btw={10digits}` |
| `statutes` | `StatutesAdapter` | `publications_index` (défaut) | `{MONITEUR}/list.pl?language=nl&btw={10digits}` |
| `statutes` | `StatutesAdapter` | `statutes_notaire_info` (option) | `NOTAIRE_STATUTES_URL` si défini (consigne prof) |
| `bnb` | `BnbAdapter` | `consult_profile` | `{BNB}/consult-enterprise/{10digits}` |

Variables de base : `KBO_PUBLIC_BASE_URL`, `BNB_CONSULT_BASE_URL`, `MONITEUR_EJUSTICE_BASE_URL`.

**Mandats / pouvoirs** : pas de page KBO publique dédiée stable (404 sur `toonfunctiesps` v2026) ; contenu présent dans le HTML `enterprise_detail` ; publications dans Moniteur/statuts.

### Intégration MS-03

- Sur `STORE` uniquement : `store_raw_bundle(...)` avec `download_status=SUCCESS`
- **5 artefacts bruts** par entreprise en scrape complet (2 KBO + moniteur + statuts + BNB)

### Intégration MS-05

1. `claim_enterprises_for_scrape(session, limit=..., worker_id=...)`
2. Pour chaque job : fetch → validate (retries ≤ `ACQUISITION_MAX_RETRIES`)
3. **Succès** (tous les jobs STORE) : `SCRAPING` → **`QUEUED_PARSE`**
4. **Échec définitif** (un job DROP/épuisé) : `SCRAPING` → **`FAILED_SCRAPE`**
5. **Exception non récupérée** : `SCRAPING` → **`FAILED_SCRAPE`**

### Sélection des sources

- `ACQUISITION_ENABLED_SOURCES` : CSV (`kbo,moniteur,statutes,bnb`) ou vide / `all` → **toutes**
- CLI : `--sources kbo bnb` pour sous-ensemble

### Proxy pool

- Fichier `data/proxies/proxies.txt` (gitignored), format `host:port`
- `ACQUISITION_PROXY_URLS` (CSV)
- Métrique `proxy_failures` via `packages.acquisition.metrics.record_proxy_failure`
- Health-check : opt-in `ACQUISITION_PROXY_HEALTHCHECK=1`, thread daemon, non bloquant CI

## Variables d’environnement gelées

Voir `packages/acquisition/RESEARCH.md` et `packages/acquisition/config.py`.

## Validation HTML (v2.1 — 2026-05-20)

- Ne plus rejeter les fiches KBO valides contenant « Geen gegevens opgenomen in KBO » (champ vide).
- Marqueurs page-level : `geen onderneming`, `onderneming niet gevonden`, etc.

## Non gelé / évolutif

- Heuristiques HTML (marqueurs d’erreur / captcha)
- BNB SPA (shell HTML ; API JSON hors MS-02)
- Délais et timeouts par défaut
