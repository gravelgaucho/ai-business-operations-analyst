from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from business_ops.analytics.types import MetricRecord
from business_ops.datasets.enterprise_bench import (
    AccountRisk,
    ProductAreaRisk,
    opportunity_metric_records,
    rank_account_risk,
    rank_product_area_risk,
)
from business_ops.datasets.query_types import (
    OpportunityBreakdownQuery,
    OpportunityBreakdownRow,
    OpportunityDimension,
)


@runtime_checkable
class BusinessDataRepository(Protocol):
    """Model-neutral read boundary for structured business evidence."""

    def opportunity_metric_records(
        self, *, stage: str = "closed_won", currency: str = "USD"
    ) -> list[MetricRecord]: ...

    def rank_account_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 5,
    ) -> list[AccountRisk]: ...

    def rank_product_area_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p0", "p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 10,
    ) -> list[ProductAreaRisk]: ...

    def query_closed_won_opportunity_acv(
        self, query: OpportunityBreakdownQuery
    ) -> list[OpportunityBreakdownRow]: ...


class JsonEnterpriseBenchRepository:
    """Reference adapter over the authenticated source JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def opportunity_metric_records(
        self, *, stage: str = "closed_won", currency: str = "USD"
    ) -> list[MetricRecord]:
        return opportunity_metric_records(self.root, stage=stage, currency=currency)

    def rank_account_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 5,
    ) -> list[AccountRisk]:
        return rank_account_risk(
            self.root,
            priorities=priorities,
            open_statuses=open_statuses,
            top_n=top_n,
        )

    def rank_product_area_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p0", "p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 10,
    ) -> list[ProductAreaRisk]:
        return rank_product_area_risk(
            self.root,
            priorities=priorities,
            open_statuses=open_statuses,
            top_n=top_n,
        )

    def query_closed_won_opportunity_acv(
        self, query: OpportunityBreakdownQuery
    ) -> list[OpportunityBreakdownRow]:
        records = self.opportunity_metric_records(
            stage="closed_won", currency=query.currency.value
        )
        grouped: dict[tuple[str, ...], int] = {}
        for record in records:
            if not query.start_date <= record.date <= query.end_date:
                continue
            values = {
                OpportunityDimension.ACCOUNT: f"{record.entity_name} ({record.entity_id})",
                OpportunityDimension.REGION: record.segment,
                OpportunityDimension.CLOSE_MONTH: record.date.strftime("%Y-%m"),
                OpportunityDimension.CLOSE_QUARTER: (
                    f"{record.date.year}-Q{(record.date.month - 1) // 3 + 1}"
                ),
            }
            key = tuple(values[dimension] for dimension in query.dimensions)
            grouped[key] = grouped.get(key, 0) + int(record.value)
        ordered = sorted(grouped.items(), key=lambda item: (-item[1], item[0]))[: query.top_n]
        return [
            OpportunityBreakdownRow(
                dimensions={
                    dimension.value: key[index]
                    for index, dimension in enumerate(query.dimensions)
                },
                closed_won_opportunity_acv=value,
            )
            for key, value in ordered
        ]


DataSource = Path | BusinessDataRepository


def as_repository(source: DataSource) -> BusinessDataRepository:
    if isinstance(source, Path):
        return JsonEnterpriseBenchRepository(source)
    if isinstance(source, BusinessDataRepository):
        return source
    raise TypeError(f"Unsupported business data source: {type(source).__name__}")
