#!/usr/bin/env bash
# Démo bout-en-bout prof (5–10 entreprises) — ne relance PAS 01_ingest_csv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/infra"
export AIRFLOW_UID="${AIRFLOW_UID:-$(id -u)}"

echo "1/3 — Pipeline scrape + extract (Airflow)"
docker compose exec -T airflow-scheduler \
  airflow dags trigger 08_full_pipeline --conf '{"limit":8,"wire_bridge":true}'

echo "Attente fin DAG 08 (max ~3 min)…"
sleep 90
docker compose exec -T airflow-scheduler \
  airflow tasks states-for-dag-run 08_full_pipeline "$(docker compose exec -T airflow-scheduler airflow dags list-runs 08_full_pipeline -o plain 2>/dev/null | tail -1 | awk '{print $2}')" 2>/dev/null || true

echo "2/3 — Analytics + lifecycle"
docker compose exec -T airflow-scheduler airflow dags trigger 07_analytics_refresh
docker compose exec -T airflow-scheduler airflow dags trigger 06_lifecycle_refresh --conf '{"limit":10}'

echo "3/3 — Compteurs PostgreSQL"
export DATABASE_URL="${DATABASE_URL:-postgresql://app:app@localhost:5432/belgian_companies}"
psql "$DATABASE_URL" -c "
SELECT 'enterprises' t, COUNT(*) FROM enterprises
UNION ALL SELECT 'raw_documents', COUNT(*) FROM raw_documents
UNION ALL SELECT 'snapshots', COUNT(*) FROM enterprise_snapshots
UNION ALL SELECT 'analytics_postal', COUNT(*) FROM analytics_postal_summary;
"

echo "Dashboard : cd \"$ROOT\" && ./scripts/run-dashboard.sh → http://127.0.0.1:8090/"
