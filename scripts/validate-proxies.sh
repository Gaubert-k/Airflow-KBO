#!/usr/bin/env bash
# Teste les proxies du pool contre KBO (ou ACQUISITION_PROXY_PROBE_URL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/infra"
docker compose exec -T airflow-scheduler python3 <<'PY'
from packages.acquisition.config import get_acquisition_config
from packages.acquisition.pool_bootstrap import prepare_proxy_pool

cfg = get_acquisition_config()
pool = prepare_proxy_pool(cfg)
total = len(pool)
ok = pool.healthy_count()
print(f"Fichier: {cfg.proxy_file}")
print(f"Joignables: {ok}/{total} (allow_direct={cfg.allow_direct})")
if ok == 0:
    raise SystemExit(1)
PY
