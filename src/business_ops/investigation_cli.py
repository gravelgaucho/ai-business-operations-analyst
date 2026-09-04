from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from business_ops.config import Settings
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.investigation import InvestigationError, run_investigation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-investigate",
        description="Plan and run a bounded, evidence-backed business investigation.",
    )
    parser.add_argument("question", help="The business question to investigate.")
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--database", type=Path, help="Use a verified read-only SQLite store.")
    parser.add_argument("--model", help="Override MODEL_ID for this investigation.")
    parser.add_argument("--base-url", help="Override BASE_URL for this investigation.")
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
        result = run_investigation(
            args.question,
            settings=settings,
            data_root=args.data_root,
            database_path=args.database,
        )
    except (InvestigationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
