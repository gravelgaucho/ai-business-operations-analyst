from __future__ import annotations

import asyncio
import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext, UsageLimits
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from business_ops.analyst import ToolCallTrace, UsageSummary
from business_ops.catalog import DEFAULT_CATALOG, CapabilityCatalog
from business_ops.config import Settings
from business_ops.datasets.download import DatasetImportError, verify_dataset
from business_ops.datasets.enterprise_bench import EnterpriseBenchDataError, default_data_root
from business_ops.datasets.query_types import (
    OpportunityBreakdownQuery,
    OpportunityDimension,
)
from business_ops.datasets.repository import BusinessDataRepository, DataSource
from business_ops.datasets.sqlite_store import (
    SqliteEnterpriseBenchRepository,
    SqliteStoreError,
)
from business_ops.provenance import (
    AuditBundle,
    AuditClaim,
    ClaimType,
    EvidenceLedger,
    EvidenceRecord,
    build_evidence_record,
    investigation_id,
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
    opportunity_breakdown_report,
    pipeline_change_report,
    product_risk_report,
    support_pipeline_link_report,
)

PLAN_USAGE_LIMITS = UsageLimits(request_limit=3)
STEP_USAGE_LIMITS = UsageLimits(request_limit=3)
SYNTHESIS_USAGE_LIMITS = UsageLimits(request_limit=4)
MAX_ANALYSIS_STEPS = 4
UNSUPPORTED_STATISTICAL_LANGUAGE = (
    "statistical significance",
    "statistically significant",
    "significantly higher",
    "significantly lower",
    "significantly different",
)
MANDATORY_CAUSAL_SENTENCE = (
    "the available evidence does not support attribution; causation remains unresolved."
)
CAUSAL_ATTRIBUTION_LANGUAGE = (
    MANDATORY_CAUSAL_SENTENCE,
    "causal attribution",
    "causal inference",
    "causal impact",
    "establish causation",
)
DECISIVE_CAUSAL_PHRASES = ("caused the", "drove the", "driven by", "primary driver")
CAUSAL_UNCERTAINTY_MARKERS = (
    "cannot",
    "could not",
    "does not support",
    "insufficient",
    "no evidence",
    "not enough",
    "not established",
    "not sufficient",
    "unable",
    "uncertain",
    "unknown",
    "unresolved",
    "whether",
)


class InvestigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AnalysisKind(StrEnum):
    ACCOUNT_SUPPORT_RISK = "get_account_support_risk"
    PRODUCT_AREA_SUPPORT_RISK = "get_product_area_support_risk"
    CLOSED_WON_PIPELINE = "compare_closed_won_pipeline"
    SUPPORT_PIPELINE_OVERLAP = "test_support_pipeline_overlap"
    GOVERNED_OPPORTUNITY_BREAKDOWN = "query_closed_won_opportunity_acv"


EvidenceId = Annotated[str, Field(pattern=r"^EV-[0-9a-f]{16}$")]


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
    dimensions: list[OpportunityDimension] = Field(
        default_factory=lambda: [OpportunityDimension.REGION],
        min_length=1,
        max_length=2,
    )

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
        if self.analysis == AnalysisKind.GOVERNED_OPPORTUNITY_BREAKDOWN and (
            self.current_start is None or self.current_end is None
        ):
            raise ValueError("governed opportunity queries require an explicit current period")
        return self


class Finding(InvestigationModel):
    finding_id: str = Field(pattern=r"^F[1-9][0-9]*$")
    statement: str = Field(min_length=1)
    claim_type: Literal["verified_fact", "analytical_finding"]
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=4)


class HypothesisAssessment(InvestigationModel):
    hypothesis_id: str = Field(pattern=r"^H[1-9][0-9]*$")
    status: Literal["supported", "rejected", "inconclusive"]
    rationale: str = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=4)


class BusinessImplication(InvestigationModel):
    implication_id: str = Field(pattern=r"^I[1-9][0-9]*$")
    statement: str = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=6)


class Recommendation(InvestigationModel):
    recommendation_id: str = Field(pattern=r"^R[1-9][0-9]*$")
    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=6)
    human_review_required: Literal[True]


class ConfidenceAssessment(InvestigationModel):
    level: Literal["low", "medium", "high"]
    rationale: str = Field(min_length=1)
    evidence_coverage: Literal["limited", "partial", "strong"]
    source_agreement: Literal["not_assessed", "mixed", "consistent"]
    data_quality: Literal["limited", "adequate", "strong"]


