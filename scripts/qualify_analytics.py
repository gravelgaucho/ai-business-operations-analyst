from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from business_ops.analytics import DateRange, compare_periods
from business_ops.datasets.download import ENTERPRISE_BENCH, verify_dataset
from business_ops.datasets.enterprise_bench import (
    default_data_root,
    opportunity_metric_records,
    rank_account_risk,
    rank_product_area_risk,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    started = time.perf_counter()
    root = default_data_root()
    verify_dataset(root)
    source = json.loads((root / ".source.json").read_text(encoding="utf-8"))
    accounts = rank_account_risk(root, top_n=10_000)
    products = rank_product_area_risk(root, top_n=10_000)
    opportunities = opportunity_metric_records(root)
    comparison = compare_periods(
        opportunities,
        DateRange(start=date(2026, 1, 1), end=date(2026, 3, 31)),
        DateRange(start=date(2025, 10, 1), end=date(2025, 12, 31)),
    )
    checks = {
        "verified_source": source.get("sha256") == ENTERPRISE_BENCH.sha256,
        "synthetic_source": source.get("synthetic") is True,
        "account_risk_join": (
            len(accounts) == 8 and sum(x.arr_at_risk for x in accounts) == 1_041_000
        ),
        "product_risk_join": bool(products)
        and products[0].component_name == "Subscription Lifecycle Management"
        and products[0].arr_at_risk == 732_000,
        "period_comparison": comparison.total.baseline == 80_700_000
        and comparison.total.current == 31_175_000,
    }
    artifact = {
        "dataset": ENTERPRISE_BENCH.name,
        "source_commit": ENTERPRISE_BENCH.source_commit,
        "sha256": ENTERPRISE_BENCH.sha256,
        "checks": checks,
        "all_passed": all(checks.values()),
        "metrics": {
            "closed_won_usd_opportunities": len(opportunities),
            "accounts_with_open_p1_tickets": len(accounts),
            "distinct_arr_at_risk": sum(item.arr_at_risk for item in accounts),
            "highest_risk_product_area": products[0].model_dump(mode="json"),
            "q1_2026_vs_q4_2025": comparison.total.model_dump(mode="json"),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }
    artifact_path = PROJECT_ROOT / "artifacts" / "stage3_qualification.json"
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2))
    return 0 if artifact["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
