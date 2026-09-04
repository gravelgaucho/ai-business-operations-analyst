from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext, UsageLimits
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from business_ops.analyst import ToolCallTrace, UsageSummary
from business_ops.config import Settings
from business_ops.datasets.download import DatasetImportError, verify_dataset
from business_ops.datasets.enterprise_bench import EnterpriseBenchDataError, default_data_root
from business_ops.datasets.repository import BusinessDataRepository, DataSource
from business_ops.datasets.sqlite_store import (
    SqliteEnterpriseBenchRepository,
    SqliteStoreError,
)
from business_ops.questions import BusinessQuestion, QuestionType
from business_ops.reports import (
    AccountRiskQuery,
    Currency,
    PipelineChangeQuery,
    ProductRiskQuery,
    SupportPipelineLinkQuery,
    TicketPriority,
    account_risk_report,
    pipeline_change_report,
    product_risk_report,
    support_pipeline_link_report,
)

PLAN_USAGE_LIMITS = UsageLimits(request_limit=3)
STEP_USAGE_LIMITS = UsageLimits(request_limit=3)
SYNTHESIS_USAGE_LIMITS = UsageLimits(request_limit=4)
MAX_ANALYSIS_STEPS = 4


class InvestigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AnalysisKind(StrEnum):
    ACCOUNT_SUPPORT_RISK = "get_account_support_risk"
    PRODUCT_AREA_SUPPORT_RISK = "get_product_area_support_risk"
    CLOSED_WON_PIPELINE = "compare_closed_won_pipeline"
    SUPPORT_PIPELINE_OVERLAP = "test_support_pipeline_overlap"


class PlannedHypothesis(InvestigationModel):
    hypothesis_id: str = Field(pattern=r"^H[1-9][0-9]*$")
    statement: str = Field(min_length=1)
    test: str = Field(min_length=1)


class PlanStep(InvestigationModel):
    step_id: str = Field(pattern=r"^step_[1-9][0-9]*$")
    analysis: AnalysisKind
    purpose: str = Field(min_length=1)
    success_criterion: str = Field(min_length=1)


class InvestigationPlan(InvestigationModel):
    question: BusinessQuestion
    objective: str = Field(min_length=1)
    hypotheses: list[PlannedHypothesis] = Field(min_length=1, max_length=3)
    steps: list[PlanStep] = Field(min_length=2, max_length=4)
    stop_conditions: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def plan_is_bounded_and_distinct(self) -> InvestigationPlan:
        step_ids = [step.step_id for step in self.steps]
        hypothesis_ids = [hypothesis.hypothesis_id for hypothesis in self.hypotheses]
        analyses = {step.analysis for step in self.steps}
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("plan step IDs must be unique")
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("hypothesis IDs must be unique")
        if len(analyses) < 2:
            raise ValueError("an investigation plan must use at least two distinct analyses")
        return self


class AnalysisDecision(InvestigationModel):
    analysis: AnalysisKind
    rationale: str = Field(min_length=1)
    current_start: date | None = None
    current_end: date | None = None
    previous_start: date | None = None
    previous_end: date | None = None
    top_n: int = Field(default=5, ge=1, le=20)
    top_n_decliners: int = Field(default=5, ge=1, le=20)
    priorities: list[TicketPriority] = Field(
        default_factory=lambda: [TicketPriority.P1], min_length=1, max_length=4
    )
    currency: Currency = Currency.USD

    @model_validator(mode="after")
    def dated_analyses_have_explicit_periods(self) -> AnalysisDecision:
        if self.analysis in {
            AnalysisKind.CLOSED_WON_PIPELINE,
            AnalysisKind.SUPPORT_PIPELINE_OVERLAP,
        }:
            dates = (
                self.current_start,
                self.current_end,
                self.previous_start,
                self.previous_end,
            )
            if any(item is None for item in dates):
                raise ValueError("pipeline analyses require four explicit period dates")
        return self


class Finding(InvestigationModel):
    finding_id: str = Field(pattern=r"^F[1-9][0-9]*$")
    statement: str = Field(min_length=1)
    evidence_type: Literal["direct", "association", "evidence_gap"]
    source_tools: list[AnalysisKind] = Field(min_length=1, max_length=4)


class HypothesisAssessment(InvestigationModel):
    hypothesis_id: str = Field(pattern=r"^H[1-9][0-9]*$")
    status: Literal["supported", "rejected", "inconclusive"]
    rationale: str = Field(min_length=1)
    source_tools: list[AnalysisKind] = Field(min_length=1, max_length=4)


