from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from business_ops.catalog import DEFAULT_CATALOG
from business_ops.testbed import (
    DEFAULT_TESTBED,
    BusinessEvidenceTestbed,
    CoverageStatus,
    ScenarioReadiness,
    active_asset_locators,
    inventory_testbed,
)
from business_ops.testbed_cli import main as run_testbed_cli


def test_default_testbed_is_self_validating_and_separates_coverage_states() -> None:
    restored = BusinessEvidenceTestbed.model_validate_json(DEFAULT_TESTBED.model_dump_json())

    assert restored.testbed_version == "stage-12-v1"
    assert len(restored.entities) == 19
    assert len(restored.assets) == 21
    assert len(restored.relationships) == 16
    assert len(restored.metrics) == 14
    assert len(restored.scenarios) == 5
    assert sum(asset.status == CoverageStatus.ACTIVE for asset in restored.assets) == 5
    assert sum(asset.status == CoverageStatus.AVAILABLE for asset in restored.assets) == 7
    assert sum(asset.status == CoverageStatus.PLANNED for asset in restored.assets) == 9


def test_active_assets_are_backed_by_current_catalog_but_planned_assets_are_not() -> None:
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

    assert active_primary <= registered
    assert planned_primary.isdisjoint(registered)
    assert all("maple_finance_extension" in locator for locator in planned_primary)
    assert "bookings" not in {metric.metric_id for metric in DEFAULT_CATALOG.metrics}


def test_scenario_readiness_is_derived_from_required_metric_coverage() -> None:
    readiness = {
        scenario.scenario_id: DEFAULT_TESTBED.scenario_readiness(scenario)
        for scenario in DEFAULT_TESTBED.scenarios
    }

    assert readiness["support_pipeline_causal_screen"] == ScenarioReadiness.QUALIFIED
    assert readiness["document_grounded_support_review"] == ScenarioReadiness.QUALIFIED
    assert readiness["product_issue_customer_impact"] == ScenarioReadiness.PARTIAL
    assert readiness["bookings_revenue_divergence"] == ScenarioReadiness.BLOCKED
    assert readiness["transaction_contract_pricing_review"] == ScenarioReadiness.BLOCKED


def test_testbed_rejects_tampered_semantics_without_a_new_digest() -> None:
    tampered = DEFAULT_TESTBED.model_dump(mode="python")
    tampered["metrics"][7]["semantic_boundary"] = "Bookings are recognized revenue."

    with pytest.raises(ValidationError, match="testbed digest"):
        BusinessEvidenceTestbed.model_validate(tampered)


def test_inventory_counts_present_records_and_reports_planned_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for asset in DEFAULT_TESTBED.assets:
        if asset.status == CoverageStatus.PLANNED:
            continue
        path = tmp_path / asset.primary_locator
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [{"status": "published"}, {"status": "draft"}]
        path.write_text(json.dumps(records), encoding="utf-8")
    monkeypatch.setattr("business_ops.testbed.verify_dataset", lambda root, spec: root)

    report = inventory_testbed(tmp_path, check_relationships=False)

    assert report.source_verified is True
    assert report.summary.present_source_records == 24
    assert report.summary.active_assets == 5
    assert report.summary.available_assets == 7
    assert report.summary.planned_assets == 9
    assert all(
        not item.present
        for item in report.assets
        if item.status == CoverageStatus.PLANNED
    )
    documents = next(item for item in report.assets if item.asset_id == "internal_documents")
    assert documents.record_count == 2
    assert documents.eligible_record_count == 1


def test_testbed_cli_prints_machine_readable_spec(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_testbed_cli(["--spec-only"]) == 0
    value = json.loads(capsys.readouterr().out)

    assert value["testbed_digest"] == DEFAULT_TESTBED.testbed_digest
    assert len(value["assets"]) == 21
    assert value["scenarios"][3]["scenario_id"] == "bookings_revenue_divergence"
