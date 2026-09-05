from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from business_ops.testbed import DEFAULT_TESTBED, inventory_testbed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-testbed",
        description="Inspect current and planned business-data coverage.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/enterprise_bench"),
        help="Verified Maple Payments source directory.",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help="Print the versioned testbed specification without inspecting local data.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    value = (
        DEFAULT_TESTBED
        if args.spec_only
        else inventory_testbed(args.data_root, testbed=DEFAULT_TESTBED)
    )
    print(json.dumps(value.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
