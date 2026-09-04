from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from business_ops.catalog import DEFAULT_CATALOG, CapabilityCatalog
from business_ops.catalog_cli import main as catalog_cli_main
from business_ops.investigation import planner_instructions


def test_default_catalog_is_self_validating_and_complete() -> None:
    restored = CapabilityCatalog.model_validate_json(DEFAULT_CATALOG.model_dump_json())

    assert restored.catalog_version == "stage-9-v1"
    assert len(restored.sources) == 1
    assert len(restored.entities) == 4
    assert len(restored.metrics) == 5
    assert restored.capability_ids == {
        "get_account_support_risk",
        "get_product_area_support_risk",
        "compare_closed_won_pipeline",
        "test_support_pipeline_overlap",
    }
    assert all(item.deterministic and item.read_only for item in restored.capabilities)
    assert restored.sources[0].classification == "public_synthetic"


def test_catalog_rejects_tampered_semantics_without_a_new_digest() -> None:
    tampered = DEFAULT_CATALOG.model_dump(mode="python")
    tampered["metrics"][3]["semantic_boundary"] = "This is recognized revenue."

    with pytest.raises(ValidationError, match="catalog digest"):
        CapabilityCatalog.model_validate(tampered)


def test_capability_definitions_drive_evidence_method_and_locators() -> None:
    capability = DEFAULT_CATALOG.capability("test_support_pipeline_overlap")

    assert capability.implementation == "business_ops.reports.support_pipeline_link_report"
    assert capability.method_version == "stage-9-v1"
    assert capability.json_files == (
        "crm_json_data/accounts.json",
        "crm_json_data/opportunities.json",
        "crm_json_data/tickets.json",
    )
    assert capability.sqlite_tables == ("accounts", "opportunities", "tickets")
    assert "causation" in capability.interpretation_boundary


def test_planner_receives_compact_approved_catalog() -> None:
    instructions = planner_instructions()

    assert DEFAULT_CATALOG.catalog_digest in instructions
    assert "test_support_pipeline_overlap" in instructions
    assert "Association screen only" in instructions
    assert ENTERPRISE_NAME in instructions


def test_catalog_cli_prints_machine_readable_full_and_planning_views(capsys) -> None:
    assert catalog_cli_main([]) == 0
    full = json.loads(capsys.readouterr().out)
    assert full["catalog_digest"] == DEFAULT_CATALOG.catalog_digest
    assert len(full["metrics"]) == 5

    assert catalog_cli_main(["--planning-view"]) == 0
    planning = json.loads(capsys.readouterr().out)
    assert planning["catalog_digest"] == DEFAULT_CATALOG.catalog_digest
    assert len(planning["available_capabilities"]) == 4
    assert "metrics" not in planning


ENTERPRISE_NAME = "DevRev Enterprise-Bench / Maple Payments"