class InvestigationConclusion(InvestigationModel):
    executive_summary: str = Field(min_length=1)
    findings: list[Finding] = Field(min_length=1, max_length=6)
    hypothesis_assessments: list[HypothesisAssessment] = Field(min_length=1, max_length=3)
    business_implications: list[BusinessImplication] = Field(min_length=1, max_length=4)
    recommendation: Recommendation
    confidence: ConfidenceAssessment
    unresolved_questions: list[str] = Field(max_length=6)
    limitations: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> InvestigationConclusion:
        finding_ids = [finding.finding_id for finding in self.findings]
        hypothesis_ids = [item.hypothesis_id for item in self.hypothesis_assessments]
        implication_ids = [item.implication_id for item in self.business_implications]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding IDs must be unique")
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("hypothesis assessment IDs must be unique")
        if len(implication_ids) != len(set(implication_ids)):
            raise ValueError("business implication IDs must be unique")
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


class ClassificationCorrection(InvestigationModel):
    model_output: QuestionType
    enforced: QuestionType
    reason: str


class PlanCorrection(InvestigationModel):
    removed_analyses: list[AnalysisKind] = Field(min_length=1)
    enforced_analyses: list[AnalysisKind] = Field(min_length=2)
    reason: str


class ConclusionCorrection(InvestigationModel):
    corrected_sections: list[str] = Field(min_length=1)
    triggering_rules: list[str] = Field(min_length=1)
    reason: str


class InvestigationState(InvestigationModel):
    original_question: str
    capability_catalog: CapabilityCatalog
    plan: InvestigationPlan
    classification_correction: ClassificationCorrection | None = None
    plan_correction: PlanCorrection | None = None
    conclusion_correction: ConclusionCorrection | None = None
    decisions: list[AnalysisDecision]
    actions: list[ToolCallTrace]
    observations: list[ToolObservation]
    evidence_ledger: EvidenceLedger
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
    evidence_ledger: EvidenceLedger
    validation_failures: list[str] = field(default_factory=list, compare=False)


PLANNER_INSTRUCTIONS = """
Convert the user's business question into a bounded investigation plan; do not answer it.

Classify the question using only stated or clearly implied details. Predictive means the user
explicitly asks to forecast an unknown future outcome. Prescriptive means the user asks what
action to take or what to review first. Descriptive means the user asks for a current ranking
or measurement. Never classify prioritization from current measured exposure as predictive.
Propose one or two falsifiable hypotheses and two or three steps using only capability IDs
present in the supplied approved catalog. Use at least two distinct analyses. For a possible
support-versus-pipeline relationship, include test_support_pipeline_overlap so Python—not
the language model—performs the cross-system comparison. Define observable success criteria
that match what these tools can actually measure. Do not claim that association proves
causation, and list missing information in the nested question classification. None of the
available analyses calculates statistical significance, a correlation coefficient, or
historical ticket status, so never promise those measurements in a success criterion.
For a causal question, frame every hypothesis as a measurable association screen. Do not
write a null hypothesis that says another factor caused or drove the outcome, because the
available reports cannot establish either the proposed cause or an alternative cause.

Use pipeline analyses only when the question explicitly asks about pipeline, opportunity ACV,
a period change, or a relationship between support and business performance. For a question
that asks only which accounts and product areas to review because of current support exposure,
use exactly get_account_support_risk and get_product_area_support_risk; do not include either
pipeline analysis. For a causal support-versus-pipeline question, use exactly
compare_closed_won_pipeline and test_support_pipeline_overlap; the overlap report already
includes the account support-risk set, so a separate account or product-risk report is redundant.
Use query_closed_won_opportunity_acv when the question requests a flexible breakdown by
account, region, close month, or close quarter. It accepts only cataloged dimensions and must
not be described as arbitrary SQL. Pair it with compare_closed_won_pipeline when a question
asks for both a period comparison and a dimensional breakdown.
""".strip()


STEP_INSTRUCTIONS = """
Select exactly one next analysis for a bounded investigation of the approved synthetic
Maple Payments data. Choose only from the allowed analyses supplied in the prompt. Base the
choice on the investigation plan and the observations already returned. Do not answer the
business question and do not repeat an analysis. Supply explicit ISO dates for pipeline
analyses; Q1 2026 is 2026-01-01 through 2026-03-31 and Q4 2025 is 2025-10-01 through
2025-12-31. Use P1 when the question asks about P1 tickets and USD when it asks about USD.
For query_closed_won_opportunity_acv, set current_start/current_end to the requested breakdown
period and choose only account, region, close_month, or close_quarter dimensions.
The application—not you—will execute the calculation and enforce the stopping rule.
""".strip()


