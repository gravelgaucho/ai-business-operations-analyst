from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from business_ops.catalog import catalog_digest
from business_ops.datasets.sqlite_store import build_database
from business_ops.investigation import (
    InvestigationError,
    InvestigationPlan,
    create_audit_bundle,
    create_planner,
    create_step_selector,
    create_synthesizer,
    decisive_causal_phrases,
    has_causal_attribution_language,
    has_revenue_metric_conflation,
    plan_introduces_unsupported_ranking_concentration,
    run_investigation,
)
from business_ops.investigation_cli import main as investigation_cli_main
from business_ops.provenance import AuditBundle, EvidenceRecord

QUESTION = "Did open P1 support issues explain the Q1 2026 pipeline decline versus Q4 2025?"

PLAN = {
    "question": {
        "question_type": "causal",
        "scope": "support_pipeline_relationship",
        "metric": "closed-won opportunity ACV",
        "time_period": "Q1 2026 versus Q4 2025",
        "entities": [],
        "requires_investigation": True,
        "missing_information": ["Ticket timing", "Opportunity stage history"],
        "normalized_question": QUESTION,
    },
    "objective": "Test whether support risk is concentrated among the largest decliners.",
    "hypotheses": [
        {
            "hypothesis_id": "H1",
            "statement": "Open P1 issues are concentrated among the largest ACV decliners.",
            "test": "Measure deterministic account overlap.",
        }
    ],
    "steps": [
        {
            "step_id": "step_1",
            "analysis": "compare_closed_won_pipeline",
            "purpose": "Establish the decline and contributors.",
            "success_criterion": "The period variance is measured.",
        },
        {
            "step_id": "step_2",
            "analysis": "test_support_pipeline_overlap",
            "purpose": "Test the cross-system overlap.",
            "success_criterion": "The overlap count and share are measured.",
        },
    ],
    "stop_conditions": ["Both measurements are available", "Required evidence is missing"],
}

PIPELINE_DECISION = {
    "analysis": "compare_closed_won_pipeline",
    "rationale": "Establish the size and account concentration of the decline first.",
    "current_start": "2026-01-01",
    "current_end": "2026-03-31",
    "previous_start": "2025-10-01",
    "previous_end": "2025-12-31",
    "top_n": 5,
    "top_n_decliners": 5,
    "priorities": ["p1"],
    "currency": "USD",
}

OVERLAP_DECISION = {
    "analysis": "test_support_pipeline_overlap",
    "rationale": "Test whether priority support risk is concentrated among those decliners.",
    "current_start": "2026-01-01",
    "current_end": "2026-03-31",
    "previous_start": "2025-10-01",
    "previous_end": "2025-12-31",
    "top_n": 5,
    "top_n_decliners": 5,
    "priorities": ["p1"],
    "currency": "USD",
}

PRODUCT_DECISION = {
    "analysis": "get_product_area_support_risk",
    "rationale": "Check whether support exposure is concentrated by product area.",
    "current_start": None,
    "current_end": None,
    "previous_start": None,
    "previous_end": None,
    "top_n": 5,
    "top_n_decliners": 5,
    "priorities": ["p1"],
    "currency": "USD",
}

ACCOUNT_DECISION = PRODUCT_DECISION | {
    "analysis": "get_account_support_risk",
    "rationale": "Check which accounts currently have open P1 support exposure.",
}

