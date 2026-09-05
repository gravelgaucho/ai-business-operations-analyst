from __future__ import annotations

from pathlib import Path
from typing import Any

from business_ops.catalog import DEFAULT_CATALOG
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.evaluation import (
    CAUSAL_ATTRIBUTION,
    DOCUMENT_GROUNDED_SUPPORT_REVIEW,
    GOVERNED_OPPORTUNITY_ANALYSIS,
    SUPPORT_PRIORITIZATION,
    evaluate_investigation,
    run_evaluation_suite,
)
from business_ops.investigation import InvestigationState
from business_ops.provenance import EvidenceLedger, build_evidence_record


def source() -> dict[str, object]:
    return {
        "dataset": ENTERPRISE_BENCH.name,
        "source_commit": ENTERPRISE_BENCH.source_commit,
        "license": ENTERPRISE_BENCH.license,
        "synthetic": True,
    }


def state_for(
    *,
    question: str,
    question_type: str,
    tools: list[str],
    observations: list[dict[str, Any]],
    causal: bool,
) -> InvestigationState:
    hypotheses = [
        {
            "hypothesis_id": "H1",
            "statement": "The available evidence can prioritize review.",
            "test": "Use the approved deterministic reports.",
        }
    ]
    plan = {
        "question": {
            "question_type": question_type,
            "scope": "portfolio_evaluation",
            "metric": "business exposure",
            "time_period": "Q1 2026 versus Q4 2025" if causal else None,
            "entities": [],
            "requires_investigation": True,
            "missing_information": ["Timing"] if causal else [],
            "normalized_question": question,
        },
        "objective": "Evaluate the question against approved evidence.",
        "hypotheses": hypotheses,
        "steps": [
            {
                "step_id": f"step_{index}",
                "analysis": tool,
                "purpose": "Collect relevant evidence.",
                "success_criterion": "The deterministic report returns.",
            }
            for index, tool in enumerate(tools, start=1)
        ],
        "stop_conditions": ["Required evidence is available."],
    }
    decisions = []
    actions = []
    tool_observations = []
    evidence_records = []
    for index, (tool, content) in enumerate(zip(tools, observations, strict=True), start=1):
        dated = tool in {
            "compare_closed_won_pipeline",
            "test_support_pipeline_overlap",
            "query_closed_won_opportunity_acv",
        }
        arguments = (
            content["semantic_query"]
            if tool == "query_closed_won_opportunity_acv"
            else content["query"]
            if tool == "search_internal_documents"
            else {}
        )
        decisions.append(
            {
                "analysis": tool,
                "rationale": "Collect the planned evidence.",
                "current_start": "2026-01-01" if dated else None,
                "current_end": "2026-03-31" if dated else None,
                "previous_start": "2025-10-01" if dated else None,
                "previous_end": "2025-12-31" if dated else None,
                "top_n": 5,
                "top_n_decliners": 5,
                "priorities": ["p1"],
                "currency": "USD",
                "search_query": (
                    arguments.get("query")
                    if tool == "search_internal_documents"
                    else None
                ),
                "document_top_k": (
                    arguments.get("top_k", 5)
                    if tool == "search_internal_documents"
                    else 5
                ),
            }
        )
        actions.append({"name": tool, "arguments": arguments, "returned": True})
        tool_observations.append(
            {
                "observation_id": f"observation_{index}",
                "tool_name": tool,
                "content": content,
            }
        )
        evidence_records.append(
            build_evidence_record(
                observation_id=f"observation_{index}",
                tool_name=tool,
                arguments=arguments,
                result=content,
                source=Path("."),
            )
        )

    evidence_ids = [record.evidence_id for record in evidence_records]

    conclusion = {
        "executive_summary": (
            "The available evidence does not support attribution; causation remains unresolved."
            if causal
            else "The approved evidence supports a bounded review."
        ),
        "findings": [
            {
                "finding_id": f"F{index}",
                "statement": f"Evidence was returned by {tool}.",
                "claim_type": "analytical_finding" if causal else "verified_fact",
                "evidence_ids": [evidence_ids[index - 1]],
            }
            for index, tool in enumerate(tools, start=1)
        ],
        "hypothesis_assessments": [
            {
                "hypothesis_id": "H1",
                "status": "inconclusive" if causal else "supported",
                "rationale": "Causal timing is unavailable." if causal else "Reports agree.",
                "evidence_ids": evidence_ids,
            }
        ],
        "business_implications": [
            {
                "implication_id": "I1",
                "statement": "The evidence supports a focused management review.",
                "evidence_ids": evidence_ids,
            }
        ],
        "recommendation": {
            "recommendation_id": "R1",
            "statement": "Have an operations leader review the ranked evidence.",
            "rationale": "The deterministic reports identify the review scope.",
            "evidence_ids": evidence_ids,
            "human_review_required": True,
        },
        "confidence": {
            "level": "medium",
            "rationale": "The evidence is bounded to the approved synthetic sources.",
            "evidence_coverage": "partial",
            "source_agreement": "not_assessed",
            "data_quality": "adequate",
        },
        "unresolved_questions": ["Did the issue precede the change?"] if causal else [],
        "limitations": ["Association is not causation."] if causal else ["Synthetic data."],
    }
    usage_item = {
        "requests": 1,
        "input_tokens": 10,
        "output_tokens": 10,
        "total_tokens": 20,
        "tool_calls": 0,
    }
    return InvestigationState.model_validate(
        {
            "original_question": question,
            "capability_catalog": DEFAULT_CATALOG.model_dump(mode="json"),
            "plan": plan,
            "decisions": decisions,
            "actions": actions,
            "observations": tool_observations,
            "evidence_ledger": EvidenceLedger(records=tuple(evidence_records)).model_dump(
                mode="json"
            ),
            "stop_reason": "The evidence gate is satisfied.",
            "conclusion": conclusion,
            "usage": {
                "planning": usage_item,
                "execution": usage_item | {"tool_calls": len(tools)},
                "total_requests": 2,
                "total_tokens": 40,
                "total_tool_calls": len(tools),
            },
        }
    )