class InvestigationConclusion(InvestigationModel):
    executive_summary: str = Field(min_length=1)
    findings: list[Finding] = Field(min_length=1, max_length=6)
    hypothesis_assessments: list[HypothesisAssessment] = Field(min_length=1, max_length=3)
    recommendation: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]
    unresolved_questions: list[str] = Field(max_length=6)
    limitations: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> InvestigationConclusion:
        finding_ids = [finding.finding_id for finding in self.findings]
        hypothesis_ids = [item.hypothesis_id for item in self.hypothesis_assessments]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding IDs must be unique")
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("hypothesis assessment IDs must be unique")
        return self


class ToolObservation(InvestigationModel):
    observation_id: str
    tool_name: AnalysisKind
    content: Any


class InvestigationUsage(InvestigationModel):
    planning: UsageSummary
    execution: UsageSummary
    total_requests: int
    total_tokens: int
    total_tool_calls: int


class InvestigationState(InvestigationModel):
    original_question: str
    plan: InvestigationPlan
    decisions: list[AnalysisDecision]
    actions: list[ToolCallTrace]
    observations: list[ToolObservation]
    stop_reason: str
    conclusion: InvestigationConclusion
    usage: InvestigationUsage


class InvestigationError(RuntimeError):
    """Stable application error for a failed controlled investigation."""


@dataclass(frozen=True)
class DecisionDependencies:
    allowed_analyses: tuple[AnalysisKind, ...]
    validation_failures: list[str] = field(default_factory=list, compare=False)


@dataclass(frozen=True)
class SynthesisDependencies:
    plan: InvestigationPlan
    actions: tuple[ToolCallTrace, ...]
    validation_failures: list[str] = field(default_factory=list, compare=False)


PLANNER_INSTRUCTIONS = """
Convert the user's business question into a bounded investigation plan; do not answer it.

Classify the question using only stated or clearly implied details. Propose one or two
falsifiable hypotheses and two or three steps using only these exact analysis names:
get_account_support_risk, get_product_area_support_risk, compare_closed_won_pipeline, and
test_support_pipeline_overlap. Use at least two distinct analyses. For a possible
support-versus-pipeline relationship, include test_support_pipeline_overlap so Python—not
the language model—performs the cross-system comparison. Define observable success criteria
that match what these tools can actually measure. Do not claim that association proves
causation, and list missing information in the nested question classification. None of the
available analyses calculates statistical significance, a correlation coefficient, or
historical ticket status, so never promise those measurements in a success criterion.
""".strip()


STEP_INSTRUCTIONS = """
Select exactly one next analysis for a bounded investigation of the approved synthetic
Maple Payments data. Choose only from the allowed analyses supplied in the prompt. Base the
choice on the investigation plan and the observations already returned. Do not answer the
business question and do not repeat an analysis. Supply explicit ISO dates for pipeline
analyses; Q1 2026 is 2026-01-01 through 2026-03-31 and Q4 2025 is 2025-10-01 through
2025-12-31. Use P1 when the question asks about P1 tickets and USD when it asks about USD.
The application—not you—will execute the calculation and enforce the stopping rule.
""".strip()


SYNTHESIS_INSTRUCTIONS = """
Produce a decision-ready conclusion using only the supplied plan and tool observations.
All arithmetic, joins, rankings, and cross-system comparisons came from deterministic tools;
preserve their exact values and two-decimal percentages. Assess every planned hypothesis as
supported, rejected, or inconclusive and cite only tools that were actually used. A zero or
nonzero account overlap is an association screen, not proof of causation. If ticket timing,
history, or causal evidence is missing, state the gap explicitly. Recommend only human review
or further analysis; never imply that an external action was taken. For a causal question,
the current tools cannot establish causation because ticket timing and history are absent:
all hypotheses must remain inconclusive and confidence cannot be high. Never claim
statistical significance because no available analysis performs a statistical test. Use no
more than three findings and keep the executive summary under 100 words.
""".strip()


def create_planner(model: Model) -> Agent[None, InvestigationPlan]:
    return Agent(
        model,
        output_type=NativeOutput(
            InvestigationPlan,
            name="investigation_plan",
            description="A bounded, testable business investigation plan.",
            strict=True,
        ),
        instructions=PLANNER_INSTRUCTIONS,
        model_settings={"temperature": 0.0, "max_tokens": 1200},
        retries={"output": 2},
    )