CONCLUSION = {
    "executive_summary": (
        "Closed-won ACV declined. The available evidence does not support attribution; "
        "causation remains unresolved."
    ),
    "findings": [
        {
            "finding_id": "F1",
            "statement": "Closed-won ACV declined from the previous period.",
            "claim_type": "verified_fact",
            "evidence_ids": ["__EVIDENCE_1__"],
        },
        {
            "finding_id": "F2",
            "statement": "The declining account also had an open P1 ticket.",
            "claim_type": "analytical_finding",
            "evidence_ids": ["__EVIDENCE_2__"],
        },
    ],
    "hypothesis_assessments": [
        {
            "hypothesis_id": "H1",
            "status": "inconclusive",
            "rationale": "Overlap is measurable, but ticket timing is unavailable.",
            "evidence_ids": ["__EVIDENCE_2__"],
        }
    ],
    "business_implications": [
        {
            "implication_id": "I1",
            "statement": "The overlap warrants focused review but not causal attribution.",
            "evidence_ids": ["__EVIDENCE_1__", "__EVIDENCE_2__"],
        }
    ],
    "recommendation": {
        "recommendation_id": "R1",
        "statement": "Review ticket timing before treating this as causal.",
        "rationale": "The measured overlap does not establish event sequence.",
        "evidence_ids": ["__EVIDENCE_2__"],
        "human_review_required": True,
    },
    "confidence": {
        "level": "medium",
        "rationale": "The calculations are verified, but causal timing is missing.",
        "evidence_coverage": "partial",
        "source_agreement": "not_assessed",
        "data_quality": "adequate",
    },
    "unresolved_questions": ["Did the ticket precede the opportunity change?"],
    "limitations": ["Set overlap does not establish causation."],
}


def write_records(root: Path, relative_path: str, records: list[dict[str, object]]) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    write_records(
        tmp_path,
        "crm_json_data/accounts.json",
        [{"account_id": "A", "account_name": "Alpha", "region": "East", "arr": 1000}],
    )
    write_records(
        tmp_path,
        "crm_json_data/tickets.json",
        [
            {
                "ticket_id": "T1",
                "account_id": "A",
                "priority": "p1",
                "status": "open",
                "components": ["P1"],
            }
        ],
    )
    write_records(
        tmp_path,
        "crm_json_data/opportunities.json",
        [
            {
                "account_id": "A",
                "stage": "closed_won",
                "currency": "USD",
                "acv": 1000,
                "target_close_date": "2025-12-15",
            },
            {
                "account_id": "A",
                "stage": "closed_won",
                "currency": "USD",
                "acv": 300,
                "target_close_date": "2026-01-15",
            },
        ],
    )
    write_records(
        tmp_path,
        "pm_json_data/maple_parts.json",
        [{"part_id": "P1", "title": "Checkout"}],
    )
    return tmp_path


def render_payload(payload: dict[str, object], messages: object) -> str:
    rendered = json.dumps(payload)
    evidence_ids = list(dict.fromkeys(re.findall(r"EV-[0-9a-f]{16}", repr(messages))))
    for index, value in enumerate(evidence_ids, start=1):
        rendered = rendered.replace(f"__EVIDENCE_{index}__", value)
    return rendered


def json_agent(payload: dict[str, object]):
    def model(messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(render_payload(payload, messages))])

    return FunctionModel(model)


def selector_agent(sequence: list[dict[str, object]]):
    decisions: Iterator[dict[str, object]] = iter(sequence)

    def model(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(decisions)))])

    return create_step_selector(FunctionModel(model))


def test_plan_rejects_single_analysis_disguised_as_multiple_steps() -> None:
    invalid = PLAN | {"steps": [PLAN["steps"][0], PLAN["steps"][0] | {"step_id": "step_2"}]}

    with pytest.raises(ValidationError, match="two distinct analyses"):
        InvestigationPlan.model_validate(invalid)


def test_causal_language_check_distinguishes_assertion_from_uncertainty() -> None:
    assert decisive_causal_phrases("Open P1 issues drove the ACV decline.") == (
        "drove the",
    )
    assert (
        decisive_causal_phrases(
            "The evidence cannot determine whether open P1 issues drove the ACV decline."
        )
        == ()
    )
    assert decisive_causal_phrases("The primary driver remains unknown.") == ()
    assert decisive_causal_phrases("Support issues were the primary driver.") == (
        "primary driver",
    )
    assert has_causal_attribution_language(
        "This descriptive result does not establish causation."
    ) is False
    assert has_causal_attribution_language("The analysis can establish causation.") is True
    assert has_causal_attribution_language(
        "The available evidence does not support attribution; causation remains unresolved."
    ) is True


