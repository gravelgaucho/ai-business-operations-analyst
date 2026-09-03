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