def create_step_selector(model: Model) -> Agent[DecisionDependencies, AnalysisDecision]:
    agent = Agent(
        model,
        deps_type=DecisionDependencies,
        output_type=NativeOutput(
            AnalysisDecision,
            name="next_analysis",
            description="The single best next deterministic analysis to execute.",
            strict=True,
        ),
        instructions=STEP_INSTRUCTIONS,
        model_settings={"temperature": 0.0, "max_tokens": 500},
        retries={"output": 2},
    )

    @agent.output_validator
    def validate_selection(
        ctx: RunContext[DecisionDependencies], output: AnalysisDecision
    ) -> AnalysisDecision:
        if output.analysis not in ctx.deps.allowed_analyses:
            allowed = ", ".join(item.value for item in ctx.deps.allowed_analyses)
            message = (
                f"Analysis {output.analysis.value} is not allowed now. Select exactly one "
                f"of: {allowed}."
            )
            ctx.deps.validation_failures.append(message)
            raise ModelRetry(message)
        return output

    return agent


def create_synthesizer(model: Model) -> Agent[SynthesisDependencies, InvestigationConclusion]:
    agent = Agent(
        model,
        deps_type=SynthesisDependencies,
        output_type=NativeOutput(
            InvestigationConclusion,
            name="investigation_conclusion",
            description="A decision-ready conclusion grounded in executed analyses.",
            strict=True,
        ),
        instructions=SYNTHESIS_INSTRUCTIONS,
        model_settings={"temperature": 0.0, "max_tokens": 1100},
        retries={"output": 3},
    )

    @agent.output_validator
    def validate_conclusion(
        ctx: RunContext[SynthesisDependencies], output: InvestigationConclusion
    ) -> InvestigationConclusion:
        try:
            _validate_completed_investigation(ctx.deps.plan, list(ctx.deps.actions), output)
        except InvestigationError as exc:
            ctx.deps.validation_failures.append(str(exc))
            raise ModelRetry(str(exc)) from exc
        return output

    return agent


def _openai_compatible_model(settings: Settings) -> OpenAIChatModel:
    client = AsyncOpenAI(
        api_key="local-not-required",
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
    )
    return OpenAIChatModel(
        settings.model_id,
        provider=OpenAIProvider(openai_client=client),
    )


def _usage_summary(usage: Any) -> UsageSummary:
    return UsageSummary(
        requests=usage.requests,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        tool_calls=usage.tool_calls,
    )