def test_metric_check_allows_explicit_non_revenue_boundary() -> None:
    assert has_revenue_metric_conflation("Closed-won ACV is not recognized revenue.") is False
    assert has_revenue_metric_conflation("Revenue fell during the period.") is True


def test_controller_selects_two_analyses_and_preserves_visible_state(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    assert [action.name for action in state.actions] == [
        "compare_closed_won_pipeline",
        "test_support_pipeline_overlap",
    ]
    assert len(state.decisions) == 2
    assert len(state.observations) == 2
    assert len(state.evidence_ledger.records) == 2
    assert state.conclusion.findings[0].evidence_ids == [
        state.evidence_ledger.records[0].evidence_id
    ]
    assert state.observations[1].tool_name == "test_support_pipeline_overlap"
    assert "evidence gate is satisfied" in state.stop_reason
    assert state.usage.total_requests == 4
    assert state.usage.total_tool_calls == 2


def test_controller_combines_period_comparison_with_governed_breakdown(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    question = (
        "Compare Q1 2026 closed-won USD opportunity ACV with Q4 2025, then break "
        "Q1 2026 down by region."
    )
    plan = json.loads(json.dumps(PLAN))
    plan["question"] = {
        "question_type": "comparative",
        "scope": "opportunity_performance",
        "metric": "closed-won opportunity ACV",
        "time_period": "Q1 2026 versus Q4 2025",
        "entities": ["region"],
        "requires_investigation": True,
        "missing_information": [],
        "normalized_question": question,
    }
    plan["objective"] = "Measure the period change and identify the Q1 regional mix."
    plan["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "statement": "Q1 closed-won opportunity ACV is concentrated by region.",
            "test": "Compare periods and group Q1 ACV by the approved region dimension.",
        }
    ]
    plan["steps"] = [
        PLAN["steps"][0],
        {
            "step_id": "step_2",
            "analysis": "query_closed_won_opportunity_acv",
            "purpose": "Measure the Q1 regional breakdown.",
            "success_criterion": "The bounded regional values are returned.",
        },
    ]
    breakdown_decision = PIPELINE_DECISION | {
        "analysis": "query_closed_won_opportunity_acv",
        "rationale": "Group the requested current period by the approved region dimension.",
        "dimensions": ["region"],
        "top_n": 10,
    }
    conclusion = json.loads(json.dumps(CONCLUSION))
    conclusion["executive_summary"] = (
        "Closed-won opportunity ACV declined and the Q1 regional mix is measurable."
    )
    conclusion["findings"][0]["statement"] = (
        "Closed-won opportunity ACV declined from Q4 to Q1."
    )
    conclusion["findings"][1]["statement"] = (
        "The Q1 regional breakdown is reported by a governed query."
    )
    conclusion["hypothesis_assessments"][0] = {
        "hypothesis_id": "H1",
        "status": "supported",
        "rationale": "The requested regional grouping returned a measured result.",
        "evidence_ids": ["__EVIDENCE_2__"],
    }
    conclusion["business_implications"][0]["statement"] = (
        "The regional mix gives management a bounded review starting point."
    )
    conclusion["recommendation"]["statement"] = (
        "Have an operations leader review the period change and regional mix."
    )
    conclusion["recommendation"]["rationale"] = (
        "The deterministic reports identify the measured change and regional distribution."
    )
    conclusion["confidence"]["rationale"] = (
        "The values come from two deterministic reports over one verified snapshot."
    )
    conclusion["unresolved_questions"] = []
    conclusion["limitations"] = [
        "Closed-won opportunity ACV is not recognized revenue."
    ]

    state = run_investigation(
        question,
        planner=create_planner(json_agent(plan)),
        selector=selector_agent([PIPELINE_DECISION, breakdown_decision]),
        synthesizer=create_synthesizer(json_agent(conclusion)),
        data_root=dataset,
    )

    assert [action.name for action in state.actions] == [
        "compare_closed_won_pipeline",
        "query_closed_won_opportunity_acv",
    ]
    assert state.actions[1].arguments == {
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "dimensions": ["region"],
        "currency": "USD",
        "top_n": 10,
    }
    assert state.observations[1].content["rows"] == [
        {
            "dimensions": {"region": "East"},
            "closed_won_opportunity_acv": 300,
        }
    ]
    assert state.evidence_ledger.records[1].method.arguments == state.actions[1].arguments


def test_controller_combines_structured_exposure_with_cited_document_evidence(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    write_records(
        dataset,
        "internal_docs/msa_and_compliance.json",
        [
            {
                "document_id": "MSA-005",
                "status": "published",
                "created_at": "2024-01-01T00:00:00Z",
                "modified_at": "2026-01-01T00:00:00Z",
                "author_id": "USER-001",
                "content_format": "markdown",
                "audience": "internal",
                "title": "Maple Payments — Standard MSA Template",
                "content_file": "msa_standard_template.md",
            }
        ],
    )
    (dataset / "internal_docs" / "msa_standard_template.md").write_text(
        "# Standard MSA\n\n## 3.2 Response & Resolution Targets\n"
        "| Priority | Initial Response | Resolution | Coverage |\n"
        "| **P1** | 1 hour | 24 hours | 24/7 |\n",
        encoding="utf-8",
    )
    question = (
        "Which accounts should an operations leader review first because of open P1 support "
        "exposure, and what initial response and resolution commitments does the published "
        "Standard MSA specify for P1 issues?"
    )
    plan = json.loads(json.dumps(PLAN))
    plan["question"] = {
        "question_type": "prescriptive",
        "scope": "support_exposure_and_contract_commitment",
        "metric": "ARR exposure and P1 response commitments",
        "time_period": None,
        "entities": ["account", "internal_document"],
        "requires_investigation": True,
        "missing_information": [],
        "normalized_question": question,
    }
    plan["objective"] = "Prioritize accounts and retrieve the governing Standard MSA terms."
    plan["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "statement": "Published Standard MSA terms define P1 response commitments.",
            "test": "Retrieve a hashed passage from the manifest-approved published document.",
        }
    ]
    plan["steps"] = [
        {
            "step_id": "step_1",
            "analysis": "get_account_support_risk",
            "purpose": "Rank current account exposure.",
            "success_criterion": "A bounded account ranking is returned.",
        },
        {
            "step_id": "step_2",
            "analysis": "search_internal_documents",
            "purpose": "Retrieve the published Standard MSA P1 terms.",
            "success_criterion": "A hashed line-level passage is returned.",
        },
    ]
    document_decision = PRODUCT_DECISION | {
        "analysis": "search_internal_documents",
        "rationale": "Retrieve the exact published Standard MSA passage.",
        "search_query": "Standard MSA P1 initial response resolution",
        "document_top_k": 3,
    }
    conclusion = json.loads(json.dumps(CONCLUSION))
    conclusion["executive_summary"] = (
        "The account ranking identifies current P1 exposure, and the published Standard MSA "
        "specifies a 1-hour initial response and 24-hour resolution target with 24/7 coverage. "
        "Verify the applicable executed agreement before applying those reference terms."
    )
    conclusion["findings"][0] = {
        "finding_id": "F1",
        "statement": "The structured report ranks the current account exposure.",
        "claim_type": "verified_fact",
        "evidence_ids": ["__EVIDENCE_1__"],
    }
    conclusion["findings"][1] = {
        "finding_id": "F2",
        "statement": (
            "The published Standard MSA passage specifies a 1-hour P1 initial response and "
            "24-hour resolution target with 24/7 coverage."
        ),
        "claim_type": "verified_fact",
        "evidence_ids": ["__EVIDENCE_2__"],
    }
    conclusion["hypothesis_assessments"][0] = {
        "hypothesis_id": "H1",
        "status": "supported",
        "rationale": "The cited published passage contains the requested P1 terms.",
        "evidence_ids": ["__EVIDENCE_2__"],
    }
    conclusion["business_implications"][0]["statement"] = (
        "If the applicable executed agreement uses these terms, operations can review exposed "
        "accounts against the cited response commitment."
    )
    conclusion["recommendation"]["statement"] = (
        "Have an operations leader review the ranked accounts and verify applicable agreements."
    )
    conclusion["recommendation"]["rationale"] = (
        "The ranking identifies exposure while the cited template defines the reference terms."
    )
    conclusion["confidence"]["rationale"] = (
        "The ranking and passage are deterministic, but agreement applicability needs review."
    )
    conclusion["unresolved_questions"] = [
        "Does each affected account use the published Standard MSA without amendments?"
    ]
    conclusion["limitations"] = [
        "A template passage does not establish account-specific contractual applicability."
    ]

    state = run_investigation(
        question,
        planner=create_planner(json_agent(plan)),
        selector=selector_agent([ACCOUNT_DECISION, document_decision]),
        synthesizer=create_synthesizer(json_agent(conclusion)),
        data_root=dataset,
    )

    assert [action.name for action in state.actions] == [
        "get_account_support_risk",
        "search_internal_documents",
    ]
    assert state.actions[1].arguments["query"] == question
    citation = state.observations[1].content["results"][0]
    assert citation["document_id"] == "MSA-005"
    assert citation["section"] == "3.2 Response & Resolution Targets"
    assert citation["line_start"] == 3
    assert state.evidence_ledger.records[1].source.access_mode == "authenticated_files"
    assert state.evidence_ledger.records[1].reported_record_ids == ("MSA-005",)
    assert state.conclusion.confidence.level == "medium"
    assert state.conclusion.confidence.data_quality == "limited"
    assert state.conclusion_correction is not None
    assert "document_applicability_confidence" in state.conclusion_correction.triggering_rules


def test_document_ranking_plan_rejects_an_unavailable_concentration_hypothesis() -> None:
    plan = json.loads(json.dumps(PLAN))
    plan["steps"] = [
        {
            "step_id": "step_1",
            "analysis": "get_account_support_risk",
            "purpose": "Rank current account exposure.",
            "success_criterion": "A bounded account ranking is returned.",
        },
        {
            "step_id": "step_2",
            "analysis": "search_internal_documents",
            "purpose": "Retrieve the published Standard MSA terms.",
            "success_criterion": "A cited passage is returned.",
        },
    ]
    plan["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "statement": "A small subset holds the majority of P1 exposure.",
            "test": "Calculate its share of total exposure.",
        }
    ]

    assert plan_introduces_unsupported_ranking_concentration(
        InvestigationPlan.model_validate(plan)
    )


