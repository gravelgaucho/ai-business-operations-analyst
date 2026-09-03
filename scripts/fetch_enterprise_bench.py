from __future__ import annotations

import argparse
import sys
from pathlib import Path

from business_ops.datasets import DatasetImportError, import_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = PROJECT_ROOT / "data" / "enterprise_bench"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the verified Maple Payments dataset.")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument(
        "--archive",
        type=Path,
        help="Use a local archive; it must match the pinned official SHA-256 digest.",
    )
    args = parser.parse_args()
    try:
        destination = import_dataset(args.destination, archive_path=args.archive)
    except DatasetImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Verified synthetic dataset ready at {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
