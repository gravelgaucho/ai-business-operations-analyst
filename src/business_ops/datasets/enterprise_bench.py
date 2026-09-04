from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from business_ops.analytics.types import MetricRecord


class EnterpriseBenchDataError(RuntimeError):
    """Raised when local Enterprise-Bench data is missing or invalid."""


class _SourceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Account(_SourceRecord):
    account_id: str
    account_name: str
    region: str
    arr: int = Field(ge=0)


class Opportunity(_SourceRecord):
    opportunity_id: str | None = None
    account_id: str
    stage: str
    currency: str
    acv: int = Field(ge=0)
    target_close_date: str


class Ticket(_SourceRecord):
    ticket_id: str
    account_id: str
    priority: str
    status: str
    components: list[str]


class ProductPart(_SourceRecord):
    part_id: str
    title: str


class AccountRisk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int
    account_id: str
    account_name: str
    region: str
    arr_at_risk: int
    open_ticket_count: int


class ProductAreaRisk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int
    component_id: str
    component_name: str
    arr_at_risk: int
    accounts_at_risk: int
    open_ticket_count: int


def default_data_root() -> Path:
    configured = os.getenv("ENTERPRISE_BENCH_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "data" / "enterprise_bench"


def load_records[RecordT: BaseModel](
    root: Path, relative_path: str, record_type: type[RecordT]
) -> list[RecordT]:
    path = root / relative_path
    if not path.is_file():
        raise EnterpriseBenchDataError(
            f"Maple Payments data is missing at {path}. Run 'make data'."
        )
    try:
        return TypeAdapter(list[record_type]).validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise EnterpriseBenchDataError(f"Invalid Maple Payments data in {path}: {exc}") from exc


def _accounts(root: Path) -> dict[str, Account]:
    records = load_records(root, "crm_json_data/accounts.json", Account)
    return {record.account_id: record for record in records}


def opportunity_metric_records(
    root: Path,
    *,
    stage: str = "closed_won",
    currency: str = "USD",
) -> list[MetricRecord]:
    accounts = _accounts(root)
    opportunities = load_records(root, "crm_json_data/opportunities.json", Opportunity)
    records: list[MetricRecord] = []
    for opportunity in opportunities:
        if opportunity.stage != stage or opportunity.currency != currency:
            continue
        account = accounts.get(opportunity.account_id)
        if account is None:
            raise EnterpriseBenchDataError(
                f"Opportunity references unknown account {opportunity.account_id}."
            )
        try:
            metric_date = date.fromisoformat(opportunity.target_close_date[:10])
        except ValueError as exc:
            raise EnterpriseBenchDataError(
                f"Invalid opportunity target date: {opportunity.target_close_date}"
            ) from exc
        records.append(
            MetricRecord(
                date=metric_date,
                entity_id=account.account_id,
                entity_name=account.account_name,
                segment=account.region,
                value=opportunity.acv,
            )
        )
    return records


def rank_account_risk(
    root: Path,
    *,
    priorities: frozenset[str] = frozenset({"p1"}),
    open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
    top_n: int = 5,
) -> list[AccountRisk]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    accounts = _accounts(root)
    tickets = load_records(root, "crm_json_data/tickets.json", Ticket)
    counts: dict[str, int] = {}
    for ticket in tickets:
        if ticket.priority in priorities and ticket.status in open_statuses:
            counts[ticket.account_id] = counts.get(ticket.account_id, 0) + 1

    at_risk: list[tuple[Account, int]] = []
    for account_id, count in counts.items():
        account = accounts.get(account_id)
        if account is None:
            raise EnterpriseBenchDataError(f"Ticket references unknown account {account_id}.")
        at_risk.append((account, count))
    at_risk.sort(key=lambda item: (-item[0].arr, -item[1], item[0].account_name))
    return [
        AccountRisk(
            rank=index,
            account_id=account.account_id,
            account_name=account.account_name,
            region=account.region,
            arr_at_risk=account.arr,
            open_ticket_count=count,
        )
        for index, (account, count) in enumerate(at_risk[:top_n], start=1)
    ]


def rank_product_area_risk(
    root: Path,
    *,
    priorities: frozenset[str] = frozenset({"p0", "p1"}),
    open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
    top_n: int = 10,
) -> list[ProductAreaRisk]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    accounts = _accounts(root)
    tickets = load_records(root, "crm_json_data/tickets.json", Ticket)
    parts = {
        record.part_id: record
        for record in load_records(root, "pm_json_data/maple_parts.json", ProductPart)
    }
    account_ids: dict[str, set[str]] = {}
    ticket_counts: dict[str, int] = {}
    for ticket in tickets:
        if ticket.priority not in priorities or ticket.status not in open_statuses:
            continue
        if ticket.account_id not in accounts:
            raise EnterpriseBenchDataError(
                f"Ticket references unknown account {ticket.account_id}."
            )
        for component in ticket.components:
            if component not in parts:
                raise EnterpriseBenchDataError(f"Ticket references unknown component {component}.")
            account_ids.setdefault(component, set()).add(ticket.account_id)
            ticket_counts[component] = ticket_counts.get(component, 0) + 1

    risks = [
        (
            component,
            sum(accounts[account_id].arr for account_id in affected_accounts),
            len(affected_accounts),
            ticket_counts[component],
        )
        for component, affected_accounts in account_ids.items()
    ]
    risks.sort(key=lambda item: (-item[1], -item[2], parts[item[0]].title))
    return [
        ProductAreaRisk(
            rank=index,
            component_id=component,
            component_name=parts[component].title,
            arr_at_risk=arr,
            accounts_at_risk=account_count,
            open_ticket_count=ticket_count,
        )
        for index, (component, arr, account_count, ticket_count) in enumerate(
            risks[:top_n], start=1
        )
    ]
