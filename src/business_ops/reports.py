from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from business_ops.analytics import (
    ConcentrationAnalysis,
    DateRange,
    EntityChange,
    SegmentMetric,
    Variance,
    analyze_concentration,
    compare_periods,
    segment_performance,
)
from business_ops.datasets.download import ENTERPRISE_BENCH
from business_ops.datasets.enterprise_bench import (
    AccountRisk,
    ProductAreaRisk,
    opportunity_metric_records,
    rank_account_risk,
    rank_product_area_risk,
)


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TicketPriority(StrEnum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class Currency(StrEnum):
    USD = "USD"
    GBP = "GBP"


class AccountRiskQuery(ReportModel):
    top_n: int = Field(default=5, ge=1, le=20)
    priorities: list[TicketPriority] = Field(
        default_factory=lambda: [TicketPriority.P1], min_length=1, max_length=4
    )


class ProductRiskQuery(ReportModel):
    top_n: int = Field(default=5, ge=1, le=20)
    priorities: list[TicketPriority] = Field(
        default_factory=lambda: [TicketPriority.P1], min_length=1, max_length=4
    )


class PipelineChangeQuery(ReportModel):
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    top_n: int = Field(default=5, ge=1, le=20)
    currency: Currency = Currency.USD


class SupportPipelineLinkQuery(ReportModel):
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    top_n_decliners: int = Field(default=5, ge=1, le=20)
    priorities: list[TicketPriority] = Field(
        default_factory=lambda: [TicketPriority.P1], min_length=1, max_length=4
    )
    currency: Currency = Currency.USD


class SourceMetadata(ReportModel):
    dataset: str
    source_commit: str
    license: str
    synthetic: bool


class AccountRiskSummary(ReportModel):
    affected_accounts: int
    total_arr_at_risk: int


class AccountRiskReport(ReportModel):
    question: str
    source: SourceMetadata
    calculation: str
    summary: AccountRiskSummary
    results: list[AccountRisk]


class ProductRiskReport(ReportModel):
    question: str
    source: SourceMetadata
    calculation: str
    results: list[ProductAreaRisk]


class PipelineChangeReport(ReportModel):
    question: str
    source: SourceMetadata
    metric_definition: str
    comparison: Variance
    current_period: DateRange
    previous_period: DateRange
    largest_decline_contributors: list[EntityChange]
    current_segments: list[SegmentMetric]
    current_concentration: ConcentrationAnalysis


class SupportPipelineAccount(ReportModel):
    decline_rank: int
    account_id: str
    account_name: str
    region: str
    opportunity_acv: Variance
    arr_at_risk: int
    open_ticket_count: int


class SupportPipelineLinkReport(ReportModel):
    question: str
    source: SourceMetadata
    metric_definition: str
    top_decline_accounts_considered: int
    support_risk_accounts: int
    overlapping_accounts: int
    overlap_share_of_top_decline_count_percent: float
    top_decline_absolute_change: int
    overlapping_absolute_change: int
    overlap_share_of_top_decline_change_percent: float
    overlaps: list[SupportPipelineAccount]
    interpretation_boundary: str


def source_metadata() -> SourceMetadata:
    return SourceMetadata(
        dataset=ENTERPRISE_BENCH.name,
        source_commit=ENTERPRISE_BENCH.source_commit,
        license=ENTERPRISE_BENCH.license,
        synthetic=ENTERPRISE_BENCH.synthetic,
    )


def account_risk_report(root: Path, query: AccountRiskQuery) -> AccountRiskReport:
    priorities = frozenset(priority.value for priority in query.priorities)
    all_results = rank_account_risk(root, priorities=priorities, top_n=10_000)
    priority_label = "/".join(sorted(priority.upper() for priority in priorities))
    return AccountRiskReport(
        question=(
            f"Which {query.top_n} accounts have the most ARR exposed to open "
            f"{priority_label} support tickets?"
        ),
        source=source_metadata(),
        calculation=(
            "Rank distinct account ARR for accounts with at least one matching open ticket; "
            "multiple tickets do not multiply ARR."
        ),
        summary=AccountRiskSummary(
            affected_accounts=len(all_results),
            total_arr_at_risk=sum(item.arr_at_risk for item in all_results),
        ),
        results=all_results[: query.top_n],
    )


def product_risk_report(root: Path, query: ProductRiskQuery) -> ProductRiskReport:
    priorities = frozenset(priority.value for priority in query.priorities)
    results = rank_product_area_risk(root, priorities=priorities, top_n=query.top_n)
    priority_label = "/".join(sorted(priority.upper() for priority in priorities))
    return ProductRiskReport(
        question=(
            "Which product areas have the most ARR exposed through open "
            f"{priority_label} support tickets?"
        ),
        source=source_metadata(),
        calculation=(
            "Join open tickets to product components and accounts, then sum each affected "
            "account's ARR once per component."
        ),
        results=results,
    )


def pipeline_change_report(root: Path, query: PipelineChangeQuery) -> PipelineChangeReport:
    current = DateRange(start=query.current_start, end=query.current_end)
    previous = DateRange(start=query.previous_start, end=query.previous_end)
    records = opportunity_metric_records(root, stage="closed_won", currency=query.currency.value)
    comparison = compare_periods(records, current, previous)
    declines = [item for item in comparison.contributors if item.variance.absolute_change < 0][
        : query.top_n
    ]
    return PipelineChangeReport(
        question=(
            "Which accounts contributed most to the change in closed_won "
            f"{query.currency.value} opportunity ACV?"
        ),
        source=source_metadata(),
        metric_definition=(
            "Opportunity ACV grouped by target close date and current final stage. "
            "This is not recognized revenue."
        ),
        comparison=comparison.total,
        current_period=current,
        previous_period=previous,
        largest_decline_contributors=declines,
        current_segments=segment_performance(records, period=current),
        current_concentration=analyze_concentration(records, period=current, top_n=query.top_n),
    )


def support_pipeline_link_report(
    root: Path, query: SupportPipelineLinkQuery
) -> SupportPipelineLinkReport:
    """Measure set overlap without asking the model to perform a cross-system join."""

    current = DateRange(start=query.current_start, end=query.current_end)
    previous = DateRange(start=query.previous_start, end=query.previous_end)
    records = opportunity_metric_records(root, stage="closed_won", currency=query.currency.value)
    comparison = compare_periods(records, current, previous)
    top_declines = [
        item for item in comparison.contributors if item.variance.absolute_change < 0
    ][: query.top_n_decliners]
    priorities = frozenset(priority.value for priority in query.priorities)
    at_risk = {
        item.account_id: item
        for item in rank_account_risk(root, priorities=priorities, top_n=10_000)
    }
    overlaps = [
        SupportPipelineAccount(
            decline_rank=rank,
            account_id=decline.entity_id,
            account_name=decline.entity_name,
            region=decline.segment,
            opportunity_acv=decline.variance,
            arr_at_risk=at_risk[decline.entity_id].arr_at_risk,
            open_ticket_count=at_risk[decline.entity_id].open_ticket_count,
        )
        for rank, decline in enumerate(top_declines, start=1)
        if decline.entity_id in at_risk
    ]
    top_decline_change = sum(abs(item.variance.absolute_change) for item in top_declines)
    overlap_change = sum(abs(item.opportunity_acv.absolute_change) for item in overlaps)
    priority_label = "/".join(sorted(priority.upper() for priority in priorities))
    return SupportPipelineLinkReport(
        question=(
            f"Do accounts with open {priority_label} tickets overlap with the top "
            f"{query.top_n_decliners} closed-won {query.currency.value} opportunity ACV "
            "decline contributors?"
        ),
        source=source_metadata(),
        metric_definition=(
            "Set overlap between accounts with matching open support tickets and the largest "
            "closed-won opportunity ACV declines by target close date."
        ),
        top_decline_accounts_considered=len(top_declines),
        support_risk_accounts=len(at_risk),
        overlapping_accounts=len(overlaps),
        overlap_share_of_top_decline_count_percent=(
            round(len(overlaps) / len(top_declines) * 100, 2) if top_declines else 0.0
        ),
        top_decline_absolute_change=top_decline_change,
        overlapping_absolute_change=overlap_change,
        overlap_share_of_top_decline_change_percent=(
            round(overlap_change / top_decline_change * 100, 2)
            if top_decline_change
            else 0.0
        ),
        overlaps=overlaps,
        interpretation_boundary=(
            "Overlap is an association screen, not evidence that support tickets caused the "
            "opportunity change. Ticket timing and opportunity stage history are not tested."
        ),
    )