SYNTHESIS_INSTRUCTIONS = """
Produce a decision-ready conclusion using only the supplied plan and evidence ledger.
All arithmetic, joins, rankings, and cross-system comparisons came from deterministic tools;
preserve their exact values and two-decimal percentages. Cite evidence records by their exact
EV- identifier; every finding, hypothesis assessment, business implication, and recommendation
must cite at least one supplied evidence record. Classify a directly reported value as a
verified_fact and a calculated comparison or cross-source interpretation as an
analytical_finding. Assess every planned hypothesis as supported, rejected, or inconclusive.
Recommendations must require human review and must explain how their cited findings motivate
the proposed next step; never imply that an external action was taken. Confidence must explain
evidence coverage, source agreement, and data quality. Never claim that an unperformed
statistical test was performed. The current report catalog contains no statistical-test result,
so describe numerical differences with exact values or neutral terms such as material.
Multiple tools or reports from one dataset do not constitute independent source agreement; set
source_agreement to not_assessed when every evidence record has the same source and snapshot.
Preserve every supplied metric definition exactly. In particular, never rename closed-won
opportunity ACV as revenue. If the distinction is relevant, the only permitted wording is the
explicit boundary that opportunity ACV is not recognized revenue.
Use no more than three findings and keep the executive summary under 100 words. Include at
least one business implication, clearly distinguished from verified facts and analytical
findings. Follow the question-type policy supplied with the investigation; do not introduce
causal, predictive, or other analytical framing that the user did not request.
""".strip()


def planner_instructions(catalog: CapabilityCatalog = DEFAULT_CATALOG) -> str:
    return (
        PLANNER_INSTRUCTIONS
        + "\n\nApproved source and analytical-capability catalog:\n"
        + json.dumps(catalog.planning_context(), indent=2)
    )


