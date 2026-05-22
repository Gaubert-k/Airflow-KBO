#!/usr/bin/env bash
# Remise à zéro données pipeline : DB app + quarantaine + stub HDFS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

echo "==> DB applicative"
"${REPO_ROOT}/scripts/db-reset-app.sh"

echo "==> Quarantaine ingestion"
rm -rf "${REPO_ROOT}/data/quarantine"/*
mkdir -p "${REPO_ROOT}/data/quarantine"

echo "==> Marqueur bootstrap (permet un nouvel init auto au prochain start)"
rm -f "${REPO_ROOT}/data/.platform_initialized"

echo "==> Stub HDFS (HTML scrapés)"
mkdir -p "${REPO_ROOT}/data/hdfs-stub"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^infra-airflow-scheduler-1$'; then
  docker exec -u root infra-airflow-scheduler-1 bash -c 'rm -rf /opt/airflow/data/hdfs-stub/*'
else
  rm -rf "${REPO_ROOT}/data/hdfs-stub"/* 2>/dev/null || true
fi

echo "Données pipeline réinitialisées."
