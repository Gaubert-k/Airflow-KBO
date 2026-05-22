#!/usr/bin/env bash
# Lance le dashboard MS-09 — de préférence via Docker Compose (service dashboard).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/infra/docker-compose.yml"

if docker compose -f "${COMPOSE_FILE}" ps dashboard 2>/dev/null | grep -qE 'running|healthy'; then
  echo "Dashboard déjà actif via Docker → http://127.0.0.1:8090/"
  exit 0
fi

if docker compose -f "${COMPOSE_FILE}" ps postgres 2>/dev/null | grep -q running; then
  echo "==> Démarrage service dashboard (Docker Compose)"
  export AIRFLOW_UI_URL="${AIRFLOW_UI_URL:-http://localhost:8080}"
  docker compose -f "${COMPOSE_FILE}" up -d --build dashboard
  echo "Dashboard → http://127.0.0.1:8090/"
  exit 0
fi

# Fallback local (Postgres sur localhost)
cd "$ROOT"
export DATABASE_URL="${DATABASE_URL:-postgresql://app:app@localhost:5432/belgian_companies}"
export AIRFLOW_UI_URL="${AIRFLOW_UI_URL:-http://localhost:8080}"
export PYTHONPATH="$ROOT"
if ! python3 -c "import fastapi" 2>/dev/null; then
  pip install -r requirements-dashboard.txt sqlalchemy==2.0.36 psycopg2-binary==2.9.10
fi
echo "==> Dashboard local (uvicorn) — Postgres doit être accessible"
exec python3 -m uvicorn packages.dashboard.app:app --host 0.0.0.0 --port 8090
