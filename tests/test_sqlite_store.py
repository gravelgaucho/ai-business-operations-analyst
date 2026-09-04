from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from business_ops.datasets.repository import JsonEnterpriseBenchRepository
from business_ops.datasets.sqlite_store import (
    SqliteEnterpriseBenchRepository,
    SqliteStoreError,
    _read_only_connection,
    build_database,
    validate_database,
)
from business_ops.reports import (
    AccountRiskQuery,
    PipelineChangeQuery,
    ProductRiskQuery,
    SupportPipelineLinkQuery,
    account_risk_report,
    pipeline_change_report,
    product_risk_report,
    support_pipeline_link_report,
)


def write_records(root: Path, relative_path: str, records: list[dict[str, object]]) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


@pytest.fixture
def source_data(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    write_records(
        root,
        "crm_json_data/accounts.json",
        [
            {"account_id": "A", "account_name": "Alpha", "region": "East", "arr": 1000},
            {"account_id": "B", "account_name": "Beta", "region": "West", "arr": 2000},
        ],
    )
    write_records(
        root,
        "crm_json_data/opportunities.json",
        [
            {
                "opportunity_id": "O1",
                "account_id": "A",
                "stage": "closed_won",
                "currency": "USD",
                "acv": 1000,
                "target_close_date": "2025-12-15",
            },
            {
                "opportunity_id": "O2",
                "account_id": "A",
                "stage": "closed_won",
                "currency": "USD",
                "acv": 300,
                "target_close_date": "2026-01-15",
            },
            {
                "opportunity_id": "O3",
                "account_id": "B",
                "stage": "closed_won",
                "currency": "USD",
                "acv": 500,
                "target_close_date": "2026-02-01",
            },
        ],
    )
    write_records(
        root,
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
                "status": "in_progress",
                "components": ["P1"],
            },
            {
                "ticket_id": "T3",
                "account_id": "B",
                "priority": "p2",
                "status": "open",
                "components": ["P2"],
            },
        ],
    )
    write_records(
        root,
        "pm_json_data/maple_parts.json",
        [
            {"part_id": "P1", "title": "Checkout"},
            {"part_id": "P2", "title": "Billing"},
        ],
    )
    return root


@pytest.fixture
def repositories(
    source_data: Path, tmp_path: Path
) -> tuple[JsonEnterpriseBenchRepository, SqliteEnterpriseBenchRepository, Path]:
    database = tmp_path / "derived" / "maple.sqlite3"
    build_database(source_data, database, verify_source=False)
    return (
        JsonEnterpriseBenchRepository(source_data),
        SqliteEnterpriseBenchRepository(database),
        database,
    )


def test_builds_normalized_database_with_provenance_and_indexes(
    source_data: Path, tmp_path: Path
) -> None:
    database = tmp_path / "maple.sqlite3"
    summary = build_database(source_data, database, verify_source=False)

    assert summary.accounts == 2
    assert summary.opportunities == 3
    assert summary.tickets == 3
    assert summary.product_parts == 2
    assert summary.ticket_components == 3
    assert validate_database(database) == summary
    with sqlite3.connect(database) as connection:
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert "idx_opportunities_stage_currency_date" in indexes
    assert "idx_tickets_priority_status_account" in indexes


def test_repository_opens_database_read_only(repositories: tuple[object, object, Path]) -> None:
    database = repositories[2]

    with (
        _read_only_connection(database) as connection,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        connection.execute(
            "INSERT INTO accounts VALUES (99, 'X', 'Unsafe', 'Nowhere', 0)"
        )


def test_sql_repository_matches_json_reference(
    repositories: tuple[
        JsonEnterpriseBenchRepository, SqliteEnterpriseBenchRepository, Path
    ],
) -> None:
    json_repository, sql_repository, _ = repositories

    assert sql_repository.opportunity_metric_records() == (
        json_repository.opportunity_metric_records()
    )
    assert sql_repository.rank_account_risk(top_n=20) == (
        json_repository.rank_account_risk(top_n=20)
    )
    assert sql_repository.rank_product_area_risk(top_n=20) == (
        json_repository.rank_product_area_risk(top_n=20)
    )


def test_all_reports_have_sql_json_parity(
    repositories: tuple[
        JsonEnterpriseBenchRepository, SqliteEnterpriseBenchRepository, Path
    ],
) -> None:
    json_repository, sql_repository, _ = repositories
    account_query = AccountRiskQuery(top_n=5, priorities=["p1"])
    product_query = ProductRiskQuery(top_n=5, priorities=["p1", "p2"])
    pipeline_query = PipelineChangeQuery(
        current_start=date(2026, 1, 1),
        current_end=date(2026, 3, 31),
        previous_start=date(2025, 10, 1),
        previous_end=date(2025, 12, 31),
        top_n=5,
        currency="USD",
    )
    overlap_query = SupportPipelineLinkQuery(
        **pipeline_query.model_dump(exclude={"top_n"}),
        top_n_decliners=5,
        priorities=["p1"],
    )

    comparisons = (
        (
            account_risk_report(json_repository, account_query),
            account_risk_report(sql_repository, account_query),
        ),
        (
            product_risk_report(json_repository, product_query),
            product_risk_report(sql_repository, product_query),
        ),
        (
            pipeline_change_report(json_repository, pipeline_query),
            pipeline_change_report(sql_repository, pipeline_query),
        ),
        (
            support_pipeline_link_report(json_repository, overlap_query),
            support_pipeline_link_report(sql_repository, overlap_query),
        ),
    )
    assert all(json_report == sql_report for json_report, sql_report in comparisons)


def test_rejects_database_with_modified_provenance(source_data: Path, tmp_path: Path) -> None:
    database = tmp_path / "maple.sqlite3"
    build_database(source_data, database, verify_source=False)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE metadata SET value = 'unknown' WHERE key = 'source_commit'"
        )

    with pytest.raises(SqliteStoreError, match="provenance"):
        validate_database(database)


def test_rejects_source_rows_with_broken_foreign_keys(
    source_data: Path, tmp_path: Path
) -> None:
    tickets = json.loads(
        (source_data / "crm_json_data" / "tickets.json").read_text(encoding="utf-8")
    )
    tickets[0]["account_id"] = "UNKNOWN"
    write_records(source_data, "crm_json_data/tickets.json", tickets)

    with pytest.raises(SqliteStoreError, match="FOREIGN KEY"):
        build_database(
            source_data,
            tmp_path / "invalid.sqlite3",
            verify_source=False,
        )
