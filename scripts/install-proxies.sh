#!/usr/bin/env bash
# Installe le pool proxies (copie statique ou fetch gratuit + test KBO).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "${1:-}" == "--validate" ]]; then
  cp "$ROOT/scripts/proxies-pool.txt" "$DEST" 2>/dev/null || true
  exec "$ROOT/scripts/validate-user-proxies.sh"
fi
DEST="$ROOT/data/proxies/proxies.txt"
mkdir -p "$(dirname "$DEST")"
if [[ -f "$ROOT/scripts/proxies-pool.txt" ]]; then
  cp "$ROOT/scripts/proxies-pool.txt" "$DEST"
else
  echo "proxies-pool.txt absent — lancez : ./scripts/fetch-free-proxies.sh" >&2
  exit 1
fi
chmod 644 "$DEST" 2>/dev/null || true
echo "Installé : $DEST ($(grep -cE '^[0-9]' "$DEST" || echo 0) proxies)"
echo "Liste fraîche : ./scripts/install-proxies.sh --fetch"
