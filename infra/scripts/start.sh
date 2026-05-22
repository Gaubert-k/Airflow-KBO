#!/usr/bin/env bash
# Démarre la stack Airflow MS-00 (depuis la racine du repo ou infra/)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${INFRA_DIR}/.." && pwd)"

cd "${INFRA_DIR}"

if [[ ! -f .env ]]; then
  echo "Création de infra/.env depuis .env.example…"
  cp "${REPO_ROOT}/.env.example" .env
  # Chemins relatifs pour docker compose
  sed -i "s|AIRFLOW_PROJ_DIR=.*|AIRFLOW_PROJ_DIR=${REPO_ROOT}|" .env
  sed -i "s|AIRFLOW_DAGS_DIR=.*|AIRFLOW_DAGS_DIR=${REPO_ROOT}/airflow/dags|" .env
  sed -i "s|AIRFLOW_PACKAGES_DIR=.*|AIRFLOW_PACKAGES_DIR=${REPO_ROOT}/packages|" .env
fi

# 50000 = utilisateur airflow dans l'image officielle (évite KeyError getpwuid)
export AIRFLOW_UID="${AIRFLOW_UID:-50000}"
if grep -q '^AIRFLOW_UID=' .env 2>/dev/null; then
  sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=${AIRFLOW_UID}/" .env
else
  echo "AIRFLOW_UID=${AIRFLOW_UID}" >> .env
fi

docker compose up -d
echo "UI : http://localhost:8080 (airflow / airflow par défaut)"

if [[ "${PLATFORM_AUTO_BOOTSTRAP:-1}" != "0" ]]; then
  echo "Vérification bootstrap premier démarrage (volume data vide)…"
  bash "${REPO_ROOT}/scripts/bootstrap-if-empty.sh" || true
fi
