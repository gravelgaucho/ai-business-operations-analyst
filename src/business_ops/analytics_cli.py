from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from business_ops.analytics import (
    DateRange,
    analyze_concentration,
    compare_periods,
    segment_performance,
)
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.datasets.enterprise_bench import (
    EnterpriseBenchDataError,
    default_data_root,
    opportunity_metric_records,
    rank_account_risk,
    rank_product_area_risk,
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


def _source() -> dict[str, object]:
    return {
        "dataset": ENTERPRISE_BENCH.name,
        "source_commit": ENTERPRISE_BENCH.source_commit,
        "license": ENTERPRISE_BENCH.license,
        "synthetic": ENTERPRISE_BENCH.synthetic,
    }


def _account_risk_report(args: argparse.Namespace) -> dict[str, object]:
    if args.top < 1:
        raise ValueError("top must be positive")
    priorities = frozenset(args.priority)
    all_results = rank_account_risk(args.data_root, priorities=priorities, top_n=10_000)
    return {
        "question": f"Which {args.top} accounts have the most ARR exposed to open "
        f"{'/'.join(sorted(priorities)).upper()} support tickets?",
        "source": _source(),
        "calculation": (
            "Rank distinct account ARR for accounts with at least one matching open ticket; "
            "multiple tickets do not multiply ARR."
        ),
        "summary": {
            "affected_accounts": len(all_results),
            "total_arr_at_risk": sum(item.arr_at_risk for item in all_results),
        },
        "results": [item.model_dump(mode="json") for item in all_results[: args.top]],
    }


def _product_risk_report(args: argparse.Namespace) -> dict[str, object]:
    priorities = frozenset(args.priority)
    results = rank_product_area_risk(
        args.data_root, priorities=priorities, top_n=args.top
    )
    return {
        "question": "Which product areas have the most ARR exposed through open "
        f"{'/'.join(sorted(priorities)).upper()} support tickets?",
        "source": _source(),
        "calculation": (
            "Join open tickets to product components and accounts, then sum each affected "
            "account's ARR once per component."
        ),
        "results": [item.model_dump(mode="json") for item in results],
    }


def _pipeline_report(args: argparse.Namespace) -> dict[str, object]:
    if args.top < 1:
        raise ValueError("top must be positive")
    current = DateRange(start=args.current_start, end=args.current_end)
    previous = DateRange(start=args.previous_start, end=args.previous_end)
    records = opportunity_metric_records(
        args.data_root, stage=args.stage, currency=args.currency
    )
    comparison = compare_periods(records, current, previous)
    declines = [
        item for item in comparison.contributors if item.variance.absolute_change < 0
    ][: args.top]
    return {
        "question": (
            f"Which accounts contributed most to the change in {args.stage} "
            f"{args.currency} opportunity ACV?"
        ),
        "source": _source(),
        "metric_definition": (
            "Opportunity ACV grouped by target close date and current final stage. "
            "This is not recognized revenue."
        ),
        "comparison": comparison.total.model_dump(mode="json"),
        "current_period": current.model_dump(mode="json"),
        "previous_period": previous.model_dump(mode="json"),
        "largest_decline_contributors": [item.model_dump(mode="json") for item in declines],
        "current_segments": [
            item.model_dump(mode="json")
            for item in segment_performance(records, period=current)
        ],
        "current_concentration": analyze_concentration(
            records, period=current, top_n=args.top
        ).model_dump(mode="json"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "account-risk":
            report = _account_risk_report(args)
        elif args.command == "product-risk":
            report = _product_risk_report(args)
        else:
            report = _pipeline_report(args)
    except (EnterpriseBenchDataError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
