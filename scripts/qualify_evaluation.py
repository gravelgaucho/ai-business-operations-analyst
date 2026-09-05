from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from business_ops.catalog import DEFAULT_CATALOG
from business_ops.config import Settings
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.datasets.sqlite_store import default_database_path
from business_ops.evaluation import DEFAULT_SCENARIOS, run_evaluation_suite
from business_ops.investigation import run_investigation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT_ROOT / "artifacts" / "stage11_qualification.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Stage 11 cross-modal local-model reliability scenarios."
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[item.scenario_id for item in DEFAULT_SCENARIOS],
        help="Run only this scenario; repeat to select more than one.",
    )
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--output", type=Path, default=ARTIFACT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = tuple(
        scenario
        for scenario in DEFAULT_SCENARIOS
        if not args.scenario or scenario.scenario_id in args.scenario
    )
    settings = Settings.from_environment()
    data_root = default_data_root()

    suite = run_evaluation_suite(
        lambda question: run_investigation(
            question,
            settings=settings,
            data_root=data_root,
            database_path=args.database,
        ),
        selected,
    )
    artifact = {
        "stage": 11,
        "evidence_schema_version": "1.0",
        "capability_catalog_version": DEFAULT_CATALOG.catalog_version,
        "capability_catalog_digest": DEFAULT_CATALOG.catalog_digest,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": settings.model_id,
        "base_url": settings.base_url,
        "dataset": {
            "name": ENTERPRISE_BENCH.name,
            "source_commit": ENTERPRISE_BENCH.source_commit,
            "license": ENTERPRISE_BENCH.license,
            "synthetic": ENTERPRISE_BENCH.synthetic,
        },
        "suite": suite.model_dump(mode="json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")

    summary = {
        "all_passed": suite.all_passed,
        "passed_scenarios": suite.passed_scenarios,
        "total_scenarios": suite.total_scenarios,
        "elapsed_seconds": suite.elapsed_seconds,
        "scenarios": [
            {
                "scenario_id": run.scenario.scenario_id,
                "passed": bool(run.evaluation and run.evaluation.passed),
                "score_percent": (
                    run.evaluation.score_percent if run.evaluation is not None else 0.0
                ),
                "elapsed_seconds": run.elapsed_seconds,
                "error": run.error,
            }
            for run in suite.runs
        ],
    }
    print(json.dumps(summary, indent=2))
    print(f"Evidence: {args.output}")
    return 0 if suite.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
