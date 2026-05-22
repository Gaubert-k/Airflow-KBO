#!/usr/bin/env bash
# Télécharge des proxies gratuits (Proxifly) et valide ceux qui atteignent le KBO.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python scripts/fetch-free-proxies.py "$@"
fi
exec python3 scripts/fetch-free-proxies.py "$@"
