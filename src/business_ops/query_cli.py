from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from business_ops.datasets.download import DatasetImportError, verify_dataset
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.datasets.query_types import OpportunityBreakdownQuery, OpportunityDimension
from business_ops.datasets.sqlite_store import (
    SqliteEnterpriseBenchRepository,
    SqliteStoreError,
    default_database_path,
)
from business_ops.reports import opportunity_breakdown_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-query",
        description="Run a governed closed-won opportunity ACV breakdown.",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--dimension",
        action="append",
        choices=[item.value for item in OpportunityDimension],
        help="Approved grouping dimension; repeat once to add a second dimension.",
    )
    parser.add_argument("--currency", choices=["USD", "GBP"], default="USD")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--engine", choices=["sqlite", "json"], default="sqlite")
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--database", type=Path, default=default_database_path())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        query = OpportunityBreakdownQuery(
            start_date=args.start,
            end_date=args.end,
            dimensions=args.dimension or [OpportunityDimension.REGION],
            currency=args.currency,
            top_n=args.top,
        )
        root = verify_dataset(args.data_root.resolve())
        source = (
            SqliteEnterpriseBenchRepository(args.database, source_root=root)
            if args.engine == "sqlite"
            else root
        )
        report = opportunity_breakdown_report(source, query)
    except (DatasetImportError, SqliteStoreError, ValidationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
