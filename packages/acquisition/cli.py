"""CLI MS-02 — scrape batch."""

from __future__ import annotations

import argparse
import sys


def _cmd_scrape(args: argparse.Namespace) -> int:
    from packages.acquisition.sources.registry import get_adapters
    from packages.acquisition.worker import scrape_batch

    adapters = get_adapters(enabled_sources=args.sources)
    report = scrape_batch(
        limit=args.limit,
        adapters=adapters,
        wire_persistence_bridge=args.wire_bridge,
    )
    print(f"claimed: {report.claimed}")
    print(f"succeeded: {report.succeeded}")
    print(f"failed: {report.failed}")
    print(f"enterprises: {', '.join(report.enterprises) or '-'}")
    return 0 if report.failed == 0 or report.succeeded > 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="packages.acquisition.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape_parser = sub.add_parser("scrape", help="Scraper des entreprises QUEUED_SCRAPE")
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Nombre max d'entreprises à traiter (défaut: 10)",
    )
    scrape_parser.add_argument(
        "--wire-bridge",
        action="store_true",
        help="Active le pont MS-03 → MS-05 (raw_documents)",
    )
    scrape_parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        metavar="SOURCE",
        help=(
            "Sources à scraper : kbo, moniteur, bnb, statutes (défaut : toutes). "
            "Ex. --sources kbo bnb"
        ),
    )
    scrape_parser.set_defaults(func=_cmd_scrape)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
