from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from business_ops.analyst import AnalyticsAgentError, run_analysis
from business_ops.config import Settings
from business_ops.datasets.enterprise_bench import default_data_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-analyze",
        description="Answer a business question with bounded, read-only analytics tools.",
    )
    parser.add_argument("question", help="The business question to investigate.")
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--model", help="Override MODEL_ID for this request.")
    parser.add_argument("--base-url", help="Override BASE_URL for this request.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    defaults = Settings.from_environment()
    settings = Settings(
        model_id=args.model or defaults.model_id,
        base_url=(args.base_url or defaults.base_url).rstrip("/"),
        timeout_seconds=defaults.timeout_seconds,
    )
    try:
        result = run_analysis(args.question, settings=settings, data_root=args.data_root)
    except (AnalyticsAgentError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