def causal_state() -> InvestigationState:
    return state_for(
        question=CAUSAL_ATTRIBUTION.question,
        question_type="causal",
        tools=["compare_closed_won_pipeline", "test_support_pipeline_overlap"],
        observations=[
            {
                "source": source(),
                "metric_definition": (
                    "Opportunity ACV grouped by target close date and current final stage. "
                    "This is not recognized revenue."
                ),
                "comparison": {
                    "baseline": 80_700_000,
                    "current": 31_175_000,
                    "percent_change": -61.37,
                },
            },
            {"source": source(), "overlapping_accounts": 1},
        ],
        causal=True,
    )


def test_causal_scenario_passes_all_reliability_gates() -> None:
    result = evaluate_investigation(CAUSAL_ATTRIBUTION, causal_state())

    assert result.passed is True
    assert result.score_percent == 100.0
    assert all(check.passed for check in result.checks)


def test_observation_ledger_mismatch_is_visible_without_hiding_other_checks() -> None:
    state = causal_state()
    observations = list(state.observations)
    observations[0] = observations[0].model_copy(
        update={
            "content": {
                "source": source(),
                "comparison": {
                    "baseline": 80_700_000,
                    "current": 0,
                    "percent_change": -100.0,
                },
            }
        }
    )
    state = state.model_copy(update={"observations": observations})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert result.passed is False
    assert checks["complete_evidence_ledger"].passed is False
    assert checks["deterministic_evidence"].passed is True
    assert checks["grounded_citations"].passed is True


def test_evidence_method_must_match_the_capability_catalog() -> None:
    state = causal_state()
    records = list(state.evidence_ledger.records)
    records[0] = records[0].model_copy(
        update={
            "method": records[0].method.model_copy(
                update={"implementation": "business_ops.reports.unapproved_report"}
            )
        }
    )
    state = state.model_copy(
        update={"evidence_ledger": state.evidence_ledger.model_copy(update={"records": records})}
    )

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["catalog_execution_alignment"].passed is False
    assert checks["tamper_evident_evidence"].passed is False


