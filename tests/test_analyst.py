from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic_ai import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UsageLimits
from pydantic_ai.models.function import AgentInfo, FunctionModel

from business_ops.analyst import AnalyticsAgentError, create_analytics_agent, run_analysis
from business_ops.datasets.download import DatasetImportError
from business_ops.reports import (
    SupportPipelineLinkQuery,
    support_pipeline_link_report,
)


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
    return tmp_path


def bypass_source_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("business_ops.analyst.verify_dataset", lambda root: root)


def test_agent_exposes_only_bounded_read_only_analytics_tools(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bypass_source_verification(monkeypatch)
    observed: dict[str, object] = {}

    def model(messages: object, info: AgentInfo) -> ModelResponse:
        observed["names"] = [tool.name for tool in info.function_tools]
        schema = next(
            tool.parameters_json_schema
            for tool in info.function_tools
            if tool.name == "get_account_support_risk"
        )
        observed["schema"] = schema
        return ModelResponse(parts=[TextPart("No tool used.")])

    agent = create_analytics_agent(FunctionModel(model))

    with pytest.raises(AnalyticsAgentError, match="did not complete"):
        run_analysis("Which accounts are at risk?", agent=agent, data_root=dataset)

    assert observed["names"] == [
        "get_account_support_risk",
        "get_product_area_support_risk",
        "compare_closed_won_pipeline",
        "test_support_pipeline_overlap",
        "query_closed_won_opportunity_acv",
        "search_internal_documents",
    ]
    schema = observed["schema"]
    assert isinstance(schema, dict)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["top_n"]["maximum"] == 20


def test_support_pipeline_link_is_calculated_deterministically(dataset: Path) -> None:
    result = support_pipeline_link_report(
        dataset,
        SupportPipelineLinkQuery(
            current_start=date(2026, 1, 1),
            current_end=date(2026, 3, 31),
            previous_start=date(2025, 10, 1),
            previous_end=date(2025, 12, 31),
            top_n_decliners=5,
            priorities=["p1"],
        ),
    )

    assert result.overlapping_accounts == 1
    assert result.overlap_share_of_top_decline_count_percent == 100.0
    assert result.overlapping_absolute_change == 700
    assert result.overlaps[0].account_name == "Alpha"


def test_agent_executes_tool_and_continues_with_returned_evidence(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bypass_source_verification(monkeypatch)
    model_calls = 0

    def model(messages: list[object], _info: AgentInfo) -> ModelResponse:
        nonlocal model_calls
        model_calls += 1
        returned = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if returned:
            assert "Alpha" in str(returned[-1].content)
            return ModelResponse(parts=[TextPart("Alpha has $1,000 of ARR at risk.")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "get_account_support_risk",
                    {"top_n": 1, "priorities": ["p1"]},
                    tool_call_id="account-risk-1",
                )
            ]
        )

    agent = create_analytics_agent(FunctionModel(model))
    result = run_analysis("Which account is at risk?", agent=agent, data_root=dataset)

    assert model_calls == 2
    assert result.answer == "Alpha has $1,000 of ARR at risk."
    assert result.tool_calls[0].name == "get_account_support_risk"
    assert result.tool_calls[0].returned is True
    assert result.tool_calls[0].arguments == {"top_n": 1, "priorities": ["p1"]}
    assert result.usage.requests == 2
    assert result.usage.tool_calls == 1


def test_invalid_tool_arguments_are_retried_before_execution(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bypass_source_verification(monkeypatch)
    model_calls = 0

    def model(messages: list[object], _info: AgentInfo) -> ModelResponse:
        nonlocal model_calls
        model_calls += 1
        returned = any(
            isinstance(part, ToolReturnPart) for message in messages for part in message.parts
        )
        if returned:
            return ModelResponse(parts=[TextPart("Validated result.")])
        top_n = 0 if model_calls == 1 else 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "get_account_support_risk",
                    {"top_n": top_n, "priorities": ["p1"]},
                    tool_call_id=f"account-risk-{model_calls}",
                )
            ]
        )

    agent = create_analytics_agent(FunctionModel(model))
    result = run_analysis("Which account is at risk?", agent=agent, data_root=dataset)

    assert model_calls == 3
    assert [call.returned for call in result.tool_calls] == [False, True]


def test_dataset_is_verified_before_the_model_runs(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_source(_root: Path) -> Path:
        raise DatasetImportError("unapproved dataset")

    monkeypatch.setattr("business_ops.analyst.verify_dataset", reject_source)

    def model(_messages: object, _info: AgentInfo) -> ModelResponse:
        raise AssertionError("model must not run before source verification")

    agent = create_analytics_agent(FunctionModel(model))
    with pytest.raises(AnalyticsAgentError, match="unapproved dataset"):
        run_analysis("Which account is at risk?", agent=agent, data_root=dataset)


def test_tool_call_limit_stops_an_open_ended_loop(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bypass_source_verification(monkeypatch)
    model_calls = 0

    def model(_messages: object, _info: AgentInfo) -> ModelResponse:
        nonlocal model_calls
        model_calls += 1
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "get_account_support_risk",
                    {"top_n": 1, "priorities": ["p1"]},
                    tool_call_id=f"account-risk-{model_calls}",
                )
            ]
        )

    agent = create_analytics_agent(FunctionModel(model))
    limits = UsageLimits(request_limit=3, tool_calls_limit=1)

    with pytest.raises(AnalyticsAgentError, match="tool_calls_limit"):
        run_analysis(
            "Keep checking account risk.",
            agent=agent,
            data_root=dataset,
            usage_limits=limits,
        )


def test_empty_question_fails_before_source_or_model_work() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        run_analysis("   ")
