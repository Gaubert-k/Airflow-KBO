#!/usr/bin/env python3
"""Teste ip:port du pool et réécrit proxies-pool.txt + data/proxies/proxies.txt."""

from __future__ import annotations

import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "scripts" / "proxies-pool.txt"
DEST = ROOT / "data" / "proxies" / "proxies.txt"
PROBE = "https://kbopub.economie.fgov.be/kbopub/"
UA = "belgian-companies-platform/0.1"
_LINE = re.compile(r"^[\w.-]+:\d{1,5}$")


def load_candidates() -> list[str]:
    out: list[str] = []
    for line in POOL.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and _LINE.match(s):
            out.append(s)
    return out


def probe(host_port: str, timeout: float = 14.0) -> tuple[str, bool]:
    proxy = f"http://{host_port}"
    try:
        o = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        r = o.open(
            urllib.request.Request(PROBE, headers={"User-Agent": UA}),
            timeout=timeout,
        )
        r.read(800)
        r.close()
        return host_port, True
    except Exception:
        return host_port, False


def main() -> int:
    candidates = load_candidates()
    if not candidates:
        print("Aucun candidat dans", POOL, file=sys.stderr)
        return 1
    print(f"Test de {len(candidates)} proxies vers KBO…")
    working: list[str] = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(probe, c) for c in candidates]
        for f in as_completed(futs):
            hp, ok = f.result()
            if ok:
                working.append(hp)
                print(f"  OK {hp}")
            else:
                print(f"  -- {hp}")
    header = "# Proxies HTTP testés vers KBO (liste utilisateur, statut Actif)\n"
    body = "\n".join(working) + ("\n" if working else "")
    POOL.write_text(header + body, encoding="utf-8")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    try:
        DEST.write_text(header + body, encoding="utf-8")
    except OSError:
        pass
    print(f"\n{len(working)}/{len(candidates)} joignables → {POOL}")
    return 0 if working else 1


if __name__ == "__main__":
    raise SystemExit(main())
