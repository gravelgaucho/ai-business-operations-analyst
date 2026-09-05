from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from business_ops.datasets.documents import DocumentError, DocumentSearchQuery
from business_ops.datasets.download import DatasetImportError, verify_dataset
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.reports import document_search_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops-documents",
        description="Search approved published internal documents with exact citations.",
    )
    parser.add_argument("query", help="Plain-text terms; document content is never executed.")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = verify_dataset(args.data_root.resolve())
        query = DocumentSearchQuery(query=args.query, top_k=args.top)
        report = document_search_report(root, query)
    except (DatasetImportError, DocumentError, ValidationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