def _sum_usage(items: list[UsageSummary], *, tool_calls: int) -> UsageSummary:
    return UsageSummary(
        requests=sum(item.requests for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
        tool_calls=tool_calls,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _decision_arguments(decision: AnalysisDecision) -> dict[str, Any]:
    if decision.analysis in {
        AnalysisKind.ACCOUNT_SUPPORT_RISK,
        AnalysisKind.PRODUCT_AREA_SUPPORT_RISK,
    }:
        return {
            "top_n": decision.top_n,
            "priorities": [item.value for item in decision.priorities],
        }
    common = {
        "current_start": decision.current_start,
        "current_end": decision.current_end,
        "previous_start": decision.previous_start,
        "previous_end": decision.previous_end,
        "currency": decision.currency,
    }
    if decision.analysis == AnalysisKind.CLOSED_WON_PIPELINE:
        return common | {"top_n": decision.top_n}
    return common | {
        "top_n_decliners": decision.top_n_decliners,
        "priorities": decision.priorities,
    }


def _execute_analysis(source: DataSource, decision: AnalysisDecision) -> Any:
    arguments = _decision_arguments(decision)
    try:
        if decision.analysis == AnalysisKind.ACCOUNT_SUPPORT_RISK:
            return account_risk_report(source, AccountRiskQuery.model_validate(arguments))
        if decision.analysis == AnalysisKind.PRODUCT_AREA_SUPPORT_RISK:
            return product_risk_report(source, ProductRiskQuery.model_validate(arguments))
        if decision.analysis == AnalysisKind.CLOSED_WON_PIPELINE:
            return pipeline_change_report(source, PipelineChangeQuery.model_validate(arguments))
        return support_pipeline_link_report(
            source, SupportPipelineLinkQuery.model_validate(arguments)
        )
    except ValidationError as exc:
        raise InvestigationError(
            f"The selected analysis parameters were invalid: {exc}"
        ) from exc


def _evidence_gate_satisfied(plan: InvestigationPlan, used: set[AnalysisKind]) -> bool:
    if len(used) < 2:
        return False
    planned = {step.analysis for step in plan.steps}
    return (
        AnalysisKind.SUPPORT_PIPELINE_OVERLAP not in planned
        or AnalysisKind.SUPPORT_PIPELINE_OVERLAP in used
    )


def _validate_completed_investigation(
    plan: InvestigationPlan,
    actions: list[ToolCallTrace],
    conclusion: InvestigationConclusion,
) -> None:
    used_tools = {AnalysisKind(action.name) for action in actions if action.returned}
    if not _evidence_gate_satisfied(plan, used_tools):
        raise InvestigationError(
            "Conclusion failed the evidence gate: at least two distinct analyses are required, "
            "including the planned support-pipeline overlap test when applicable."
        )

    errors: list[str] = []
    planned_hypotheses = {hypothesis.hypothesis_id for hypothesis in plan.hypotheses}
    assessed_hypotheses = {
        assessment.hypothesis_id for assessment in conclusion.hypothesis_assessments
    }
    if assessed_hypotheses != planned_hypotheses:
        errors.append("Assess every planned hypothesis exactly once.")

    cited_tools = {
        tool for finding in conclusion.findings for tool in finding.source_tools
    } | {
        tool
        for assessment in conclusion.hypothesis_assessments
        for tool in assessment.source_tools
    }
    if not cited_tools.issubset(used_tools):
        invalid = sorted(tool.value for tool in cited_tools - used_tools)
        errors.append(f"Remove citations to analyses that were not executed: {invalid}.")

    conclusion_text = conclusion.model_dump_json().lower()
    unsupported_statistics = ("statistical significance", "statistically significant")
    if any(phrase in conclusion_text for phrase in unsupported_statistics):
        errors.append(
            "Do not claim statistical significance; no executed analysis performs a "
            "statistical test. Describe only the observed counts and shares."
        )

    if plan.question.question_type == QuestionType.CAUSAL:
        decisive = [
            item.hypothesis_id
            for item in conclusion.hypothesis_assessments
            if item.status != "inconclusive"
        ]
        if decisive:
            errors.append(
                "Mark these causal hypotheses inconclusive because ticket timing and causal "
                f"identification are unavailable: {decisive}."
            )
        if conclusion.confidence == "high":
            errors.append(
                "Use low or medium confidence because ticket timing and opportunity history "
                "are unavailable."
            )
        forbidden_causal_claims = (
            "does not explain",
            "do not explain",
            "did not explain",
            "caused the",
            "drove the",
            "driven by",
            "primary driver",
        )
        if any(phrase in conclusion_text for phrase in forbidden_causal_claims):
            errors.append(
                "Replace definitive causal language with 'the available evidence does not "
                "support attribution'; the analyses test association only."
            )

    if errors:
        raise InvestigationError("Conclusion requires correction: " + " ".join(errors))


def _selector_prompt(
    question: str,
    plan: InvestigationPlan,
    observations: list[ToolObservation],
    allowed: tuple[AnalysisKind, ...],
) -> str:
    evidence = (
        "No analyses have been executed yet."
        if not observations
        else "Observations already returned:\n"
        + "\n".join(
            f"- {item.tool_name.value}: {item.model_dump_json(exclude={'observation_id'})}"
            for item in observations
        )
    )
    return (
        f"Original business question:\n{question}\n\n"
        f"Investigation plan:\n{plan.model_dump_json(indent=2)}\n\n"
        f"{evidence}\n\n"
        "Allowed unused analyses for this decision:\n"
        + "\n".join(f"- {item.value}" for item in allowed)
        + "\n\nSelect the single best next analysis."
    )


def run_investigation(
    question: str,
    *,
    planner: Agent[None, InvestigationPlan] | None = None,
    selector: Agent[DecisionDependencies, AnalysisDecision] | None = None,
    synthesizer: Agent[SynthesisDependencies, InvestigationConclusion] | None = None,
    settings: Settings | None = None,
    data_root: Path | None = None,
    database_path: Path | None = None,
    plan_usage_limits: UsageLimits = PLAN_USAGE_LIMITS,
    step_usage_limits: UsageLimits = STEP_USAGE_LIMITS,
    synthesis_usage_limits: UsageLimits = SYNTHESIS_USAGE_LIMITS,
) -> InvestigationState:
    """Plan, control, execute, and synthesize one bounded investigation."""

    question = question.strip()
    if not question:
        raise ValueError("question cannot be empty.")

    root = (data_root or default_data_root()).resolve()
    decision_deps: DecisionDependencies | None = None
    synthesis_deps: SynthesisDependencies | None = None
    try:
        verify_dataset(root)
        repository: BusinessDataRepository | None = (
            SqliteEnterpriseBenchRepository(database_path, source_root=root)
            if database_path is not None
            else None
        )
        source: DataSource = repository or root
        if planner is None or selector is None or synthesizer is None:
            model = _openai_compatible_model(settings or Settings.from_environment())
            planner = planner or create_planner(model)
            selector = selector or create_step_selector(model)
            synthesizer = synthesizer or create_synthesizer(model)

        decisions: list[AnalysisDecision] = []
        actions: list[ToolCallTrace] = []
        observations: list[ToolObservation] = []
        execution_usage_items: list[UsageSummary] = []

        with asyncio.Runner() as runner:
            plan_result = runner.run(planner.run(question, usage_limits=plan_usage_limits))
            plan = plan_result.output
            planned_order = tuple(dict.fromkeys(step.analysis for step in plan.steps))

            while not _evidence_gate_satisfied(
                plan, {decision.analysis for decision in decisions}
            ):
                if len(decisions) >= MAX_ANALYSIS_STEPS:
                    raise InvestigationError(
                        "The investigation reached its analysis-step limit before satisfying "
                        "the evidence gate."
                    )
                used = {decision.analysis for decision in decisions}
                allowed = tuple(item for item in planned_order if item not in used)
                if not allowed:
                    raise InvestigationError(
                        "The plan ran out of distinct analyses before satisfying the evidence gate."
                    )
                decision_deps = DecisionDependencies(allowed_analyses=allowed)
                decision_result = runner.run(
                    selector.run(
                        _selector_prompt(question, plan, observations, allowed),
                        deps=decision_deps,
                        usage_limits=step_usage_limits,
                    )
                )
                decision = decision_result.output
                report = _execute_analysis(source, decision)
                decisions.append(decision)
                actions.append(
                    ToolCallTrace(
                        name=decision.analysis.value,
                        arguments=_json_safe(_decision_arguments(decision)),
                        returned=True,
                    )
                )
                observations.append(
                    ToolObservation(
                        observation_id=f"observation_{len(observations) + 1}",
                        tool_name=decision.analysis,
                        content=_json_safe(report),
                    )
                )
                execution_usage_items.append(_usage_summary(decision_result.usage))

            stop_reason = (
                "The evidence gate is satisfied: at least two distinct planned analyses "
                "completed, including the support-pipeline overlap test when applicable."
            )
            synthesis_plan = {
                "question_classification": plan.question.model_dump(mode="json"),
                "objective": plan.objective,
                "hypotheses": [item.model_dump(mode="json") for item in plan.hypotheses],
            }
            synthesis_prompt = (
                f"Original business question:\n{question}\n\n"
                f"Validated synthesis scope:\n{json.dumps(synthesis_plan, indent=2)}\n\n"
                "Executed observations:\n"
                + "\n".join(item.model_dump_json(indent=2) for item in observations)
                + f"\n\nStop reason:\n{stop_reason}"
            )
            synthesis_deps = SynthesisDependencies(plan=plan, actions=tuple(actions))
            synthesis_result = runner.run(
                synthesizer.run(
                    synthesis_prompt,
                    deps=synthesis_deps,
                    usage_limits=synthesis_usage_limits,
                )
            )
            execution_usage_items.append(_usage_summary(synthesis_result.usage))
    except (
        AgentRunError,
        UserError,
        DatasetImportError,
        EnterpriseBenchDataError,
        SqliteStoreError,
        InvestigationError,
    ) as exc:
        failures = []
        if decision_deps:
            failures.extend(decision_deps.validation_failures)
        if synthesis_deps:
            failures.extend(synthesis_deps.validation_failures)
        detail = f" Validation feedback: {'; '.join(dict.fromkeys(failures))}" if failures else ""
        raise InvestigationError(f"Investigation failed: {exc}.{detail}") from exc

    conclusion = synthesis_result.output
    _validate_completed_investigation(plan, actions, conclusion)
    planning_usage = _usage_summary(plan_result.usage)
    execution_usage = _sum_usage(execution_usage_items, tool_calls=len(actions))
    return InvestigationState(
        original_question=question,
        plan=plan,
        decisions=decisions,
        actions=actions,
        observations=observations,
        stop_reason=stop_reason,
        conclusion=conclusion,
        usage=InvestigationUsage(
            planning=planning_usage,
            execution=execution_usage,
            total_requests=planning_usage.requests + execution_usage.requests,
            total_tokens=planning_usage.total_tokens + execution_usage.total_tokens,
            total_tool_calls=len(actions),
        ),
    )
