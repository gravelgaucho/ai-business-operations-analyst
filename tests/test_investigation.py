from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from business_ops.datasets.sqlite_store import build_database
from business_ops.investigation import (
    InvestigationError,
    InvestigationPlan,
    create_planner,
    create_step_selector,
    create_synthesizer,
    run_investigation,
)

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
    "executive_summary": "Closed-won ACV declined, but overlap alone cannot prove causation.",
    "findings": [
        {
            "finding_id": "F1",
            "statement": "Closed-won ACV declined from the previous period.",
            "evidence_type": "direct",
            "source_tools": ["compare_closed_won_pipeline"],
        },
        {
            "finding_id": "F2",
            "statement": "The declining account also had an open P1 ticket.",
            "evidence_type": "association",
            "source_tools": ["test_support_pipeline_overlap"],
        },
    ],
    "hypothesis_assessments": [
        {
            "hypothesis_id": "H1",
            "status": "inconclusive",
            "rationale": "Overlap is measurable, but ticket timing is unavailable.",
            "source_tools": ["test_support_pipeline_overlap"],
        }
    ],
    "recommendation": "Have a human review ticket timing before treating this as causal.",
    "confidence": "medium",
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


def json_agent(payload: dict[str, object]):
    def model(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(payload))])

    return FunctionModel(model)


def selector_agent(sequence: list[dict[str, object]]):
    decisions: Iterator[dict[str, object]] = iter(sequence)

    def model(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(decisions)))])

    return create_step_selector(FunctionModel(model))


def test_plan_rejects_single_analysis_disguised_as_multiple_steps() -> None:
    invalid = PLAN | {
        "steps": [PLAN["steps"][0], PLAN["steps"][0] | {"step_id": "step_2"}]
    }

    with pytest.raises(ValidationError, match="two distinct analyses"):
        InvestigationPlan.model_validate(invalid)


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
    assert state.observations[1].tool_name == "test_support_pipeline_overlap"
    assert "evidence gate is satisfied" in state.stop_reason
    assert state.usage.total_requests == 4
    assert state.usage.total_tool_calls == 2


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


def test_evidence_gate_requires_planned_overlap_after_two_other_analyses(
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
        selector=selector_agent([PIPELINE_DECISION, ACCOUNT_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(json_agent(CONCLUSION)),
        data_root=dataset,
    )

    assert len(state.actions) == 3
    assert state.actions[-1].name == "test_support_pipeline_overlap"


def test_synthesis_retries_citations_to_unexecuted_analyses(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    invalid = json.loads(json.dumps(CONCLUSION))
    invalid["findings"][0]["source_tools"] = ["get_product_area_support_risk"]
    sequence = iter([invalid, CONCLUSION])

    def synthesize(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(sequence)))])

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(FunctionModel(synthesize)),
        data_root=dataset,
    )

    assert state.usage.execution.requests == 4
    assert state.conclusion.findings[0].source_tools == ["compare_closed_won_pipeline"]


def test_synthesis_retries_overconfident_causal_claims(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("business_ops.investigation.verify_dataset", lambda root: root)
    invalid = json.loads(json.dumps(CONCLUSION))
    invalid["confidence"] = "high"
    invalid["hypothesis_assessments"][0]["status"] = "rejected"
    invalid["hypothesis_assessments"][0]["rationale"] = (
        "The relationship was not statistically significant."
    )
    sequence = iter([invalid, CONCLUSION])

    def synthesize(_messages: object, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(next(sequence)))])

    state = run_investigation(
        QUESTION,
        planner=create_planner(json_agent(PLAN)),
        selector=selector_agent([PIPELINE_DECISION, OVERLAP_DECISION]),
        synthesizer=create_synthesizer(FunctionModel(synthesize)),
        data_root=dataset,
    )

    assert state.usage.execution.requests == 4
    assert state.conclusion.confidence == "medium"
    assert state.conclusion.hypothesis_assessments[0].status == "inconclusive"


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