def test_support_ranking_plan_rejects_an_unavailable_concentration_hypothesis() -> None:
    plan = json.loads(json.dumps(PLAN))
    plan["steps"] = [
        {
            "step_id": "step_1",
            "analysis": "get_account_support_risk",
            "purpose": "Rank current account exposure.",
            "success_criterion": "A bounded account ranking is returned.",
        },
        {
            "step_id": "step_2",
            "analysis": "get_product_area_support_risk",
            "purpose": "Rank current product-area exposure.",
            "success_criterion": "A bounded product-area ranking is returned.",
        },
    ]
    plan["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "statement": "Exposure is concentrated in a small subset of accounts.",
            "test": "Calculate its share of total exposure.",
        }
    ]

    assert plan_introduces_unsupported_ranking_concentration(
        InvestigationPlan.model_validate(plan)
    )


def test_evidence_records_are_content_addressed_and_tamper_evident(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )
    record = state.evidence_ledger.records[0]
    EvidenceRecord.model_validate(record.model_dump(mode="python"))

    tampered = record.model_dump(mode="python")
    tampered["result"]["comparison"]["current"] = 999
    with pytest.raises(ValidationError, match="result digest"):
        EvidenceRecord.model_validate(tampered)


def test_audit_bundle_is_self_contained_and_round_trips(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )
    bundle = create_audit_bundle(state)
    restored = AuditBundle.model_validate_json(bundle.model_dump_json())

    assert restored.investigation_id == bundle.investigation_id
    assert restored.capability_catalog.catalog_version == "stage-11-v1"
    assert restored.capability_catalog.catalog_digest == state.capability_catalog.catalog_digest
    assert len(restored.evidence_ledger.records) == 2
    assert {claim.claim_type for claim in restored.claims} == {
        "verified_fact",
        "analytical_finding",
        "hypothesis_assessment",
        "business_implication",
        "recommendation",
    }
    assert all(
        evidence_id in restored.evidence_ledger.evidence_ids
        for claim in restored.claims
        for evidence_id in claim.evidence_ids
    )

    tampered = bundle.model_dump(mode="python")
    tampered["conclusion"]["executive_summary"] = "A changed conclusion."
    with pytest.raises(ValidationError, match="investigation ID"):
        AuditBundle.model_validate(tampered)

    mismatched = bundle.model_dump(mode="python")
    catalog = mismatched["capability_catalog"]
    evidence_method = mismatched["evidence_ledger"]["records"][0]["method"]
    capability = next(
        item
        for item in catalog["capabilities"]
        if item["capability_id"] == evidence_method["tool_name"]
    )
    capability["implementation"] = "business_ops.reports.unapproved_report"
    catalog["catalog_digest"] = catalog_digest(
        {key: value for key, value in catalog.items() if key != "catalog_digest"}
    )
    with pytest.raises(ValidationError, match="embedded capability catalog"):
        AuditBundle.model_validate(mismatched)


