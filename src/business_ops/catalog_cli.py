from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from business_ops.catalog import DEFAULT_CATALOG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-catalog",
        description="Inspect approved business data sources and analytical capabilities.",
    )
    parser.add_argument(
        "--planning-view",
        action="store_true",
        help="Show the compact catalog supplied to the investigation planner.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    value = (
        DEFAULT_CATALOG.planning_context()
        if args.planning_view
        else DEFAULT_CATALOG.model_dump(mode="json")
    )
    print(json.dumps(value, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
