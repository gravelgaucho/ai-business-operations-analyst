from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from business_ops.analyst import run_analysis
from business_ops.config import Settings
from business_ops.datasets.download import ENTERPRISE_BENCH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT_ROOT / "artifacts" / "stage4_qualification.json"


@dataclass(frozen=True)
class QualificationCase:
    name: str
    question: str
    expected_tool: str
    expected_answer_fragments: tuple[str, ...]


@dataclass
class Check:
    name: str
    passed: bool
    elapsed_seconds: float
    expected_tool: str
    tool_calls: list[dict[str, object]]
    answer: str
    usage: dict[str, int]
    error: str | None = None


CASES = (
    QualificationCase(
        name="account_support_risk",
        question="Which five accounts have the most ARR exposed to open P1 support tickets?",
        expected_tool="get_account_support_risk",
        expected_answer_fragments=("Vantara", "432"),
    ),
    QualificationCase(
        name="product_area_support_risk",
        question=(
            "Which five product areas have the most ARR exposed through open P0 or P1 "
            "support tickets?"
        ),
        expected_tool="get_product_area_support_risk",
        expected_answer_fragments=("Subscription Lifecycle Management", "732"),
    ),
    QualificationCase(
        name="pipeline_period_comparison",
        question=(
            "Compare closed-won USD opportunity ACV for Q1 2026 against Q4 2025. "
            "Identify the largest account decline contributor."
        ),
        expected_tool="compare_closed_won_pipeline",
        expected_answer_fragments=("MercadoPay", "61.37"),
    ),
)


def run_case(case: QualificationCase) -> Check:
    started = time.perf_counter()
    try:
        result = run_analysis(case.question)
        tool_names = [call.name for call in result.tool_calls if call.returned]
        missing_fragments = [
            fragment
            for fragment in case.expected_answer_fragments
            if fragment.casefold() not in result.answer.casefold()
        ]
        passed = case.expected_tool in tool_names and not missing_fragments
        error = None
        if case.expected_tool not in tool_names:
            error = f"expected {case.expected_tool}, got {tool_names}"
        elif missing_fragments:
            error = f"answer omitted expected evidence: {missing_fragments}"
        return Check(
            name=case.name,
            passed=passed,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            expected_tool=case.expected_tool,
            tool_calls=[call.model_dump(mode="json") for call in result.tool_calls],
            answer=result.answer,
            usage=result.usage.model_dump(mode="json"),
            error=error,
        )
    except Exception as exc:  # qualification must preserve per-case evidence
        return Check(
            name=case.name,
            passed=False,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            expected_tool=case.expected_tool,
            tool_calls=[],
            answer="",
            usage={},
            error=f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    settings = Settings.from_environment()
    checks = [run_case(case) for case in CASES]
    artifact = {
        "stage": 4,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": settings.model_id,
        "base_url": settings.base_url,
        "dataset": {
            "name": ENTERPRISE_BENCH.name,
            "source_commit": ENTERPRISE_BENCH.source_commit,
            "license": ENTERPRISE_BENCH.license,
            "synthetic": ENTERPRISE_BENCH.synthetic,
        },
        "checks": [asdict(check) for check in checks],
        "summary": {
            "passed": sum(check.passed for check in checks),
            "total": len(checks),
            "all_passed": all(check.passed for check in checks),
            "elapsed_seconds": round(sum(check.elapsed_seconds for check in checks), 3),
        },
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    for check in checks:
        state = "PASS" if check.passed else "FAIL"
        print(f"{state:4} {check.name:32} {check.elapsed_seconds:8.2f}s")
        if check.error:
            print(f"     {check.error}")
    print(f"Evidence: {ARTIFACT}")
    return 0 if artifact["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
