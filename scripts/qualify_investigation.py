from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import psutil

from business_ops.config import Settings
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.investigation import AnalysisKind, run_investigation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT_ROOT / "artifacts" / "stage5_qualification.json"
QUESTION = (
    "Did open P1 support issues explain the Q1 2026 decline in closed-won USD "
    "opportunity ACV versus Q4 2025?"
)


def find_server(settings: Settings) -> psutil.Process | None:
    configured_pid = os.getenv("BUSINESS_OPS_SERVER_PID")
    if configured_pid:
        try:
            return psutil.Process(int(configured_pid))
        except (ValueError, psutil.NoSuchProcess):
            return None
    port = urlparse(settings.base_url).port or 8080
    try:
        processes = psutil.process_iter(["pid", "cmdline"])
    except PermissionError:
        return None
    for process in processes:
        try:
            command = " ".join(process.info["cmdline"] or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if "mlx_vlm.server" in command and f"--port {port}" in command:
            return process
    return None


class MemorySampler:
    def __init__(self, process: psutil.Process | None) -> None:
        self.process = process
        self.peak_rss_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self._stop.wait(0.1):
            if self.process is None:
                continue
            try:
                self.peak_rss_bytes = max(
                    self.peak_rss_bytes, self.process.memory_info().rss
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                return

    def __enter__(self) -> MemorySampler:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join()


def main() -> int:
    settings = Settings.from_environment()
    server = find_server(settings)
    started = time.perf_counter()
    error: str | None = None
    state = None
    with MemorySampler(server) as memory:
        try:
            state = run_investigation(QUESTION, settings=settings)
        except Exception as exc:  # qualification must preserve diagnostic evidence
            error = f"{type(exc).__name__}: {exc}"
    elapsed_seconds = round(time.perf_counter() - started, 3)

    checks: dict[str, bool] = {}
    if state is not None:
        used = {action.name for action in state.actions if action.returned}
        expected_hypotheses = {item.hypothesis_id for item in state.plan.hypotheses}
        assessed_hypotheses = {
            item.hypothesis_id for item in state.conclusion.hypothesis_assessments
        }
        pipeline = next(
            (
                item.content
                for item in state.observations
                if item.tool_name == AnalysisKind.CLOSED_WON_PIPELINE
            ),
            {},
        )
        overlap = next(
            (
                item.content
                for item in state.observations
                if item.tool_name == AnalysisKind.SUPPORT_PIPELINE_OVERLAP
            ),
            {},
        )
        conclusion_text = state.conclusion.model_dump_json().lower()
        checks = {
            "bounded_distinct_analyses": 2 <= len(used) <= 4,
            "pipeline_baseline_executed": AnalysisKind.CLOSED_WON_PIPELINE.value in used,
            "cross_system_test_executed": (
                AnalysisKind.SUPPORT_PIPELINE_OVERLAP.value in used
            ),
            "all_actions_returned": len(state.actions) == len(state.observations),
            "pipeline_values_exact": pipeline.get("comparison", {}).get("baseline")
            == 80_700_000
            and pipeline.get("comparison", {}).get("current") == 31_175_000,
            "overlap_values_present": "overlap_share_of_top_decline_change_percent"
            in overlap,
            "all_hypotheses_assessed": expected_hypotheses == assessed_hypotheses,
            "causal_restraint": all(
                item.status == "inconclusive"
                for item in state.conclusion.hypothesis_assessments
            )
            and state.conclusion.confidence != "high",
            "no_false_statistical_claim": "statistical significance" not in conclusion_text
            and "statistically significant" not in conclusion_text,
        }

    artifact = {
        "stage": 5,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": settings.model_id,
        "base_url": settings.base_url,
        "dataset": {
            "name": ENTERPRISE_BENCH.name,
            "source_commit": ENTERPRISE_BENCH.source_commit,
            "license": ENTERPRISE_BENCH.license,
            "synthetic": ENTERPRISE_BENCH.synthetic,
        },
        "question": QUESTION,
        "checks": checks,
        "all_passed": bool(checks) and all(checks.values()) and error is None,
        "elapsed_seconds": elapsed_seconds,
        "server_pid": server.pid if server else None,
        "peak_server_rss_bytes": memory.peak_rss_bytes or None,
        "peak_server_rss_gib": (
            round(memory.peak_rss_bytes / 1024**3, 3) if memory.peak_rss_bytes else None
        ),
        "state": state.model_dump(mode="json") if state else None,
        "error": error,
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "all_passed": artifact["all_passed"],
                "checks": checks,
                "elapsed_seconds": elapsed_seconds,
                "peak_server_rss_gib": artifact["peak_server_rss_gib"],
                "error": error,
            },
            indent=2,
        )
    )
    print(f"Evidence: {ARTIFACT}")
    return 0 if artifact["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
