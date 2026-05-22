# Matrice livrable — sujet PDF ↔ dépôt

Source : `AIRFLOW_Group_project.pdf` — trace détaillée : `doc.EN/reference/requirements-traceability.md`.

| Exigence (résumé) | Statut | Preuve | Action / limite |
|-------------------|--------|--------|------------------|
| Lire CSV numéros entreprises | ✅ | `packages/ingestion/`, DAG `01_ingest_csv` | CSV prof dans `data/input/csv/` — **3 634 593** lignes en base (ne pas relancer l’ingest) |
| Scraper HTML sans extraction métier | ✅ | `packages/acquisition/`, DAG `02` / `08` | Lots `limit` ; démo : **75** `raw_documents` |
| Stocker brut sur HDFS | ✅ (stub cours) | `packages/storage/` → `data/hdfs-stub/` | **Choix pédagogique** : stub local monté dans Docker (`HDFS_LOCAL_ROOT`), pas cluster Hadoop |
| Ne jamais stocker pages d’erreur | ✅ | `validation.py`, MS-02 `validate_fetch` | |
| Métadonnées obligatoires scraping | ✅ | sidecar `metadata.json`, MS-02 | |
| Sources indépendantes (KBO, Moniteur, BNB, …) | ✅ | DAG **`02_scrape_by_source`** (4 tasks ∥) | kbo / moniteur / statutes / bnb |
| Traitement auto après HDFS | ✅ | `wire_bridge`, DAG `04` / `08` | `08_full_pipeline` : scrape **success** → extract **success** (2026-05-21) |
| Extraction champs structurés (liste PDF) | ✅ (MVP) | `kbo.py` (fiche + profil), `moniteur.py`, `generic.py` | Bug NACE corrigé ; pas tous les champs PDF |
| Base structurée | ✅ | `packages/persistence/`, migrations | **10** `enterprise_snapshots` après démo |
| Découverte dynamique + provenance | ✅ | `packages/discovery/`, DAG `05` | Heuristiques liens HTML |
| Cycle de vie / fraîcheur 2 semaines | ✅ (logique) | DAG `06_lifecycle_refresh`, `LIFECYCLE_MAX_AGE_DAYS` | `due_selected=0` tant que scrapes < 14 j (comportement attendu) |
| Historisation (pas de suppression) | ✅ | snapshots + `enterprise_lifecycle_history` | |
| Analytics périodiques | ✅ | DAG `07`, tables `analytics_*` | Démo : **8** postal, **19** activity, **1** state |
| Dashboard supervision temps réel | ✅ | `packages/dashboard/`, `:8090` | `/api/supervision` — `fully_structured: 10` |
| Orchestration Airflow + dépendances | ✅ | DAGs `00`–`08`, `08_full_pipeline` | Pools : `scrape_parallel_pool` (4), `scrape_pool`, `ingest_pool` |
| Proxies (listes externes sujet) | ⚠️ | `ACQUISITION_PROXY_*` | Optionnel en démo |

**Légende :** ✅ conforme démo | ⚠️ partiel / optionnel | ❌ absent.

## Preuves démo (2026-05-21)

```sql
-- DATABASE_URL=postgresql://app:app@localhost:5432/belgian_companies
SELECT COUNT(*) FROM enterprises;              -- 3634593
SELECT COUNT(*) FROM raw_documents;            -- 75
SELECT COUNT(*) FROM enterprise_snapshots;     -- 10
SELECT COUNT(*) FROM analytics_postal_summary; -- 8
SELECT COUNT(*) FROM analytics_activity_rank;  -- 19
```

Airflow : `08_full_pipeline` tâches `scrape` + `extract` en **success**. Tests : **51** passed (`pytest tests/ -q`).

## Checklist rendu prof

- [x] Ingest millions (déjà fait)
- [x] Pipeline bout-en-bout démo (`08` + `07`)
- [x] Snapshots + analytics non vides
- [x] Dashboard opérationnel
- [x] HDFS stub documenté comme choix cours
- [x] `pytest` vert
