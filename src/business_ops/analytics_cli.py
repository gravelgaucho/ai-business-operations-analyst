from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from business_ops.datasets.enterprise_bench import (
    EnterpriseBenchDataError,
    default_data_root,
)
from business_ops.reports import (
    AccountRiskQuery,
    Currency,
    PipelineChangeQuery,
    ProductRiskQuery,
    TicketPriority,
    account_risk_report,
    pipeline_change_report,
    product_risk_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-analytics",
        description="Run deterministic business analysis without an AI model.",
    )
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    commands = parser.add_subparsers(dest="command", required=True)

    account_risk = commands.add_parser(
        "account-risk", description="Rank ARR exposed to open priority support tickets."
    )
    account_risk.add_argument("--top", type=int, default=5)
    account_risk.add_argument("--priority", nargs="+", default=["p1"])

    product_risk = commands.add_parser(
        "product-risk", description="Rank product areas by ARR exposed through support tickets."
    )
    product_risk.add_argument("--top", type=int, default=10)
    product_risk.add_argument("--priority", nargs="+", default=["p0", "p1"])

    pipeline = commands.add_parser(
        "pipeline-change", description="Compare closed-won opportunity ACV across two periods."
    )
    pipeline.add_argument("--current-start", type=date.fromisoformat, default=date(2026, 1, 1))
    pipeline.add_argument("--current-end", type=date.fromisoformat, default=date(2026, 3, 31))
    pipeline.add_argument("--previous-start", type=date.fromisoformat, default=date(2025, 10, 1))
    pipeline.add_argument("--previous-end", type=date.fromisoformat, default=date(2025, 12, 31))
    pipeline.add_argument("--stage", default="closed_won")
    pipeline.add_argument("--currency", default="USD")
    pipeline.add_argument("--top", type=int, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "account-risk":
            report = account_risk_report(
                args.data_root,
                AccountRiskQuery(
                    top_n=args.top,
                    priorities=[TicketPriority(value) for value in args.priority],
                ),
            )
        elif args.command == "product-risk":
            report = product_risk_report(
                args.data_root,
                ProductRiskQuery(
                    top_n=args.top,
                    priorities=[TicketPriority(value) for value in args.priority],
                ),
            )
        else:
            if args.stage != "closed_won":
                raise ValueError("pipeline-change supports only closed_won opportunities")
            report = pipeline_change_report(
                args.data_root,
                PipelineChangeQuery(
                    current_start=args.current_start,
                    current_end=args.current_end,
                    previous_start=args.previous_start,
                    previous_end=args.previous_end,
                    top_n=args.top,
                    currency=Currency(args.currency),
                ),
            )
    except (EnterpriseBenchDataError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
