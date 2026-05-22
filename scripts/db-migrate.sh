#!/usr/bin/env bash
# MS-05 — applique les migrations Alembic sur DATABASE_URL
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/packages"
: "${DATABASE_URL:=postgresql://app:app@localhost:5432/belgian_companies}"

echo "==> alembic upgrade head (${DATABASE_URL})"
python -m alembic -c packages/persistence/alembic.ini upgrade head

echo "Migrations MS-05 OK"
