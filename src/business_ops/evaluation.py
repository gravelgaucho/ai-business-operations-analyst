from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from business_ops.catalog import CapabilityCatalog
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.investigation import (
    MANDATORY_CAUSAL_SENTENCE,
    AnalysisKind,
    InvestigationState,
    has_causal_attribution_language,
    has_revenue_metric_conflation,
    has_unsupported_statistical_language,
)
from business_ops.provenance import EvidenceRecord
from business_ops.questions import QuestionType


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceExpectation(EvaluationModel):
    analysis: AnalysisKind
    path: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$")
    expected: str | int | float | bool


class EvaluationScenario(EvaluationModel):
    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    question: str = Field(min_length=1)
    expected_question_types: tuple[QuestionType, ...] = Field(min_length=1)
    required_analyses: tuple[AnalysisKind, ...] = Field(min_length=1)
    allowed_analyses: tuple[AnalysisKind, ...] = ()
    evidence_expectations: tuple[EvidenceExpectation, ...] = ()
    require_causal_restraint: bool = False
    max_analysis_steps: int = Field(default=4, ge=2, le=4)
    max_model_requests: int = Field(default=12, ge=1)

    @model_validator(mode="after")
    def entries_are_distinct(self) -> EvaluationScenario:
        if len(self.expected_question_types) != len(set(self.expected_question_types)):
            raise ValueError("expected question types must be distinct")
        if len(self.required_analyses) != len(set(self.required_analyses)):
            raise ValueError("required analyses must be distinct")
        if len(self.allowed_analyses) != len(set(self.allowed_analyses)):
            raise ValueError("allowed analyses must be distinct")
        if self.allowed_analyses and not set(self.required_analyses).issubset(
            self.allowed_analyses
        ):
            raise ValueError("allowed analyses must include every required analysis")
        return self


class EvaluationCheck(EvaluationModel):
    name: str
    passed: bool
    detail: str


class ScenarioEvaluation(EvaluationModel):
    scenario_id: str
    passed: bool
    score_percent: float
    checks: tuple[EvaluationCheck, ...]


class ScenarioRun(EvaluationModel):
    scenario: EvaluationScenario
    elapsed_seconds: float
    evaluation: ScenarioEvaluation | None = None
    state: InvestigationState | None = None
    error: str | None = None


class EvaluationSuiteResult(EvaluationModel):
    all_passed: bool
    passed_scenarios: int
    total_scenarios: int
    elapsed_seconds: float
    runs: tuple[ScenarioRun, ...]


CAUSAL_ATTRIBUTION = EvaluationScenario(
    scenario_id="causal_attribution",
    question=(
        "Did open P1 support issues explain the Q1 2026 decline in closed-won USD "
        "opportunity ACV versus Q4 2025?"
    ),
    expected_question_types=(QuestionType.CAUSAL,),
    required_analyses=(
        AnalysisKind.CLOSED_WON_PIPELINE,
        AnalysisKind.SUPPORT_PIPELINE_OVERLAP,
    ),
    evidence_expectations=(
        EvidenceExpectation(
            analysis=AnalysisKind.CLOSED_WON_PIPELINE,
            path="comparison.baseline",
            expected=80_700_000,
        ),
        EvidenceExpectation(
            analysis=AnalysisKind.CLOSED_WON_PIPELINE,
            path="comparison.current",
            expected=31_175_000,
        ),
        EvidenceExpectation(
            analysis=AnalysisKind.CLOSED_WON_PIPELINE,
            path="comparison.percent_change",
            expected=-61.37,
        ),
    ),
    require_causal_restraint=True,
)


SUPPORT_PRIORITIZATION = EvaluationScenario(
    scenario_id="support_prioritization",
    question=(
        "Which accounts and product areas should an operations leader review first because "
        "of open P1 support exposure?"
    ),
    expected_question_types=(QuestionType.PRESCRIPTIVE, QuestionType.DESCRIPTIVE),
    required_analyses=(
        AnalysisKind.ACCOUNT_SUPPORT_RISK,
        AnalysisKind.PRODUCT_AREA_SUPPORT_RISK,
    ),
    evidence_expectations=(
        EvidenceExpectation(
            analysis=AnalysisKind.ACCOUNT_SUPPORT_RISK,
            path="summary.affected_accounts",
            expected=8,
        ),
        EvidenceExpectation(
            analysis=AnalysisKind.ACCOUNT_SUPPORT_RISK,
            path="summary.total_arr_at_risk",
            expected=1_041_000,
        ),
        EvidenceExpectation(
            analysis=AnalysisKind.PRODUCT_AREA_SUPPORT_RISK,
            path="results.0.component_id",
            expected="PART-010",
        ),
    ),
)


