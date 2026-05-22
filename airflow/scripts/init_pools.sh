#!/usr/bin/env bash
# Pools Airflow — 4 slots pour scrape par source en parallèle.
set -euo pipefail

airflow pools set ingest_pool 1 "Ingest CSV (1 slot)" 2>/dev/null || true
airflow pools set scrape_pool 2 "Scrape séquentiel / extract" 2>/dev/null || true
airflow pools set scrape_parallel_pool 4 "4 sites en parallèle (kbo, moniteur, statutes, bnb)" 2>/dev/null || true

echo "Pools: ingest_pool=1, scrape_pool=2, scrape_parallel_pool=4"