def test_cli_writes_audit_bundle_without_overwriting_existing_evidence(
    dataset: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )
    monkeypatch.setattr(
        "business_ops.investigation_cli.run_investigation",
        lambda *args, **kwargs: state,
    )
    output = tmp_path / "audit" / "investigation.json"

    assert investigation_cli_main([QUESTION, "--audit-output", str(output)]) == 0
    AuditBundle.model_validate_json(output.read_text(encoding="utf-8"))
    assert investigation_cli_main([QUESTION, "--audit-output", str(output)]) == 1
    assert "already exists" in capsys.readouterr().err


def test_controller_audits_an_explicit_causal_classification_correction(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    predictive_plan = json.loads(json.dumps(PLAN))
    predictive_plan["question"]["question_type"] = "predictive"

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(predictive_plan)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    assert state.plan.question.question_type == "causal"
    assert state.classification_correction is not None
    assert state.classification_correction.model_output == "predictive"
    assert state.classification_correction.enforced == "causal"


def test_controller_enforces_quarter_windows_stated_in_the_question(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    wrong_period = PIPELINE_DECISION | {
        "current_start": "2025-10-01",
        "current_end": "2026-03-31",
        "previous_start": "2025-10-01",
        "previous_end": "2026-03-31",
    }

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([wrong_period, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    decision = state.decisions[0]
    assert decision.current_start == date(2026, 1, 1)
    assert decision.current_end == date(2026, 3, 31)
    assert decision.previous_start == date(2025, 10, 1)
    assert decision.previous_end == date(2025, 12, 31)
    assert state.observations[0].content["comparison"]["absolute_change"] == -700


def test_selector_retries_a_tool_outside_the_remaining_plan(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    sequence = iter([PRODUCT_DECISION, PIPELINE_DECISION, OVERLAP_DECISION])

    def select(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(sequence)))])

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=create_step_selector(FunctionModel(select)),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    assert [decision.analysis for decision in state.decisions] == [
        "compare_closed_won_pipeline",
        "test_support_pipeline_overlap",
    ]
    assert state.usage.execution.requests == 4


def test_relevance_guard_removes_redundant_planned_analysis_and_audits_correction(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    expanded_plan = json.loads(json.dumps(PLAN))
    expanded_plan["steps"].insert(
        1,
        {
            "step_id": "step_3",
            "analysis": "get_account_support_risk",
            "purpose": "Check account support exposure.",
            "success_criterion": "Account risk is ranked.",
        },
    )

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(expanded_plan)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    assert len(state.actions) == 2
    assert state.actions[-1].name == "test_support_pipeline_overlap"
    assert state.plan_correction is not None
    assert state.plan_correction.removed_analyses == ["get_account_support_risk"]
    assert [step.analysis for step in state.plan.steps] == [
        "compare_closed_won_pipeline",
        "test_support_pipeline_overlap",
    ]
    bundle = create_audit_bundle(state)
    assert bundle.controller_corrections[0]["correction_type"] == "analysis_scope"


def test_synthesis_retries_citations_to_unexecuted_analyses(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    invalid = json.loads(json.dumps(CONCLUSION))
    invalid["findings"][0]["evidence_ids"] = ["EV-0000000000000000"]
    sequence = iter([invalid, CONCLUSION])

    def synthesize(messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(render_payload(next(sequence), messages))])

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(FunctionModel(synthesize)),
        data_root=dataset,
    )

    assert state.usage.execution.requests == 4
    assert state.conclusion.findings[0].evidence_ids == [
        state.evidence_ledger.records[0].evidence_id
    ]


def test_synthesis_retries_overconfident_causal_claims(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    invalid = json.loads(json.dumps(CONCLUSION))
    invalid["confidence"]["level"] = "high"
    invalid["hypothesis_assessments"][0]["status"] = "rejected"
    invalid["hypothesis_assessments"][0]["rationale"] = (
        "The relationship was not statistically significant."
    )
    sequence = iter([invalid, CONCLUSION])

    def synthesize(messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(render_payload(next(sequence), messages))])

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(FunctionModel(synthesize)),
        data_root=dataset,
    )

    assert state.usage.execution.requests == 4
    assert state.conclusion.confidence.level == "medium"
    assert state.conclusion.hypothesis_assessments[0].status == "inconclusive"


def test_controller_records_deterministic_policy_corrections(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    unsafe = json.loads(json.dumps(CONCLUSION))
    unsafe["business_implications"][0]["statement"] = (
        "Support issues were not the primary driver of the revenue drop."
    )
    unsafe["findings"][0]["statement"] = "Revenue declined during the period."
    unsafe["confidence"]["source_agreement"] = "consistent"

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(unsafe)),
        data_root=dataset,
    )

    assert state.conclusion_correction is not None
    assert "business_implications" in state.conclusion_correction.corrected_sections
    assert "metric_terminology" in state.conclusion_correction.corrected_sections
    assert state.conclusion.confidence.source_agreement == "not_assessed"
    assert decisive_causal_phrases(state.conclusion.business_implications[0].statement) == ()
    assert has_revenue_metric_conflation(state.conclusion.model_dump_json()) is False
    bundle = create_audit_bundle(state)
    assert any(
        item["correction_type"] == "conclusion_policy"
        for item in bundle.controller_corrections
    )


