#!/usr/bin/env bash
# Annule les DAG runs en cours (état running) via l'API Airflow v2.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/infra"

API="${AIRFLOW_API_URL:-http://127.0.0.1:8080}"
USER="${AIRFLOW_API_USER:-airflow}"
PASS="${AIRFLOW_API_PASSWORD:-airflow}"

DAGS="${*:-02_scrape_by_source 02_scrape_batch 08_full_pipeline 04_extract_batch}"

TOKEN=$(curl -sf -X POST "$API/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

cancelled=0
for dag in $DAGS; do
  runs=$(curl -sf "$API/api/v2/dags/$dag/dagRuns?state=running&limit=50" \
    -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json; print(' '.join(r['dag_run_id'] for r in json.load(sys.stdin).get('dag_runs',[])))")
  for rid in $runs; do
    [ -z "$rid" ] && continue
    curl -sf -X PATCH "$API/api/v2/dags/$dag/dagRuns/$(python3 -c "import urllib.parse; print(urllib.parse.quote('$rid'))")" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"state":"failed"}' >/dev/null
    echo "Annulé (failed): $dag / $rid"
    cancelled=$((cancelled + 1))
  done
done

echo "Total runs annulés: $cancelled"
docker compose exec -T airflow-scheduler bash -c '
  for d in '"$DAGS"'; do airflow dags pause "$d" 2>/dev/null || true; done
' 2>/dev/null || true
echo "DAGs scrape mis en pause (pas de nouveaux runs jusqu'à airflow dags unpause)."