def create_planner(
    model: Model, catalog: CapabilityCatalog = DEFAULT_CATALOG
) -> Agent[None, InvestigationPlan]:
    agent = Agent(
        model,
        output_type=NativeOutput(
            InvestigationPlan,
            name="investigation_plan",
            description="A bounded, testable business investigation plan.",
            strict=True,
        ),
        instructions=planner_instructions(catalog),
        model_settings={"temperature": 0.0, "max_tokens": 1200},
        retries={"output": 2},
    )

    @agent.output_validator
    def validate_catalog_scope(
        _ctx: RunContext[None], output: InvestigationPlan
    ) -> InvestigationPlan:
        unavailable = {
            step.analysis.value for step in output.steps
        } - catalog.capability_ids
        if unavailable:
            raise ModelRetry(
                "Use only analyses in the approved capability catalog. Remove: "
                f"{sorted(unavailable)}."
            )
        return output

    return agent


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
            _validate_completed_investigation(
                ctx.deps.plan,
                list(ctx.deps.actions),
                ctx.deps.evidence_ledger,
                output,
                enforce_correctable_policies=False,
            )
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
    if decision.analysis == AnalysisKind.GOVERNED_OPPORTUNITY_BREAKDOWN:
        return {
            "start_date": decision.current_start,
            "end_date": decision.current_end,
            "dimensions": [item.value for item in decision.dimensions],
            "currency": decision.currency,
            "top_n": decision.top_n,
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


def _explicit_question_type(question: str) -> QuestionType | None:
    lowered = question.lower()
    if re.search(r"\b(why|cause|caused|causing|driver|drove|driven|explain|explained)\b", lowered):
        return QuestionType.CAUSAL
    if re.search(r"\b(forecast|predict|project|projected|future|will)\b", lowered):
        return QuestionType.PREDICTIVE
    if re.search(r"\b(should|recommend|recommendation|prioritize)\b|review first", lowered):
        return QuestionType.PRESCRIPTIVE
    if re.search(r"\b(versus|compare|compared)\b", lowered):
        return QuestionType.COMPARATIVE
    return None


def _quarter_range(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return date(year, start_month, 1), date(
        year, end_month, calendar.monthrange(year, end_month)[1]
    )


def _explicit_quarter_comparison(question: str) -> tuple[date, date, date, date] | None:
    matches = {
        (int(year), int(quarter))
        for quarter, year in re.findall(r"\bQ([1-4])\s*(20\d{2})\b", question, re.IGNORECASE)
    }
    if len(matches) != 2:
        return None
    ordered = sorted(_quarter_range(year, quarter) for year, quarter in matches)
    previous, current = ordered
    return current[0], current[1], previous[0], previous[1]


def _apply_explicit_periods(
    decision: AnalysisDecision, periods: tuple[date, date, date, date] | None
) -> AnalysisDecision:
    if periods is None or decision.analysis not in {
        AnalysisKind.CLOSED_WON_PIPELINE,
        AnalysisKind.SUPPORT_PIPELINE_OVERLAP,
        AnalysisKind.GOVERNED_OPPORTUNITY_BREAKDOWN,
    }:
        return decision
    current_start, current_end, previous_start, previous_end = periods
    return decision.model_copy(
        update={
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end,
        }
    )


def _apply_domain_relevance_guard(
    question: str, plan: InvestigationPlan
) -> tuple[InvestigationPlan, PlanCorrection | None]:
    """Remove redundant tools for the two qualified Maple question patterns."""

    lowered = question.lower()
    support_terms = ("support", "ticket", "p1")
    pipeline_terms = ("pipeline", "opportunity", "acv", "closed-won", "closed_won")
    allowed: set[AnalysisKind] | None = None
    reason = ""
    if (
        any(term in lowered for term in support_terms)
        and any(term in lowered for term in pipeline_terms)
        and _explicit_question_type(question) == QuestionType.CAUSAL
    ):
        allowed = {
            AnalysisKind.CLOSED_WON_PIPELINE,
            AnalysisKind.SUPPORT_PIPELINE_OVERLAP,
        }
        reason = (
            "The cross-system overlap report already includes the account support-risk set; "
            "separate support rankings are redundant for this causal screen."
        )
    elif (
        "account" in lowered
        and "product area" in lowered
        and any(term in lowered for term in support_terms)
        and not any(term in lowered for term in pipeline_terms)
    ):
        allowed = {
            AnalysisKind.ACCOUNT_SUPPORT_RISK,
            AnalysisKind.PRODUCT_AREA_SUPPORT_RISK,
        }
        reason = (
            "The question asks only for current account and product-area support exposure; "
            "pipeline analyses are outside its scope."
        )
    if allowed is None:
        return plan, None

    retained = [step for step in plan.steps if step.analysis in allowed]
    retained_analyses = {step.analysis for step in retained}
    removed = [step.analysis for step in plan.steps if step.analysis not in allowed]
    if not removed or retained_analyses != allowed:
        return plan, None
    corrected = InvestigationPlan.model_validate(
        plan.model_dump(mode="python") | {"steps": retained}
    )
    return corrected, PlanCorrection(
        removed_analyses=list(dict.fromkeys(removed)),
        enforced_analyses=sorted(allowed, key=lambda item: item.value),
        reason=reason,
    )


def _execute_analysis(source: DataSource, decision: AnalysisDecision) -> Any:
    arguments = _decision_arguments(decision)
    try:
        if decision.analysis == AnalysisKind.ACCOUNT_SUPPORT_RISK:
            return account_risk_report(source, AccountRiskQuery.model_validate(arguments))
        if decision.analysis == AnalysisKind.PRODUCT_AREA_SUPPORT_RISK:
            return product_risk_report(source, ProductRiskQuery.model_validate(arguments))
        if decision.analysis == AnalysisKind.CLOSED_WON_PIPELINE:
            return pipeline_change_report(source, PipelineChangeQuery.model_validate(arguments))
        if decision.analysis == AnalysisKind.GOVERNED_OPPORTUNITY_BREAKDOWN:
            return opportunity_breakdown_report(
                source, OpportunityBreakdownQuery.model_validate(arguments)
            )
        return support_pipeline_link_report(
            source, SupportPipelineLinkQuery.model_validate(arguments)
        )
    except ValidationError as exc:
        raise InvestigationError(f"The selected analysis parameters were invalid: {exc}") from exc


def _evidence_gate_satisfied(plan: InvestigationPlan, used: set[AnalysisKind]) -> bool:
    if len(used) < 2:
        return False
    planned = {step.analysis for step in plan.steps}
    return (
        AnalysisKind.SUPPORT_PIPELINE_OVERLAP not in planned
        or AnalysisKind.SUPPORT_PIPELINE_OVERLAP in used
    )


def has_unsupported_statistical_language(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in UNSUPPORTED_STATISTICAL_LANGUAGE)


def has_causal_attribution_language(text: str) -> bool:
    lowered = text.lower()
    if MANDATORY_CAUSAL_SENTENCE in lowered:
        return True
    for phrase in CAUSAL_ATTRIBUTION_LANGUAGE:
        if phrase == MANDATORY_CAUSAL_SENTENCE:
            continue
        start = 0
        while (index := lowered.find(phrase, start)) >= 0:
            context = lowered[max(0, index - 120) : index + len(phrase) + 80]
            explicitly_negated = any(
                marker in context for marker in CAUSAL_UNCERTAINTY_MARKERS
            ) or bool(
                re.search(
                    r"\b(?:does|do|did|can|could|is|was|were|has|have|had)\s+not\b|"
                    r"\b(?:cannot|can't|couldn't|no)\b",
                    context,
                )
            )
            if not explicitly_negated:
                return True
            start = index + len(phrase)
    return False


def decisive_causal_phrases(text: str) -> tuple[str, ...]:
    """Find affirmative causal wording while allowing explicit uncertainty framing."""

    lowered = text.lower()
    matched = {
        phrase
        for phrase in ("does not explain", "do not explain", "did not explain")
        if phrase in lowered
    }
    for phrase in DECISIVE_CAUSAL_PHRASES:
        start = 0
        while (index := lowered.find(phrase, start)) >= 0:
            prefix = lowered[max(0, index - 120) : index]
            suffix = lowered[index + len(phrase) : index + len(phrase) + 80]
            uncertainty_before = any(
                marker in prefix for marker in CAUSAL_UNCERTAINTY_MARKERS
            )
            uncertainty_after = phrase == "primary driver" and any(
                marker in suffix
                for marker in (
                    "is not established",
                    "is unclear",
                    "is unknown",
                    "remains unclear",
                    "remains unidentified",
                    "remains unknown",
                    "remains unresolved",
                )
            )
            if not uncertainty_before and not uncertainty_after:
                matched.add(phrase)
            start = index + len(phrase)
    return tuple(sorted(matched))


def has_revenue_metric_conflation(text: str) -> bool:
    lowered = text.lower()
    boundary_removed = re.sub(r"\b(?:this is )?not recognized revenue\b", "", lowered)
    return re.search(r"\brevenue\b", boundary_removed) is not None


def _apply_conclusion_policy(
    plan: InvestigationPlan,
    evidence_ledger: EvidenceLedger,
    conclusion: InvestigationConclusion,
) -> tuple[InvestigationConclusion, ConclusionCorrection | None]:
    """Apply narrow, auditable policy corrections after model synthesis."""

    corrected_sections: list[str] = []
    triggering_rules: list[str] = []

    source_snapshots = {
        (record.source.source_id, record.source.source_commit)
        for record in evidence_ledger.records
    }
    if (
        len(source_snapshots) == 1
        and conclusion.confidence.source_agreement != "not_assessed"
    ):
        rationale = (
            "Evidence coverage and data quality are assessed separately. All current evidence "
            "comes from one source snapshot, so independent source agreement is not assessed."
        )
        if plan.question.question_type == QuestionType.CAUSAL:
            rationale += " Timing and historical records are still needed for attribution."
        conclusion = conclusion.model_copy(
            update={
                "confidence": conclusion.confidence.model_copy(
                    update={"source_agreement": "not_assessed", "rationale": rationale}
                )
            }
        )
        corrected_sections.append("confidence")
        triggering_rules.append("independent_source_agreement")

    if plan.question.question_type == QuestionType.CAUSAL:
        def replace_if_decisive(text: str, replacement: str, section: str) -> str:
            phrases = decisive_causal_phrases(text)
            if not phrases:
                return text
            corrected_sections.append(section)
            triggering_rules.extend(f"causal_overclaim:{phrase}" for phrase in phrases)
            return replacement

        findings = [
            item.model_copy(
                update={
                    "statement": replace_if_decisive(
                        item.statement,
                        "The cited evidence reports a measured result; attribution remains "
                        "unresolved.",
                        f"finding:{item.finding_id}",
                    )
                }
            )
            for item in conclusion.findings
        ]
        assessments = [
            item.model_copy(
                update={
                    "rationale": replace_if_decisive(
                        item.rationale,
                        "The cited evidence measures association, while timing and historical "
                        "records needed for attribution are unavailable.",
                        f"hypothesis:{item.hypothesis_id}",
                    )
                }
            )
            for item in conclusion.hypothesis_assessments
        ]
        safe_implication = (
            "The observed association is a screening signal for further review; the available "
            "evidence cannot resolve attribution without timing and historical records."
        )
        implications = [
            item.model_copy(
                update={"statement": safe_implication}
            )
            for item in conclusion.business_implications
        ]
        recommendation = conclusion.recommendation.model_copy(
            update={
                "statement": (
                    "Have a human review the cited account-level evidence and obtain ticket "
                    "timing and opportunity history before making an attribution."
                ),
                "rationale": (
                    "The current evidence measures association and does not establish event "
                    "sequence."
                ),
            }
        )
        corrected_sections.extend(["business_implications", "recommendation"])
        triggering_rules.append("causal_decision_boundary")
        confidence = conclusion.confidence.model_copy(
            update={
                "rationale": replace_if_decisive(
                    conclusion.confidence.rationale,
                    "Evidence is limited to association measures from one snapshot; timing and "
                    "historical records are unavailable.",
                    "confidence:rationale",
                )
            }
        )
        conclusion = conclusion.model_copy(
            update={
                "executive_summary": replace_if_decisive(
                    conclusion.executive_summary,
                    "The analyses report a measured closed-won opportunity ACV change and a "
                    "support-account overlap. The available evidence does not support "
                    "attribution; causation remains unresolved. Timing and historical evidence "
                    "are needed for attribution.",
                    "executive_summary",
                ),
                "findings": findings,
                "hypothesis_assessments": assessments,
                "business_implications": implications,
                "recommendation": recommendation,
                "confidence": confidence,
                "unresolved_questions": [
                    replace_if_decisive(
                        item,
                        "What timing and historical evidence is needed to assess attribution?",
                        "unresolved_question",
                    )
                    for item in conclusion.unresolved_questions
                ],
                "limitations": [
                    replace_if_decisive(
                        item,
                        "The current evidence measures association and lacks causal "
                        "identification.",
                        "limitation",
                    )
                    for item in conclusion.limitations
                ],
            }
        )

    has_non_revenue_metric = any(
        record.method.metric_definition is not None
        and "not recognized revenue" in record.method.metric_definition.lower()
        for record in evidence_ledger.records
    )
    conclusion_text = conclusion.model_dump_json().lower()
    if has_non_revenue_metric and has_revenue_metric_conflation(conclusion_text):
        boundary_token = "__NOT_RECOGNIZED_REVENUE__"

        def normalize_metric(value: Any) -> Any:
            if isinstance(value, str):
                protected = re.sub(
                    r"\b(?:this is )?not recognized revenue\b",
                    boundary_token,
                    value,
                    flags=re.IGNORECASE,
                )
                corrected = re.sub(
                    r"\brevenue\b",
                    "closed-won opportunity ACV",
                    protected,
                    flags=re.IGNORECASE,
                )
                return corrected.replace(boundary_token, "not recognized revenue")
            if isinstance(value, dict):
                return {key: normalize_metric(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize_metric(item) for item in value]
            return value

        conclusion = InvestigationConclusion.model_validate(
            normalize_metric(conclusion.model_dump(mode="python"))
        )
        corrected_sections.append("metric_terminology")
        triggering_rules.append("metric_definition_preservation")

    if not corrected_sections:
        return conclusion, None
    return conclusion, ConclusionCorrection(
        corrected_sections=list(dict.fromkeys(corrected_sections)),
        triggering_rules=list(dict.fromkeys(triggering_rules)),
        reason=(
            "Deterministic policy enforcement corrected model prose or confidence metadata "
            "without changing evidence records, calculations, or citations."
        ),
    )


def _validate_completed_investigation(
    plan: InvestigationPlan,
    actions: list[ToolCallTrace],
    evidence_ledger: EvidenceLedger,
    conclusion: InvestigationConclusion,
    *,
    enforce_correctable_policies: bool = True,
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

    ledger_tools = {AnalysisKind(record.method.tool_name) for record in evidence_ledger.records}
    if ledger_tools != used_tools or len(evidence_ledger.records) != len(actions):
        errors.append("The evidence ledger must contain exactly one record per executed analysis.")

    cited_evidence = (
        {evidence_id for finding in conclusion.findings for evidence_id in finding.evidence_ids}
        | {
            evidence_id
            for assessment in conclusion.hypothesis_assessments
            for evidence_id in assessment.evidence_ids
        }
        | {
            evidence_id
            for implication in conclusion.business_implications
            for evidence_id in implication.evidence_ids
        }
        | set(conclusion.recommendation.evidence_ids)
    )
    missing_evidence = cited_evidence - evidence_ledger.evidence_ids
    if missing_evidence:
        errors.append(
            f"Remove citations to evidence that is not in the ledger: {sorted(missing_evidence)}."
        )

    conclusion_text = conclusion.model_dump_json().lower()
    if has_unsupported_statistical_language(conclusion_text):
        errors.append(
            "Remove statistical-significance language, including 'significantly' higher, "
            "lower, or different; no executed analysis performs a statistical test. State "
            "the exact values and say 'no statistical test was performed' when relevant."
        )

    has_non_revenue_metric = any(
        record.method.metric_definition is not None
        and "not recognized revenue" in record.method.metric_definition.lower()
        for record in evidence_ledger.records
    )
    if (
        enforce_correctable_policies
        and has_non_revenue_metric
        and has_revenue_metric_conflation(conclusion_text)
    ):
        errors.append(
            "Use the exact metric name closed-won opportunity ACV; the evidence explicitly "
            "states that it is not recognized revenue."
        )

    source_snapshots = {
        (record.source.source_id, record.source.source_commit)
        for record in evidence_ledger.records
    }
    if (
        enforce_correctable_policies
        and len(source_snapshots) == 1
        and conclusion.confidence.source_agreement != "not_assessed"
    ):
        errors.append(
            "Set source_agreement to not_assessed; multiple reports from one dataset are not "
            "independent source agreement."
        )

    if plan.question.question_type == QuestionType.CAUSAL:
        if MANDATORY_CAUSAL_SENTENCE not in conclusion.executive_summary.lower():
            errors.append(
                "Include the mandatory causal-restraint sentence in the executive summary."
            )
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
        if conclusion.confidence.level == "high":
            errors.append(
                "Use low or medium confidence because ticket timing and opportunity history "
                "are unavailable."
            )
        conclusion_statements = [
            conclusion.executive_summary,
            *(item.statement for item in conclusion.findings),
            *(item.rationale for item in conclusion.hypothesis_assessments),
            *(item.statement for item in conclusion.business_implications),
            conclusion.recommendation.statement,
            conclusion.recommendation.rationale,
            conclusion.confidence.rationale,
            *conclusion.unresolved_questions,
            *conclusion.limitations,
        ]
        matched_causal_claims = sorted(
            {
                phrase
                for statement in conclusion_statements
                for phrase in decisive_causal_phrases(statement)
            }
        )
        if enforce_correctable_policies and matched_causal_claims:
            triggering_statements = [
                statement
                for statement in conclusion_statements
                if decisive_causal_phrases(statement)
            ]
            errors.append(
                "Replace definitive causal language with 'the available evidence does not "
                "support attribution'; the analyses test association only. Triggering "
                f"phrases: {matched_causal_claims}. Triggering statements: "
                f"{triggering_statements}."
            )
    elif has_causal_attribution_language(conclusion_text):
        errors.append(
            "Remove causal-attribution language from this non-causal investigation; report "
            "only the requested descriptive or comparative evidence."
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
    capability_catalog: CapabilityCatalog = DEFAULT_CATALOG,
    plan_usage_limits: UsageLimits = PLAN_USAGE_LIMITS,
    step_usage_limits: UsageLimits = STEP_USAGE_LIMITS,
    synthesis_usage_limits: UsageLimits = SYNTHESIS_USAGE_LIMITS,
) -> InvestigationState:
    """Plan, control, execute, and synthesize one bounded investigation."""

    question = question.strip()
    if not question:
        raise ValueError("question cannot be empty.")

    root = (data_root or default_data_root()).resolve()
    explicit_type = _explicit_question_type(question)
    explicit_periods = _explicit_quarter_comparison(question)
    classification_correction: ClassificationCorrection | None = None
    plan_correction: PlanCorrection | None = None
    conclusion_correction: ConclusionCorrection | None = None
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
            planner = planner or create_planner(model, capability_catalog)
            selector = selector or create_step_selector(model)
            synthesizer = synthesizer or create_synthesizer(model)

        decisions: list[AnalysisDecision] = []
        actions: list[ToolCallTrace] = []
        observations: list[ToolObservation] = []
        evidence_records: list[EvidenceRecord] = []
        execution_usage_items: list[UsageSummary] = []

        with asyncio.Runner() as runner:
            plan_result = runner.run(planner.run(question, usage_limits=plan_usage_limits))
            plan = plan_result.output
            if explicit_type is not None and plan.question.question_type != explicit_type:
                classification_correction = ClassificationCorrection(
                    model_output=plan.question.question_type,
                    enforced=explicit_type,
                    reason="The original question contains an unambiguous analytical-intent cue.",
                )
                plan = plan.model_copy(
                    update={
                        "question": plan.question.model_copy(
                            update={"question_type": explicit_type}
                        )
                    }
                )
            plan, plan_correction = _apply_domain_relevance_guard(question, plan)
            unavailable = {
                step.analysis.value for step in plan.steps
            } - capability_catalog.capability_ids
            if unavailable:
                raise InvestigationError(
                    "The plan selected analyses absent from the approved capability catalog: "
                    f"{sorted(unavailable)}."
                )
            planned_order = tuple(dict.fromkeys(step.analysis for step in plan.steps))

            while not _evidence_gate_satisfied(plan, {decision.analysis for decision in decisions}):
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
                decision = _apply_explicit_periods(decision_result.output, explicit_periods)
                report = _execute_analysis(source, decision)
                report_content = _json_safe(report)
                observation_id = f"observation_{len(observations) + 1}"
                arguments = _json_safe(_decision_arguments(decision))
                decisions.append(decision)
                actions.append(
                    ToolCallTrace(
                        name=decision.analysis.value,
                        arguments=arguments,
                        returned=True,
                    )
                )
                observations.append(
                    ToolObservation(
                        observation_id=observation_id,
                        tool_name=decision.analysis,
                        content=report_content,
                    )
                )
                evidence_records.append(
                    build_evidence_record(
                        observation_id=observation_id,
                        tool_name=decision.analysis.value,
                        arguments=arguments,
                        result=report_content,
                        source=source,
                        catalog=capability_catalog,
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
            evidence_ledger = EvidenceLedger(records=tuple(evidence_records))
            synthesis_prompt = (
                f"Original business question:\n{question}\n\n"
                f"Validated synthesis scope:\n{json.dumps(synthesis_plan, indent=2)}\n\n"
                "Tamper-evident evidence ledger:\n"
                + evidence_ledger.model_dump_json(indent=2)
                + f"\n\nStop reason:\n{stop_reason}"
            )
            if plan.question.question_type == QuestionType.CAUSAL:
                synthesis_prompt += (
                    "\n\nMandatory causal-language policy:\n"
                    '- Include exactly: "The available evidence does not support attribution; '
                    'causation remains unresolved."\n'
                    "- Mark every hypothesis inconclusive.\n"
                    "- Describe only the measured change and observed association.\n"
                    "- State that timing and historical evidence are needed for attribution.\n"
                    "- Limit the recommendation to human review or further analysis of the "
                    "cited evidence.\n"
                    "- Describe magnitude with exact values or the word material; the evidence "
                    "ledger contains no statistical test."
                )
            else:
                synthesis_prompt += (
                    "\n\nNon-causal scope policy:\n"
                    "- Answer only the requested descriptive, comparative, predictive, or "
                    "prescriptive question.\n"
                    "- Do not discuss causation, causal attribution, or whether evidence "
                    "establishes causation.\n"
                    "- Do not describe current measured exposure as predictive or "
                    "forward-looking."
                )
            synthesis_deps = SynthesisDependencies(
                plan=plan,
                actions=tuple(actions),
                evidence_ledger=evidence_ledger,
            )
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

    conclusion, conclusion_correction = _apply_conclusion_policy(
        plan, evidence_ledger, synthesis_result.output
    )
    _validate_completed_investigation(plan, actions, evidence_ledger, conclusion)
    planning_usage = _usage_summary(plan_result.usage)
    execution_usage = _sum_usage(execution_usage_items, tool_calls=len(actions))
    return InvestigationState(
        original_question=question,
        capability_catalog=capability_catalog,
        plan=plan,
        classification_correction=classification_correction,
        plan_correction=plan_correction,
        conclusion_correction=conclusion_correction,
        decisions=decisions,
        actions=actions,
        observations=observations,
        evidence_ledger=evidence_ledger,
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


def create_audit_bundle(state: InvestigationState) -> AuditBundle:
    """Create a portable, self-contained audit artifact from a completed investigation."""

    claims: list[AuditClaim] = [
        AuditClaim(
            claim_id=finding.finding_id,
            claim_type=ClaimType(finding.claim_type),
            statement=finding.statement,
            evidence_ids=tuple(finding.evidence_ids),
        )
        for finding in state.conclusion.findings
    ]
    claims.extend(
        AuditClaim(
            claim_id=assessment.hypothesis_id,
            claim_type=ClaimType.HYPOTHESIS_ASSESSMENT,
            statement=f"{assessment.status}: {assessment.rationale}",
            evidence_ids=tuple(assessment.evidence_ids),
        )
        for assessment in state.conclusion.hypothesis_assessments
    )
    claims.extend(
        AuditClaim(
            claim_id=implication.implication_id,
            claim_type=ClaimType.BUSINESS_IMPLICATION,
            statement=implication.statement,
            evidence_ids=tuple(implication.evidence_ids),
        )
        for implication in state.conclusion.business_implications
    )
    recommendation = state.conclusion.recommendation
    claims.append(
        AuditClaim(
            claim_id=recommendation.recommendation_id,
            claim_type=ClaimType.RECOMMENDATION,
            statement=recommendation.statement,
            evidence_ids=tuple(recommendation.evidence_ids),
        )
    )

    unique_sources = {
        json.dumps(record.source.model_dump(mode="json"), sort_keys=True): record.source
        for record in state.evidence_ledger.records
    }
    controller_corrections: list[dict[str, Any]] = []
    if state.classification_correction is not None:
        controller_corrections.append(
            {
                "correction_type": "question_classification",
                **state.classification_correction.model_dump(mode="json"),
            }
        )
    if state.plan_correction is not None:
        controller_corrections.append(
            {
                "correction_type": "analysis_scope",
                **state.plan_correction.model_dump(mode="json"),
            }
        )
    if state.conclusion_correction is not None:
        controller_corrections.append(
            {
                "correction_type": "conclusion_policy",
                **state.conclusion_correction.model_dump(mode="json"),
            }
        )
    execution_trace = tuple(
        {
            "decision": decision.model_dump(mode="json"),
            "action": action.model_dump(mode="json"),
            "observation_id": observation.observation_id,
            "evidence_id": evidence.evidence_id,
        }
        for decision, action, observation, evidence in zip(
            state.decisions,
            state.actions,
            state.observations,
            state.evidence_ledger.records,
            strict=True,
        )
    )
    conclusion = state.conclusion.model_dump(mode="json")
    investigation_plan = state.plan.model_dump(mode="json")
    identity_payload = {
        "question": state.original_question,
        "capability_catalog_digest": state.capability_catalog.catalog_digest,
        "investigation_plan": investigation_plan,
        "controller_corrections": controller_corrections,
        "evidence_ids": [record.evidence_id for record in state.evidence_ledger.records],
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "execution_trace": execution_trace,
        "conclusion": conclusion,
    }
    return AuditBundle(
        investigation_id=investigation_id(identity_payload),
        question=state.original_question,
        capability_catalog=state.capability_catalog,
        investigation_plan=investigation_plan,
        controller_corrections=tuple(controller_corrections),
        source_snapshots=tuple(unique_sources.values()),
        evidence_ledger=state.evidence_ledger,
        claims=tuple(claims),
        execution_trace=execution_trace,
        conclusion=conclusion,
    )