def test_support_scenario_accepts_a_descriptive_classification_and_list_anchor() -> None:
    state = state_for(
        question=SUPPORT_PRIORITIZATION.question,
        question_type="descriptive",
        tools=["get_account_support_risk", "get_product_area_support_risk"],
        observations=[
            {
                "source": source(),
                "summary": {"affected_accounts": 8, "total_arr_at_risk": 1_041_000},
            },
            {
                "source": source(),
                "results": [{"component_id": "PART-010"}],
            },
        ],
        causal=False,
    )

    result = evaluate_investigation(SUPPORT_PRIORITIZATION, state)

    assert result.passed is True
    assert result.score_percent == 100.0


def governed_opportunity_state() -> InvestigationState:
    return state_for(
        question=GOVERNED_OPPORTUNITY_ANALYSIS.question,
        question_type="comparative",
        tools=["compare_closed_won_pipeline", "query_closed_won_opportunity_acv"],
        observations=[
            {
                "source": source(),
                "metric_definition": (
                    "Opportunity ACV grouped by target close date and current final stage. "
                    "This is not recognized revenue."
                ),
                "comparison": {
                    "baseline": 80_700_000,
                    "current": 31_175_000,
                    "percent_change": -61.37,
                },
            },
            {
                "source": source(),
                "semantic_query": {
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31",
                    "dimensions": ["region"],
                    "currency": "USD",
                    "top_n": 10,
                },
                "metric_definition": (
                    "Sum of closed-won opportunity ACV grouped by approved dimensions and "
                    "target close date. This is not recognized revenue."
                ),
                "rows": [
                    {
                        "dimensions": {"region": "Americas/East"},
                        "closed_won_opportunity_acv": 9_690_000,
                    },
                    {
                        "dimensions": {"region": "Americas/West"},
                        "closed_won_opportunity_acv": 9_335_000,
                    },
                ],
            },
        ],
        causal=False,
    )


def test_governed_opportunity_scenario_passes_query_contract_gates() -> None:
    result = evaluate_investigation(
        GOVERNED_OPPORTUNITY_ANALYSIS, governed_opportunity_state()
    )

    checks = {check.name: check for check in result.checks}
    assert result.passed is True
    assert checks["governed_query_contract"].passed is True
    assert checks["governed_query_result_bounds"].passed is True


def test_governed_query_action_cannot_diverge_from_evidenced_query() -> None:
    state = governed_opportunity_state()
    actions = list(state.actions)
    actions[1] = actions[1].model_copy(
        update={"arguments": actions[1].arguments | {"top_n": 1}}
    )
    state = state.model_copy(update={"actions": actions})

    result = evaluate_investigation(GOVERNED_OPPORTUNITY_ANALYSIS, state)

    checks = {check.name: check for check in result.checks}
    assert checks["governed_query_contract"].passed is False


