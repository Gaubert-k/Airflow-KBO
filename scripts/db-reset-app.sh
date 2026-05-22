#!/usr/bin/env bash
# Vide toute la base applicative belgian_companies (repartir de zéro).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${DATABASE_URL:=postgresql://app:app@localhost:5432/belgian_companies}"

echo "==> TRUNCATE belgian_companies (CASCADE)"
if [[ "${DATABASE_URL}" == *"@postgres:"* ]] || docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^infra-postgres-1$'; then
  docker exec infra-postgres-1 psql -U app -d belgian_companies -v ON_ERROR_STOP=1 -c \
    "TRUNCATE enterprises RESTART IDENTITY CASCADE;"
else
  psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -c \
    "TRUNCATE enterprises RESTART IDENTITY CASCADE;"
fi

docker exec infra-postgres-1 psql -U app -d belgian_companies -t -c "SELECT count(*) AS enterprises FROM enterprises;" 2>/dev/null \
  || psql "${DATABASE_URL}" -t -c "SELECT count(*) FROM enterprises;"

echo "Base applicative vidée."
