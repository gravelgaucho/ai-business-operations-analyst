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


DataSource = Path | BusinessDataRepository


def as_repository(source: DataSource) -> BusinessDataRepository:
    if isinstance(source, Path):
        return JsonEnterpriseBenchRepository(source)
    if isinstance(source, BusinessDataRepository):
        return source
    raise TypeError(f"Unsupported business data source: {type(source).__name__}")