def test_synthesis_retries_causal_boilerplate_for_noncausal_question(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    question = "Which accounts and product areas should an operations leader review first?"
    plan = json.loads(json.dumps(PLAN))
    plan["question"].update(
        {
            "question_type": "prescriptive",
            "normalized_question": question,
            "time_period": None,
        }
    )
    plan["steps"] = [
        {
            "step_id": "step_1",
            "analysis": "get_account_support_risk",
            "purpose": "Rank account exposure.",
            "success_criterion": "The account ranking is available.",
        },
        {
            "step_id": "step_2",
            "analysis": "get_product_area_support_risk",
            "purpose": "Rank product-area exposure.",
            "success_criterion": "The product ranking is available.",
        },
    ]
    plan["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "statement": "The approved reports produce ranked current support exposures.",
            "test": "Verify that both bounded rankings are returned.",
        }
    ]
    valid = json.loads(json.dumps(CONCLUSION))
    valid["executive_summary"] = (
        "Prioritize the highest current support exposures. These rankings do not imply "
        "contractual obligations."
    )
    valid["findings"][0]["statement"] = (
        "The account exposure ranking is available, with an unsupported $999 subtotal."
    )
    valid["findings"][1]["statement"] = "The product-area exposure ranking is available."
    valid["hypothesis_assessments"][0]["status"] = "supported"
    valid["hypothesis_assessments"][0]["rationale"] = (
        "The approved reports provide the requested rankings."
    )
    valid["confidence"]["rationale"] = "The requested rankings are directly measured."
    valid["business_implications"][0]["statement"] = (
        "The rankings provide a focused management review list."
    )
    valid["recommendation"]["statement"] = (
        "Verify contractual obligations before acting on the rankings."
    )
    valid["recommendation"]["rationale"] = (
        "The applicability of service commitments is unverified."
    )
    valid["unresolved_questions"] = []
    valid["limitations"] = ["The source is synthetic."]
    invalid = json.loads(json.dumps(valid))
    invalid["executive_summary"] += (
        " The available evidence does not support attribution; causation remains unresolved."
    )
    sequence = iter([invalid, valid])

    def synthesize(messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(render_payload(next(sequence), messages))])

    state = run_investigation(
        question,
        planner=create_planner(json_agent(plan)),
        selector=selector_agent([ACCOUNT_DECISION, PRODUCT_DECISION]),
        synthesizer=create_synthesizer(FunctionModel(synthesize)),
        data_root=dataset,
    )

    assert state.usage.execution.requests == 4
    assert "causation" not in state.conclusion.model_dump_json().lower()
    assert "contractual" not in state.conclusion.model_dump_json().lower()
    assert "999" not in state.conclusion.model_dump_json()
    assert state.conclusion.recommendation.statement == (
        "Have a human review the top-ranked accounts and product areas in the cited evidence "
        "before taking operational action."
    )
    assert state.conclusion.recommendation.rationale == (
        "The deterministic rankings identify the highest measured current exposure."
    )
    assert state.conclusion_correction is not None
    assert "document_evidence_required" in state.conclusion_correction.triggering_rules
    assert any(
        item.startswith("claim_content_scope:finding:F1:number:999")
        for item in state.conclusion_correction.triggering_rules
    )


