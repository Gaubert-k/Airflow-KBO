#!/usr/bin/env bash
# Premier démarrage uniquement : si le volume data/ est vierge, lance 09_platform_bootstrap.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="${REPO_ROOT}/data/.platform_initialized"
HDFS_RAW="${REPO_ROOT}/data/hdfs-stub/raw/v1"

if [[ "${PLATFORM_AUTO_BOOTSTRAP:-1}" == "0" ]]; then
  echo "Bootstrap auto désactivé (PLATFORM_AUTO_BOOTSTRAP=0)."
  exit 0
fi

if [[ -f "${MARKER}" ]]; then
  echo "Volume data déjà initialisé (${MARKER}) — pas de bootstrap."
  exit 0
fi

if [[ -d "${HDFS_RAW}" ]] && find "${HDFS_RAW}" -name 'document.html' -print -quit 2>/dev/null | grep -q .; then
  echo "HTML scrapé déjà présent — pas de bootstrap auto (créez le marqueur ou reset)."
  exit 0
fi

cd "${REPO_ROOT}/infra"
export AIRFLOW_UID="${AIRFLOW_UID:-50000}"

echo "Premier démarrage détecté — attente Airflow…"
for _ in $(seq 1 90); do
  if docker compose exec -T airflow-scheduler curl -sf http://airflow-apiserver:8080/api/v2/monitor/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Lancement DAG 09_platform_bootstrap (ingest + scrape massif + extract + analytics)…"
echo "Peut durer très longtemps si les CSV prof sont dans data/input/csv/."
docker compose exec -T airflow-scheduler \
  airflow dags trigger 09_platform_bootstrap \
  --conf '{"wire_bridge":true,"parallel_requests_per_site":5}'

echo "Suivi : http://localhost:8080 → DAG 09_platform_bootstrap"
