#!/usr/bin/env bash
# MS-00 T00.3 — lint, tests unitaires, smoke import
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

export PYTHONPATH="${REPO_ROOT}"

echo "==> ruff check"
python -m ruff check airflow/dags packages tests

echo "==> pytest (unit + DAG parse)"
if ! python -c "import airflow" 2>/dev/null; then
  python -m pip install -q -r requirements.txt
fi
python -m pytest tests -q

echo "==> import smoke"
python -c "import packages; import packages.platform; import packages.storage; import packages.persistence; import packages.ingestion; import packages.acquisition; import packages.orchestration; print('smoke ok:', packages.__version__)"

echo "CI baseline OK"