def test_dataset_is_verified_before_planning(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid_marker(_root: Path) -> Path:
        from business_ops.datasets.download import DatasetImportError

        raise DatasetImportError("unapproved dataset")

    def should_not_run(_messages: object, _info: AgentInfo) -> ModelResponse:
        raise AssertionError("model must not run before source verification")

    monkeypatch.setattr("business_ops.investigation.verify_dataset", invalid_marker)
    never_model = FunctionModel(should_not_run)

    with pytest.raises(InvestigationError, match="unapproved dataset"):
        run_investigation(
            QUESTION,
            planner=create_planner(never_model),
            selector=create_step_selector(never_model),
            synthesizer=create_synthesizer(never_model),
            data_root=dataset,
        )


def test_controller_can_execute_the_same_plan_through_sqlite(
    dataset: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    monkeypatch.setattr(
        "business_ops.datasets.sqlite_store.verify_dataset", lambda root, spec: root
    )
    (dataset / ".source.json").write_text("{}", encoding="utf-8")
    database = tmp_path / "derived" / "maple.sqlite3"
    build_database(dataset, database, verify_source=False)

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
        database_path=database,
    )

    assert state.actions[0].returned is True
    assert state.observations[0].content["comparison"]["absolute_change"] == -700
    assert state.observations[1].content["overlapping_accounts"] == 1
