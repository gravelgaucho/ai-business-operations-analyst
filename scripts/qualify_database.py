from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from business_ops.datasets.download import ENTERPRISE_BENCH, verify_dataset
from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.datasets.repository import JsonEnterpriseBenchRepository
from business_ops.datasets.sqlite_store import (
    SqliteEnterpriseBenchRepository,
    _read_only_connection,
    build_database,
    default_database_path,
)
from business_ops.reports import (
    AccountRiskQuery,
    PipelineChangeQuery,
    ProductRiskQuery,
    SupportPipelineLinkQuery,
    account_risk_report,
    pipeline_change_report,
    product_risk_report,
    support_pipeline_link_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT_ROOT / "artifacts" / "stage6_qualification.json"


def timed_report(
    function: Callable[[Any, Any], Any], repository: Any, query: Any
) -> tuple[Any, float]:
    started = time.perf_counter()
    result = function(repository, query)
    return result, round((time.perf_counter() - started) * 1000, 3)


def main() -> int:
    source_root = default_data_root()
    database_path = default_database_path()
    verify_dataset(source_root)

    build_started = time.perf_counter()
    summary = build_database(source_root, database_path, force=True)
    build_milliseconds = round((time.perf_counter() - build_started) * 1000, 3)
    json_repository = JsonEnterpriseBenchRepository(source_root)
    sql_repository = SqliteEnterpriseBenchRepository(database_path, source_root=source_root)

    pipeline = PipelineChangeQuery(
        current_start=date(2026, 1, 1),
        current_end=date(2026, 3, 31),
        previous_start=date(2025, 10, 1),
        previous_end=date(2025, 12, 31),
        top_n=10,
        currency="USD",
    )
    cases = (
        ("account_risk", account_risk_report, AccountRiskQuery(top_n=10, priorities=["p1"])),
        (
            "product_risk",
            product_risk_report,
            ProductRiskQuery(top_n=10, priorities=["p0", "p1"]),
        ),
        ("pipeline_change", pipeline_change_report, pipeline),
        (
            "support_pipeline_overlap",
            support_pipeline_link_report,
            SupportPipelineLinkQuery(
                **pipeline.model_dump(exclude={"top_n"}),
                top_n_decliners=10,
                priorities=["p1"],
            ),
        ),
    )

    parity: dict[str, dict[str, object]] = {}
    for name, function, query in cases:
        json_report, json_ms = timed_report(function, json_repository, query)
        sql_report, sql_ms = timed_report(function, sql_repository, query)
        parity[name] = {
            "passed": json_report == sql_report,
            "json_milliseconds": json_ms,
            "sqlite_milliseconds": sql_ms,
        }

    with _read_only_connection(database_path) as connection:
        query_plan = [
            row[3]
            for row in connection.execute(
                """
                EXPLAIN QUERY PLAN
                SELECT account_id, acv FROM opportunities
                WHERE stage = ? AND currency = ?
                  AND target_close_date BETWEEN ? AND ?
                """,
                ("closed_won", "USD", "2026-01-01", "2026-03-31"),
            )
        ]
        try:
            connection.execute(
                "INSERT INTO accounts VALUES (999999, 'X', 'Unsafe', 'Nowhere', 0)"
            )
            read_only = False
        except sqlite3.OperationalError:
            read_only = True

    checks = {
        "approved_source_verified": summary.source_commit == ENTERPRISE_BENCH.source_commit
        and summary.source_sha256 == ENTERPRISE_BENCH.sha256,
        "expected_row_counts": summary.accounts == 42
        and summary.opportunities == 8_704
        and summary.tickets == 32_768
        and summary.product_parts == 40
        and summary.ticket_components == 32_768,
        "all_report_parity": all(item["passed"] for item in parity.values()),
        "read_only_runtime": read_only,
        "indexed_period_filter": any(
            "idx_opportunities_stage_currency_date" in step for step in query_plan
        ),
    }
    artifact = {
        "stage": 6,
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "name": ENTERPRISE_BENCH.name,
            "source_commit": ENTERPRISE_BENCH.source_commit,
            "sha256": ENTERPRISE_BENCH.sha256,
            "license": ENTERPRISE_BENCH.license,
            "synthetic": ENTERPRISE_BENCH.synthetic,
        },
        "sqlite_version": sqlite3.sqlite_version,
        "database": summary.model_dump(mode="json"),
        "build_milliseconds": build_milliseconds,
        "parity": parity,
        "query_plan": query_plan,
        "checks": checks,
        "all_passed": all(checks.values()),
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2))
    return 0 if artifact["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