def document_grounded_state() -> InvestigationState:
    query = {
        "query": DOCUMENT_GROUNDED_SUPPORT_REVIEW.question,
        "top_k": 3,
    }
    excerpt = (
        "### 3.2 Response & Resolution Targets\n\n"
        "| Priority | Initial Response Time | Resolution Target | Business Hours |\n"
        "|----------|----------------------|-------------------|----------------|\n"
        "| **P1** | 1 hour | 24 hours | 24/7 |"
    )
    import hashlib

    state = state_for(
        question=DOCUMENT_GROUNDED_SUPPORT_REVIEW.question,
        question_type="prescriptive",
        tools=["get_account_support_risk", "search_internal_documents"],
        observations=[
            {
                "source": source(),
                "summary": {"affected_accounts": 8, "total_arr_at_risk": 1_041_000},
            },
            {
                "source": source(),
                "query": query,
                "results": [
                    {
                        "document_id": "MSA-005",
                        "title": "Maple Payments — Standard MSA Template",
                        "status": "published",
                        "modified_at": "2026-01-01T00:00:00Z",
                        "locator": "internal_docs/msa_standard_template.md",
                        "section": "3.2 Response & Resolution Targets",
                        "line_start": 64,
                        "line_end": 80,
                        "chunk_sha256": (
                            "sha256:" + hashlib.sha256(excerpt.encode()).hexdigest()
                        ),
                        "relevance_score": 29.0,
                        "excerpt": excerpt,
                    }
                ],
            },
        ],
        causal=False,
    )
    recommendation = state.conclusion.recommendation.model_copy(
        update={
            "statement": (
                "Have an operations leader review the ranked evidence and verify the "
                "applicable executed agreement or service tier."
            ),
            "rationale": (
                "The template provides reference terms whose account-level applicability "
                "requires human verification."
            ),
        }
    )
    confidence = state.conclusion.confidence.model_copy(
        update={
            "level": "medium",
            "rationale": "Account-to-executed-agreement or service-tier mapping is absent.",
            "data_quality": "limited",
        }
    )
    return state.model_copy(
        update={
            "conclusion": state.conclusion.model_copy(
                update={"recommendation": recommendation, "confidence": confidence}
            )
        }
    )


def test_document_grounded_scenario_passes_retrieval_and_citation_gates() -> None:
    state = document_grounded_state()
    scenario = DOCUMENT_GROUNDED_SUPPORT_REVIEW.model_copy(
        update={
            "evidence_expectations": DOCUMENT_GROUNDED_SUPPORT_REVIEW.evidence_expectations[:-1]
        }
    )
    result = evaluate_investigation(scenario, state)

    checks = {check.name: check for check in result.checks}
    assert result.passed is True
    assert checks["document_retrieval_contract"].passed is True
    assert checks["document_citation_integrity"].passed is True


