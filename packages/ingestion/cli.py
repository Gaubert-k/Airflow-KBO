"""CLI MS-01 — ingestion CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cmd_ingest(args: argparse.Namespace) -> int:
    from packages.ingestion.ingest import ingest_csv

    report = ingest_csv(
        args.path,
        column=args.column,
        batch_size=args.batch_size,
    )
    print(f"source: {report.source_file}")
    print(f"rows_read: {report.rows_read}")
    print(f"created: {report.created}")
    print(f"already_existed: {report.already_existed}")
    print(f"rejected: {report.rejected}")
    print(f"quarantine: {report.quarantine_path or '-'}")
    print(f"duration_seconds: {report.duration_seconds:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="packages.ingestion.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", help="Ingérer un fichier CSV d'entreprises")
    ingest_parser.add_argument("path", type=Path, help="Chemin du fichier CSV")
    ingest_parser.add_argument(
        "--column",
        default=None,
        help="Nom de la colonne contenant le numéro d'entreprise",
    )
    ingest_parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Taille des lots transactionnels (défaut: 5000)",
    )
    ingest_parser.set_defaults(func=_cmd_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
