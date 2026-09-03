from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_ops.datasets.enterprise_bench import (
    EnterpriseBenchDataError,
    opportunity_metric_records,
    rank_account_risk,
    rank_product_area_risk,
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
        [
            {"account_id": "A", "account_name": "Alpha", "region": "East", "arr": 1000},
            {"account_id": "B", "account_name": "Beta", "region": "West", "arr": 2000},
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
                "acv": 300,
                "target_close_date": "2026-01-15T12:00:00Z",
            },
            {
                "account_id": "B",
                "stage": "proposal",
                "currency": "USD",
                "acv": 900,
                "target_close_date": "2026-02-01",
            },
            {
                "account_id": "B",
                "stage": "closed_won",
                "currency": "GBP",
                "acv": 500,
                "target_close_date": "2026-02-01",
            },
        ],
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
            },
            {
                "ticket_id": "T2",
                "account_id": "A",
                "priority": "p1",
                "status": "open",
                "components": ["P1"],
            },
            {
                "ticket_id": "T3",
                "account_id": "B",
                "priority": "p1",
                "status": "open",
                "components": ["P1"],
            },
            {
                "ticket_id": "T4",
                "account_id": "B",
                "priority": "p1",
                "status": "solved",
                "components": ["P1"],
            },
        ],
    )
    write_records(
        tmp_path,
        "pm_json_data/maple_parts.json",
        [{"part_id": "P1", "title": "Checkout"}],
    )
    return tmp_path


def test_opportunity_adapter_filters_stage_and_currency(dataset: Path) -> None:
    records = opportunity_metric_records(dataset)

    assert len(records) == 1
    assert records[0].entity_name == "Alpha"
    assert records[0].value == 300


def test_account_risk_ranks_distinct_arr_not_arr_times_tickets(dataset: Path) -> None:
    result = rank_account_risk(dataset)

    assert [(item.account_name, item.arr_at_risk) for item in result] == [
        ("Beta", 2000),
        ("Alpha", 1000),
    ]
    assert result[1].open_ticket_count == 2


def test_product_area_risk_joins_accounts_tickets_and_parts(dataset: Path) -> None:
    result = rank_product_area_risk(dataset)

    assert len(result) == 1
    assert result[0].component_name == "Checkout"
    assert result[0].arr_at_risk == 3000
    assert result[0].accounts_at_risk == 2
    assert result[0].open_ticket_count == 3


def test_missing_dataset_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(EnterpriseBenchDataError, match="make data"):
        opportunity_metric_records(tmp_path)
