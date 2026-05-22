#!/usr/bin/env python3
"""
Télécharge des proxies HTTP(S) gratuits (Proxifly) et ne garde que ceux joignables vers le KBO.

Usage:
  python scripts/fetch-free-proxies.py
  python scripts/fetch-free-proxies.py --max-candidates 80 --target 20
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL_FILE = ROOT / "scripts" / "proxies-pool.txt"
DEST_FILE = ROOT / "data" / "proxies" / "proxies.txt"

# Listes gratuites (HTTP CONNECT uniquement — pas SOCKS sans dépendance extra)
SOURCES = (
    # Proxyscrape — API publique, milliers d'entrées
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=yes&anonymity=all",
    # Proxifly — refresh ~5 min (GitHub + jsDelivr)
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/BE/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/FR/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/NL/data.txt",
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/countries/DE/data.txt",
    # TheSpeedX — liste GitHub courante
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
)

PROBE_KBO = "https://kbopub.economie.fgov.be/kbopub/"
PROBE_HTTPBIN = "http://httpbin.org/ip"
USER_AGENT = "belgian-companies-platform/0.1 (+proxy-fetch)"
_HOST_PORT = re.compile(r"^[\w.-]+:\d{1,5}$")


def _normalize_line(line: str) -> str | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    for prefix in ("http://", "https://", "socks4://", "socks5://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.lower().startswith("socks"):
        return None
    if "@" in s:
        s = s.rsplit("@", 1)[-1]
    if _HOST_PORT.match(s):
        return s
    return None


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", errors="replace")


def download_candidates() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in SOURCES:
        try:
            text = _fetch_text(url)
        except OSError as exc:
            print(f"  skip {url[:60]}… : {exc}", file=sys.stderr)
            continue
        added = 0
        for line in text.splitlines():
            norm = _normalize_line(line)
            if norm and norm not in seen:
                seen.add(norm)
                ordered.append(norm)
                added += 1
        label = url.split("?")[0].rstrip("/").split("/")[-1] or "api"
        print(f"  +{added} depuis {label} → {len(ordered)} uniques")
    return ordered


def probe_one(
    host_port: str,
    *,
    timeout_s: float,
    probe_url: str = PROBE_KBO,
) -> tuple[str, bool]:
    proxy = f"http://{host_port}"
    try:
        handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})]
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request(probe_url, headers={"User-Agent": USER_AGENT})
        with opener.open(req, timeout=timeout_s) as resp:
            resp.read(1024)
        return host_port, True
    except Exception:
        return host_port, False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch & validate free HTTP proxies for KBO")
    parser.add_argument("--max-candidates", type=int, default=200, help="Max proxies to test")
    parser.add_argument("--target", type=int, default=25, help="Stop after N working proxies")
    parser.add_argument("--timeout", type=float, default=12.0, help="Timeout per probe (seconds)")
    parser.add_argument("--workers", type=int, default=32, help="Parallel probes")
    parser.add_argument(
        "--probe",
        choices=("kbo", "httpbin", "both"),
        default="both",
        help="both = pré-filtre httpbin puis test KBO sur les survivants",
    )
    args = parser.parse_args()

    print("Téléchargement proxies gratuits (Proxyscrape, Proxifly, TheSpeedX, BE/FR/NL/DE)…")
    candidates = download_candidates()
    if not candidates:
        print("Aucun candidat téléchargé.", file=sys.stderr)
        return 1

    to_test = candidates[: args.max_candidates]
    pool_list = to_test

    if args.probe in ("both", "httpbin"):
        print(f"Pré-test {len(pool_list)} proxies via httpbin…")
        httpbin_ok: list[str] = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(probe_one, hp, timeout_s=args.timeout, probe_url=PROBE_HTTPBIN): hp
                for hp in pool_list
            }
            for fut in as_completed(futures):
                host_port, ok = fut.result()
                if ok:
                    httpbin_ok.append(host_port)
        print(f"  {len(httpbin_ok)} proxies répondent via httpbin")
        if args.probe == "httpbin":
            pool_list = httpbin_ok
        else:
            pool_list = httpbin_ok if httpbin_ok else pool_list

    probe_final = PROBE_KBO if args.probe in ("kbo", "both") else PROBE_HTTPBIN
    print(f"Test {len(pool_list)} proxies vers {probe_final}…")

    working: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(probe_one, hp, timeout_s=args.timeout, probe_url=probe_final): hp
            for hp in pool_list
        }
        for fut in as_completed(futures):
            host_port, ok = fut.result()
            if ok:
                working.append(host_port)
                print(f"  OK {host_port} ({len(working)}/{args.target})")
                if len(working) >= args.target:
                    for f in futures:
                        f.cancel()
                    break

    if not working:
        print(
            "\nAucun proxy gratuit joignable dans ce lot (réseau ou liste expirée).\n"
            "• Réessayez : ./scripts/fetch-free-proxies.sh\n"
            "• Ou gardez ACQUISITION_ALLOW_DIRECT=1 dans infra/.env (connexion directe).\n"
            "• Proxies payants / résidentiels BE : plus fiables pour le KBO.",
            file=sys.stderr,
        )
        return 1

    header = (
        "# Généré par scripts/fetch-free-proxies.py\n"
        "# Sources : Proxyscrape, Proxifly, TheSpeedX — testés vers KBO/httpbin\n"
        "# Rafraîchir : ./scripts/fetch-free-proxies.sh\n"
    )
    body = "\n".join(working) + "\n"
    POOL_FILE.write_text(header + body, encoding="utf-8")
    DEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        DEST_FILE.write_text(header + body, encoding="utf-8")
    except OSError:
        print(f"  (data/proxies : écriture impossible, copiez depuis {POOL_FILE})", file=sys.stderr)

    print(f"\n{len(working)} proxies enregistrés → {POOL_FILE}")
    print(f"                 → {DEST_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
