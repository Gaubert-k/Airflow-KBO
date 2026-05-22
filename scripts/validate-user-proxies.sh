#!/usr/bin/env bash
# Teste scripts/proxies-pool.txt depuis le conteneur Airflow (comme le scrape réel).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/infra"
docker compose exec -T airflow-scheduler python3 - <<'PY'
from __future__ import annotations

import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

POOL = Path("/opt/airflow/data/proxies/proxies.txt")
# fallback si pas encore copié
if not POOL.is_file():
    POOL = Path("/opt/airflow/packages/../scripts/proxies-pool.txt")
CANDS = []
for p in (Path("/opt/airflow/data/proxies/proxies.txt"),):
    if p.is_file():
        CANDS = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
        break
if not CANDS:
    raise SystemExit("Aucun candidat — copiez scripts/proxies-pool.txt vers data/proxies/")

UA = "belgian-companies-platform/0.1"
PROBE_HTTPBIN = "http://httpbin.org/ip"
PROBE_KBO = "https://kbopub.economie.fgov.be/kbopub/"

def test(hp: str, url: str, t: float = 18.0) -> bool:
    proxy = f"http://{hp}"
    try:
        o = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        r = o.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=t)
        r.read(600)
        r.close()
        return True
    except Exception:
        return False

print(f"Test de {len(CANDS)} proxies (environnement Airflow)…")
httpbin_ok: list[str] = []
with ThreadPoolExecutor(24) as ex:
    futs = {ex.submit(test, c, PROBE_HTTPBIN): c for c in CANDS}
    for f in as_completed(futs):
        c = futs[f]
        if f.result():
            httpbin_ok.append(c)
            print(f"  httpbin OK  {c}")
        else:
            print(f"  httpbin --  {c}")

kbo_ok = [c for c in httpbin_ok if test(c, PROBE_KBO, 22.0)]
for c in httpbin_ok:
    if c not in kbo_ok:
        print(f"  kbo --      {c}")
for c in kbo_ok:
    print(f"  kbo OK      {c}")

working = kbo_ok if kbo_ok else httpbin_ok
if kbo_ok:
    header = f"# {len(working)}/{len(CANDS)} joignables vers KBO (test Airflow)\n"
else:
    header = (
        f"# {len(working)}/{len(CANDS)} joignables (httpbin seulement — KBO bloque)\n"
    )
body = "\n".join(working) + ("\n" if working else "")
print("\n" + header.strip())
print(body, end="")
PY
