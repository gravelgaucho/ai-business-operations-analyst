from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from business_ops.datasets.download import DatasetImportError
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.datasets.sqlite_store import (
    SqliteStoreError,
    build_database,
    default_database_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-database",
        description="Build the verified local SQLite store from Maple Payments JSON.",
    )
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace an existing derived database.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = build_database(args.data_root, args.database, force=args.force)
    except (DatasetImportError, SqliteStoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(summary.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