DEFAULT_SCENARIOS = (CAUSAL_ATTRIBUTION, SUPPORT_PRIORITIZATION)
_MISSING = object()


def _resolve_path(value: Any, path: str) -> Any:
    current = value
    for component in path.split("."):
        if isinstance(current, dict):
            current = current.get(component, _MISSING)
        elif isinstance(current, list) and component.isdigit():
            index = int(component)
            current = current[index] if index < len(current) else _MISSING
        else:
            return _MISSING
        if current is _MISSING:
            return _MISSING
    return current


def evaluate_investigation(
    scenario: EvaluationScenario, state: InvestigationState
) -> ScenarioEvaluation:
    """Score controller guarantees and deterministic evidence, never prose style."""

    checks: list[EvaluationCheck] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append(EvaluationCheck(name=name, passed=passed, detail=detail))

    question_type = state.plan.question.question_type
    correction = state.classification_correction
    record(
        "question_classification",
        question_type in scenario.expected_question_types,
        (
            f"classified as {question_type.value}"
            if correction is None
            else f"controller enforced {correction.enforced.value} after model proposed "
            f"{correction.model_output.value}"
        ),
    )

    used_sequence = [AnalysisKind(action.name) for action in state.actions if action.returned]
    used = set(used_sequence)
    catalog_integrity = True
    try:
        CapabilityCatalog.model_validate(state.capability_catalog.model_dump(mode="python"))
    except ValueError:
        catalog_integrity = False
    record(
        "capability_catalog_integrity",
        catalog_integrity,
        f"validated {state.capability_catalog.catalog_version} and its content digest",
    )

    catalog_ids = state.capability_catalog.capability_ids
    planned_ids = {step.analysis.value for step in state.plan.steps}
    executed_ids = {item.value for item in used}
    evidence_method_ids = {item.method.tool_name for item in state.evidence_ledger.records}
    catalog_alignment = planned_ids | executed_ids | evidence_method_ids <= catalog_ids
    if catalog_alignment:
        for evidence_record in state.evidence_ledger.records:
            capability = state.capability_catalog.capability(evidence_record.method.tool_name)
            source = state.capability_catalog.source(capability.source_ids[0])
            expected_locators = (
                capability.json_files
                if evidence_record.source.access_mode == "authenticated_json"
                else capability.sqlite_tables
            )
            catalog_alignment = catalog_alignment and (
                evidence_record.method.implementation == capability.implementation
                and evidence_record.method.method_version == capability.method_version
                and evidence_record.source.source_id == source.source_id
                and tuple(item.locator for item in evidence_record.source.locators)
                == expected_locators
            )
    record(
        "catalog_execution_alignment",
        catalog_alignment,
        "plan, execution, source locators, and evidence methods match the approved catalog",
    )

    missing_analyses = set(scenario.required_analyses) - used
    record(
        "required_analyses",
        not missing_analyses,
        (
            "all required analyses executed"
            if not missing_analyses
            else "missing: " + ", ".join(sorted(item.value for item in missing_analyses))
        ),
    )
    allowed = set(scenario.allowed_analyses or scenario.required_analyses)
    unexpected_analyses = used - allowed
    record(
        "relevant_analysis_scope",
        not unexpected_analyses,
        (
            "all executed analyses are relevant to the scenario"
            if not unexpected_analyses
            else "unexpected: "
            + ", ".join(sorted(item.value for item in unexpected_analyses))
        ),
    )
    record(
        "bounded_distinct_execution",
        2 <= len(used_sequence) <= scenario.max_analysis_steps and len(used_sequence) == len(used),
        f"executed {len(used_sequence)} distinct bounded analyses",
    )

    observation_tools = [item.tool_name for item in state.observations]
    record(
        "complete_observation_trace",
        len(state.actions) == len(state.observations)
        and used_sequence == observation_tools
        and all(action.returned for action in state.actions),
        f"{len(state.actions)} actions and {len(state.observations)} observations",
    )

    evidence_records = state.evidence_ledger.records
    record_tools = [AnalysisKind(item.method.tool_name) for item in evidence_records]
    record_observations = [item.observation_id for item in evidence_records]
    record_trace_complete = (
        len(evidence_records) == len(state.observations)
        and record_tools == observation_tools
        and record_observations == [item.observation_id for item in state.observations]
        and all(
            evidence.result == observation.content
            for evidence, observation in zip(evidence_records, state.observations, strict=True)
        )
    )
    record(
        "complete_evidence_ledger",
        record_trace_complete,
        f"{len(evidence_records)} evidence records for {len(state.observations)} observations",
    )

    tamper_evident = True
    try:
        for item in evidence_records:
            EvidenceRecord.model_validate(item.model_dump(mode="python"))
    except ValueError:
        tamper_evident = False
    record(
        "tamper_evident_evidence",
        tamper_evident,
        "all evidence IDs and result digests match their immutable content",
    )

    provenance_valid = all(
        item.source.dataset == ENTERPRISE_BENCH.name
        and item.source.source_commit == ENTERPRISE_BENCH.source_commit
        and item.source.snapshot_sha256 == ENTERPRISE_BENCH.sha256
        and item.source.synthetic is True
        and bool(item.source.locators)
        for item in evidence_records
    )
    record(
        "approved_source_provenance",
        provenance_valid,
        "every observation identifies the pinned synthetic source",
    )

    evidence_failures: list[str] = []
    observations_by_tool = {
        AnalysisKind(item.method.tool_name): item.result for item in evidence_records
    }
    for expectation in scenario.evidence_expectations:
        actual = _resolve_path(
            observations_by_tool.get(expectation.analysis, _MISSING), expectation.path
        )
        if actual != expectation.expected:
            rendered_actual = "missing" if actual is _MISSING else repr(actual)
            evidence_failures.append(
                f"{expectation.analysis.value}.{expectation.path} was {rendered_actual}, "
                f"expected {expectation.expected!r}"
            )
    record(
        "deterministic_evidence",
        not evidence_failures,
        "all evidence anchors matched" if not evidence_failures else "; ".join(evidence_failures),
    )

    planned_hypotheses = {item.hypothesis_id for item in state.plan.hypotheses}
    assessed_hypotheses = {item.hypothesis_id for item in state.conclusion.hypothesis_assessments}
    record(
        "complete_hypothesis_assessment",
        planned_hypotheses == assessed_hypotheses,
        f"assessed {len(assessed_hypotheses)} of {len(planned_hypotheses)} hypotheses",
    )

    cited = (
        {evidence_id for item in state.conclusion.findings for evidence_id in item.evidence_ids}
        | {
            evidence_id
            for item in state.conclusion.hypothesis_assessments
            for evidence_id in item.evidence_ids
        }
        | {
            evidence_id
            for item in state.conclusion.business_implications
            for evidence_id in item.evidence_ids
        }
        | set(state.conclusion.recommendation.evidence_ids)
    )
    ungrounded = cited - state.evidence_ledger.evidence_ids
    record(
        "grounded_citations",
        not ungrounded,
        (
            "all claims cite immutable evidence records"
            if not ungrounded
            else "unknown evidence IDs: " + ", ".join(sorted(ungrounded))
        ),
    )

    cited_claim_count = (
        len(state.conclusion.findings)
        + len(state.conclusion.hypothesis_assessments)
        + len(state.conclusion.business_implications)
        + 1
    )
    all_claims_cited = all(item.evidence_ids for item in state.conclusion.findings)
    all_claims_cited = all_claims_cited and all(
        item.evidence_ids for item in state.conclusion.hypothesis_assessments
    )
    all_claims_cited = all_claims_cited and all(
        item.evidence_ids for item in state.conclusion.business_implications
    )
    all_claims_cited = all_claims_cited and bool(state.conclusion.recommendation.evidence_ids)
    record(
        "complete_claim_citations",
        all_claims_cited,
        f"all {cited_claim_count} material claims include evidence citations",
    )

    source_snapshots = {
        (item.source.source_id, item.source.source_commit) for item in evidence_records
    }
    source_agreement_calibrated = not (
        len(source_snapshots) == 1
        and state.conclusion.confidence.source_agreement != "not_assessed"
    )
    record(
        "source_agreement_calibration",
        source_agreement_calibrated,
        (
            "source agreement is correctly not assessed for one source snapshot"
            if len(source_snapshots) == 1 and source_agreement_calibrated
            else "source agreement reflects independent source snapshots"
            if source_agreement_calibrated
            else "multiple reports from one snapshot were treated as independent sources"
        ),
    )

    conclusion_text = state.conclusion.model_dump_json().lower()
    has_non_revenue_metric = any(
        item.method.metric_definition is not None
        and "not recognized revenue" in item.method.metric_definition.lower()
        for item in evidence_records
    )
    metric_definition_preserved = not (
        has_non_revenue_metric and has_revenue_metric_conflation(conclusion_text)
    )
    record(
        "metric_definition_preserved",
        metric_definition_preserved,
        (
            "conclusion preserves the evidence metric definitions"
            if metric_definition_preserved
            else "closed-won opportunity ACV was incorrectly described as revenue"
        ),
    )

    false_statistics = has_unsupported_statistical_language(conclusion_text)
    record(
        "no_unsupported_statistics",
        not false_statistics,
        "no unperformed statistical test is claimed",
    )

    causal_restraint = not scenario.require_causal_restraint or (
        all(item.status == "inconclusive" for item in state.conclusion.hypothesis_assessments)
        and state.conclusion.confidence.level != "high"
        and bool(state.conclusion.limitations)
        and bool(state.conclusion.unresolved_questions)
    )
    record(
        "causal_restraint",
        causal_restraint,
        (
            "causal claims remain inconclusive and explicitly limited"
            if scenario.require_causal_restraint
            else "not required for this scenario"
        ),
    )

    causal_language_appropriate = (
        MANDATORY_CAUSAL_SENTENCE in state.conclusion.executive_summary.lower()
        if scenario.require_causal_restraint
        else not has_causal_attribution_language(conclusion_text)
    )
    record(
        "question_appropriate_causal_language",
        causal_language_appropriate,
        (
            "causal attribution language matches the question type"
            if causal_language_appropriate
            else "a non-causal question received the causal-attribution boilerplate"
        ),
    )

    record(
        "model_request_budget",
        state.usage.total_requests <= scenario.max_model_requests,
        f"used {state.usage.total_requests} of {scenario.max_model_requests} allowed requests",
    )

    passed_count = sum(check.passed for check in checks)
    return ScenarioEvaluation(
        scenario_id=scenario.scenario_id,
        passed=passed_count == len(checks),
        score_percent=round(passed_count / len(checks) * 100, 1),
        checks=tuple(checks),
    )


def run_evaluation_suite(
    run_case: Callable[[str], InvestigationState],
    scenarios: Sequence[EvaluationScenario] = DEFAULT_SCENARIOS,
) -> EvaluationSuiteResult:
    """Run a bounded scenario suite while preserving failures as auditable results."""

    suite_started = time.perf_counter()
    runs: list[ScenarioRun] = []
    for scenario in scenarios:
        started = time.perf_counter()
        try:
            state = run_case(scenario.question)
            evaluation = evaluate_investigation(scenario, state)
            error = None
        except Exception as exc:  # a qualification suite must preserve per-case diagnostics
            state = None
            evaluation = None
            error = f"{type(exc).__name__}: {exc}"
        runs.append(
            ScenarioRun(
                scenario=scenario,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                evaluation=evaluation,
                state=state,
                error=error,
            )
        )

    passed = sum(run.evaluation is not None and run.evaluation.passed for run in runs)
    return EvaluationSuiteResult(
        all_passed=passed == len(runs) and bool(runs),
        passed_scenarios=passed,
        total_scenarios=len(runs),
        elapsed_seconds=round(time.perf_counter() - suite_started, 3),
        runs=tuple(runs),
    )
