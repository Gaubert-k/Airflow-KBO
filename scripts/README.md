# Scripts — aide-mémoire

| Script | Usage |
|--------|--------|
| `db-migrate.sh` | Appliquer les migrations PostgreSQL |
| `db-reset-app.sh` | Réinitialiser les données applicatives (hors ingest massif) |
| `reset-pipeline-data.sh` | Remettre les états pipeline + vider bruts/snapshots |
| `run-dashboard.sh` | Lancer le dashboard MS-09 sur le port 8090 |
| `demo-e2e.sh` | Démo : DAG 08 + 07 + compteurs SQL |
| `proxies-pool.txt` | Liste proxies (captcha KBO) |
| `install-proxies.sh` | Copie vers `data/proxies/proxies.txt` |
| `cancel-airflow-runs.sh` | Annule les DAG runs **running** + pause les DAGs scrape |

Voir [`../GUIDE.md`](../GUIDE.md) pour le parcours complet.
