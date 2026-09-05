from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from business_ops.datasets.enterprise_bench import default_data_root
from business_ops.testbed import (
    DEFAULT_TESTBED,
    CoverageStatus,
    ScenarioReadiness,
    active_asset_locators,
    inventory_testbed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT_ROOT / "artifacts" / "stage12_testbed_qualification.json"

EXPECTED_COUNTS = {
    "crm_accounts": (42, 42),
    "crm_opportunities": (8_704, 8_704),
    "crm_tickets": (32_768, 32_768),
    "product_parts": (40, 40),
    "internal_documents": (8, 7),
    "crm_users": (289, 289),
    "product_users": (5, 5),
    "product_issues": (8_448, 8_448),
    "product_conversations": (23, 23),
    "product_comments": (26, 26),
    "knowledge_articles": (55, 55),
    "account_transcripts": (3, 3),
}


def main() -> int:
    report = inventory_testbed(default_data_root())
    actual_counts = {
        item.asset_id: (item.record_count, item.eligible_record_count)
        for item in report.assets
        if item.present
    }
    registered = active_asset_locators()
    active_primary = {
        asset.primary_locator
        for asset in DEFAULT_TESTBED.assets
        if asset.status == CoverageStatus.ACTIVE
    }
    planned_primary = {
        asset.primary_locator
        for asset in DEFAULT_TESTBED.assets
        if asset.status == CoverageStatus.PLANNED
    }
    readiness = {item.scenario_id: item.readiness for item in report.scenarios}
    checks = {
        "approved_source_verified": report.source_verified,
        "expected_source_counts": actual_counts == EXPECTED_COUNTS,
        "coverage_states_complete": report.summary.active_assets == 5
        and report.summary.available_assets == 7
        and report.summary.planned_assets == 9,
        "cross_source_relationships_resolve": all(
            check.passed for check in report.relationship_checks
        ),
        "active_assets_registered": active_primary <= registered,
        "planned_assets_not_executable": planned_primary.isdisjoint(registered),
        "current_scenarios_qualified": (
            readiness["support_pipeline_causal_screen"] == ScenarioReadiness.QUALIFIED
            and readiness["document_grounded_support_review"]
            == ScenarioReadiness.QUALIFIED
        ),
        "new_source_scenario_is_partial": (
            readiness["product_issue_customer_impact"] == ScenarioReadiness.PARTIAL
        ),
        "financial_scenarios_are_explicitly_blocked": (
            readiness["bookings_revenue_divergence"] == ScenarioReadiness.BLOCKED
            and readiness["transaction_contract_pricing_review"] == ScenarioReadiness.BLOCKED
        ),
    }
    artifact = {
        "stage": 12,
        "generated_at": datetime.now(UTC).isoformat(),
        "testbed_version": DEFAULT_TESTBED.testbed_version,
        "testbed_digest": DEFAULT_TESTBED.testbed_digest,
        "checks": checks,
        "all_passed": all(checks.values()),
        "inventory": report.model_dump(mode="json"),
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2))
    return 0 if artifact["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