def test_synthesis_cannot_invent_a_new_numeric_subtotal() -> None:
    state = document_grounded_state()
    findings = list(state.conclusion.findings)
    findings[0] = findings[0].model_copy(
        update={"statement": "The top accounts total $612,000 of exposure."}
    )
    state = state.model_copy(
        update={"conclusion": state.conclusion.model_copy(update={"findings": findings})}
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "612000" in checks["evidence_content_scope"].detail


def test_claim_cannot_borrow_a_number_from_uncited_evidence() -> None:
    state = document_grounded_state()
    findings = list(state.conclusion.findings)
    findings[0] = findings[0].model_copy(
        update={"statement": "The ranked accounts total $29.00 of exposure."}
    )
    state = state.model_copy(
        update={"conclusion": state.conclusion.model_copy(update={"findings": findings})}
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "finding:F1:number:29" in checks["evidence_content_scope"].detail


def test_document_language_requires_document_evidence() -> None:
    state = causal_state()
    conclusion = state.conclusion.model_copy(
        update={
            "executive_summary": (
                state.conclusion.executive_summary
                + " Verify the applicable SLA and executed agreement."
            )
        }
    )
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "document-without-evidence:sla" in checks["evidence_content_scope"].detail


def test_synthesis_cannot_describe_an_uncalculated_concentration_as_a_majority() -> None:
    state = document_grounded_state()
    assessments = list(state.conclusion.hypothesis_assessments)
    assessments[0] = assessments[0].model_copy(
        update={"rationale": "The top accounts hold the majority of exposure."}
    )
    state = state.model_copy(
        update={
            "conclusion": state.conclusion.model_copy(
                update={"hypothesis_assessments": assessments}
            )
        }
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "majority" in checks["evidence_content_scope"].detail


def test_synthesis_cannot_hide_uncalculated_math_as_a_material_share() -> None:
    state = document_grounded_state()
    findings = list(state.conclusion.findings)
    findings[0] = findings[0].model_copy(
        update={"statement": "The top accounts hold a material share of exposure."}
    )
    state = state.model_copy(
        update={"conclusion": state.conclusion.model_copy(update={"findings": findings})}
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "material share" in checks["evidence_content_scope"].detail


def test_synthesis_cannot_hide_uncalculated_math_as_a_collective_total() -> None:
    state = document_grounded_state()
    findings = list(state.conclusion.findings)
    findings[0] = findings[0].model_copy(
        update={"statement": "The top accounts collectively exceed the remaining exposure."}
    )
    state = state.model_copy(
        update={"conclusion": state.conclusion.model_copy(update={"findings": findings})}
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["evidence_content_scope"].passed is False
    assert "collectively" in checks["evidence_content_scope"].detail


def test_template_terms_require_account_applicability_verification() -> None:
    state = document_grounded_state()
    recommendation = state.conclusion.recommendation.model_copy(
        update={
            "statement": "Ensure the ranked accounts comply with the Standard MSA.",
            "rationale": "The template lists P1 response targets.",
        }
    )
    state = state.model_copy(
        update={
            "conclusion": state.conclusion.model_copy(
                update={"recommendation": recommendation}
            )
        }
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["document_applicability_restraint"].passed is False


def test_document_cited_implication_must_state_template_applicability_condition() -> None:
    state = document_grounded_state()
    implications = list(state.conclusion.business_implications)
    implications[0] = implications[0].model_copy(
        update={
            "statement": (
                "The Standard MSA commitment requires continuous monitoring for these accounts."
            )
        }
    )
    state = state.model_copy(
        update={
            "conclusion": state.conclusion.model_copy(
                update={"business_implications": implications}
            )
        }
    )

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["document_applicability_restraint"].passed is False


def test_executive_summary_must_state_template_applicability_condition() -> None:
    state = document_grounded_state()
    conclusion = state.conclusion.model_copy(
        update={
            "executive_summary": (
                "The Standard MSA specifies P1 response commitments, so operations should "
                "ensure the ranked accounts adhere to them."
            )
        }
    )
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(DOCUMENT_GROUNDED_SUPPORT_REVIEW, state)

    checks = {check.name: check for check in result.checks}
    assert checks["document_applicability_restraint"].passed is False


def test_unsupported_significantly_comparison_fails_the_statistics_gate() -> None:
    state = causal_state()
    conclusion = state.conclusion.model_copy(
        update={"executive_summary": "The current value is significantly lower than baseline."}
    )
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["no_unsupported_statistics"].passed is False


def test_same_snapshot_cannot_be_claimed_as_independent_source_agreement() -> None:
    state = causal_state()
    confidence = state.conclusion.confidence.model_copy(
        update={"source_agreement": "consistent"}
    )
    conclusion = state.conclusion.model_copy(update={"confidence": confidence})
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["source_agreement_calibration"].passed is False


def test_pipeline_acv_cannot_be_described_as_revenue() -> None:
    state = causal_state()
    conclusion = state.conclusion.model_copy(
        update={"executive_summary": state.conclusion.executive_summary + " Revenue fell."}
    )
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["metric_definition_preserved"].passed is False


def test_causal_warning_must_appear_in_the_executive_summary() -> None:
    state = causal_state()
    conclusion = state.conclusion.model_copy(
        update={
            "executive_summary": "The measured association is inconclusive.",
            "limitations": [
                *state.conclusion.limitations,
                "The available evidence does not support attribution; causation remains "
                "unresolved.",
            ],
        }
    )
    state = state.model_copy(update={"conclusion": conclusion})

    result = evaluate_investigation(CAUSAL_ATTRIBUTION, state)

    checks = {check.name: check for check in result.checks}
    assert checks["question_appropriate_causal_language"].passed is False


def test_suite_preserves_a_case_failure_as_a_result() -> None:
    def fail(_question: str) -> InvestigationState:
        raise RuntimeError("model endpoint unavailable")

    result = run_evaluation_suite(fail, (CAUSAL_ATTRIBUTION,))

    assert result.all_passed is False
    assert result.passed_scenarios == 0
    assert result.runs[0].error == "RuntimeError: model endpoint unavailable"
