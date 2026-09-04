from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from business_ops.analytics.types import MetricRecord
from business_ops.datasets.download import ENTERPRISE_BENCH, DatasetSpec, verify_dataset
from business_ops.datasets.enterprise_bench import (
    Account,
    AccountRisk,
    EnterpriseBenchDataError,
    Opportunity,
    ProductAreaRisk,
    ProductPart,
    Ticket,
    default_data_root,
    load_records,
)
from business_ops.datasets.query_types import (
    OpportunityBreakdownQuery,
    OpportunityBreakdownRow,
    OpportunityDimension,
)

SCHEMA_VERSION = 1
APPLICATION_ID = 0x424F5053


class SqliteStoreError(RuntimeError):
    """Raised when the derived relational store is missing, invalid, or unsafe."""


class DatabaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database_path: Path
    schema_version: int
    source_commit: str
    source_sha256: str
    accounts: int
    opportunities: int
    tickets: int
    product_parts: int
    ticket_components: int
    database_bytes: int


@dataclass(frozen=True)
class CompiledSemanticQuery:
    statement: str
    parameters: tuple[str | int, ...]


def default_database_path() -> Path:
    configured = os.getenv("BUSINESS_OPS_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return default_data_root().parent / "derived" / "maple_payments.sqlite3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        PRAGMA application_id = {APPLICATION_ID};
        PRAGMA user_version = {SCHEMA_VERSION};
        PRAGMA foreign_keys = ON;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;

        CREATE TABLE accounts (
            source_order INTEGER NOT NULL UNIQUE,
            account_id TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            region TEXT NOT NULL,
            arr INTEGER NOT NULL CHECK (arr >= 0)
        ) STRICT;

        CREATE TABLE opportunities (
            source_order INTEGER NOT NULL UNIQUE,
            opportunity_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(account_id),
            stage TEXT NOT NULL,
            currency TEXT NOT NULL,
            acv INTEGER NOT NULL CHECK (acv >= 0),
            target_close_date TEXT NOT NULL CHECK (length(target_close_date) = 10)
        ) STRICT;

        CREATE TABLE product_parts (
            source_order INTEGER NOT NULL UNIQUE,
            part_id TEXT PRIMARY KEY,
            title TEXT NOT NULL
        ) STRICT;

        CREATE TABLE tickets (
            source_order INTEGER NOT NULL UNIQUE,
            ticket_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(account_id),
            priority TEXT NOT NULL,
            status TEXT NOT NULL
        ) STRICT;

        CREATE TABLE ticket_components (
            ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
            part_id TEXT NOT NULL REFERENCES product_parts(part_id),
            component_order INTEGER NOT NULL,
            PRIMARY KEY (ticket_id, part_id)
        ) STRICT;

        CREATE INDEX idx_opportunities_stage_currency_date
            ON opportunities(stage, currency, target_close_date);
        CREATE INDEX idx_opportunities_account
            ON opportunities(account_id);
        CREATE INDEX idx_tickets_priority_status_account
            ON tickets(priority, status, account_id);
        CREATE INDEX idx_ticket_components_part
            ON ticket_components(part_id, ticket_id);
        """
    )


def _metadata(spec: DatasetSpec, source_root: Path) -> dict[str, str]:
    marker = source_root / ".source.json"
    return {
        "dataset_name": spec.name,
        "source_commit": spec.source_commit,
        "source_sha256": spec.sha256,
        "license": spec.license,
        "synthetic": json.dumps(spec.synthetic),
        "schema_version": str(SCHEMA_VERSION),
        "source_marker_sha256": _sha256(marker) if marker.is_file() else "unverified-test-source",
    }


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise SqliteStoreError(f"Invalid opportunity target date: {value}") from exc


def _populate(connection: sqlite3.Connection, source_root: Path, spec: DatasetSpec) -> None:
    accounts = load_records(source_root, "crm_json_data/accounts.json", Account)
    opportunities = load_records(
        source_root, "crm_json_data/opportunities.json", Opportunity
    )
    tickets = load_records(source_root, "crm_json_data/tickets.json", Ticket)
    parts = load_records(source_root, "pm_json_data/maple_parts.json", ProductPart)

    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        _metadata(spec, source_root).items(),
    )
    connection.executemany(
        """
        INSERT INTO accounts(source_order, account_id, account_name, region, arr)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (index, item.account_id, item.account_name, item.region, item.arr)
            for index, item in enumerate(accounts)
        ),
    )
    connection.executemany(
        """
        INSERT INTO opportunities(
            source_order, opportunity_id, account_id, stage, currency, acv, target_close_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                index,
                item.opportunity_id or f"SOURCE-{index:08d}",
                item.account_id,
                item.stage,
                item.currency,
                item.acv,
                _iso_date(item.target_close_date),
            )
            for index, item in enumerate(opportunities)
        ),
    )
    connection.executemany(
        "INSERT INTO product_parts(source_order, part_id, title) VALUES (?, ?, ?)",
        ((index, item.part_id, item.title) for index, item in enumerate(parts)),
    )
    connection.executemany(
        """
        INSERT INTO tickets(source_order, ticket_id, account_id, priority, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (index, item.ticket_id, item.account_id, item.priority, item.status)
            for index, item in enumerate(tickets)
        ),
    )
    connection.executemany(
        """
        INSERT INTO ticket_components(ticket_id, part_id, component_order)
        VALUES (?, ?, ?)
        """,
        (
            (ticket.ticket_id, component, component_order)
            for ticket in tickets
            for component_order, component in enumerate(ticket.components)
        ),
    )


def build_database(
    source_root: Path,
    database_path: Path,
    *,
    spec: DatasetSpec = ENTERPRISE_BENCH,
    verify_source: bool = True,
    force: bool = False,
) -> DatabaseSummary:
    """Build the relational store atomically from an approved source snapshot."""

    source_root = source_root.resolve()
    database_path = database_path.resolve()
    if verify_source:
        verify_dataset(source_root, spec=spec)
    if database_path.exists() and not force:
        return validate_database(
            database_path,
            spec=spec,
            source_root=source_root if verify_source else None,
        )

    database_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.stem}-", suffix=".sqlite3", dir=database_path.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with sqlite3.connect(temporary_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _schema(connection)
            _populate(connection, source_root, spec)
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise SqliteStoreError(
                    f"Relational import failed foreign-key checks: {foreign_key_errors[:3]}"
                )
            connection.execute("PRAGMA optimize")
        os.replace(temporary_path, database_path)
    except (OSError, sqlite3.Error, EnterpriseBenchDataError, SqliteStoreError) as exc:
        if isinstance(exc, SqliteStoreError):
            raise
        raise SqliteStoreError(f"Could not build the relational store: {exc}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)
    return validate_database(
        database_path,
        spec=spec,
        source_root=source_root if verify_source else None,
    )


def _read_only_connection(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise SqliteStoreError(
            f"Relational store is missing at {database_path}. Run 'make database'."
        )
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def validate_database(
    database_path: Path,
    *,
    spec: DatasetSpec = ENTERPRISE_BENCH,
    source_root: Path | None = None,
) -> DatabaseSummary:
    """Validate schema identity, source provenance, integrity, and table counts."""

    database_path = database_path.resolve()
    try:
        with _read_only_connection(database_path) as connection:
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id != APPLICATION_ID or schema_version != SCHEMA_VERSION:
                raise SqliteStoreError("Relational store schema identity does not match this app.")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise SqliteStoreError(f"Relational store integrity check failed: {integrity}")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise SqliteStoreError("Relational store contains broken foreign keys.")
            metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
            expected = {
                "dataset_name": spec.name,
                "source_commit": spec.source_commit,
                "source_sha256": spec.sha256,
                "license": spec.license,
                "synthetic": json.dumps(spec.synthetic),
                "schema_version": str(SCHEMA_VERSION),
            }
            if any(metadata.get(key) != value for key, value in expected.items()):
                raise SqliteStoreError(
                    "Relational store provenance does not match the approved source."
                )
            if source_root is not None:
                verified_root = verify_dataset(source_root, spec=spec)
                marker_digest = _sha256(verified_root / ".source.json")
                if metadata.get("source_marker_sha256") != marker_digest:
                    raise SqliteStoreError(
                        "Relational store does not match the verified local source marker."
                    )
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "accounts",
                    "opportunities",
                    "tickets",
                    "product_parts",
                    "ticket_components",
                )
            }
    except sqlite3.Error as exc:
        raise SqliteStoreError(f"Could not validate the relational store: {exc}") from exc
    return DatabaseSummary(
        database_path=database_path,
        schema_version=schema_version,
        source_commit=metadata["source_commit"],
        source_sha256=metadata["source_sha256"],
        accounts=counts["accounts"],
        opportunities=counts["opportunities"],
        tickets=counts["tickets"],
        product_parts=counts["product_parts"],
        ticket_components=counts["ticket_components"],
        database_bytes=database_path.stat().st_size,
    )


def _placeholders(values: frozenset[str]) -> str:
    return ", ".join("?" for _ in values)


_OPPORTUNITY_DIMENSION_SQL = {
    OpportunityDimension.ACCOUNT: "a.account_name || ' (' || a.account_id || ')'",
    OpportunityDimension.REGION: "a.region",
    OpportunityDimension.CLOSE_MONTH: "substr(o.target_close_date, 1, 7)",
    OpportunityDimension.CLOSE_QUARTER: (
        "substr(o.target_close_date, 1, 4) || '-Q' || "
        "(((CAST(substr(o.target_close_date, 6, 2) AS INTEGER) - 1) / 3) + 1)"
    ),
}


def compile_closed_won_opportunity_acv_query(
    query: OpportunityBreakdownQuery,
) -> CompiledSemanticQuery:
    """Compile a typed semantic request without accepting SQL identifiers or fragments."""

    selections = [
        f"{_OPPORTUNITY_DIMENSION_SQL[dimension]} AS {dimension.value}"
        for dimension in query.dimensions
    ]
    groupings = [_OPPORTUNITY_DIMENSION_SQL[dimension] for dimension in query.dimensions]
    order_dimensions = [dimension.value for dimension in query.dimensions]
    statement = f"""
        SELECT {", ".join(selections)}, SUM(o.acv) AS closed_won_opportunity_acv
        FROM opportunities AS o
        JOIN accounts AS a ON a.account_id = o.account_id
        WHERE o.stage = ?
          AND o.currency = ?
          AND o.target_close_date BETWEEN ? AND ?
        GROUP BY {", ".join(groupings)}
        ORDER BY closed_won_opportunity_acv DESC, {", ".join(order_dimensions)} ASC
        LIMIT ?
    """.strip()
    return CompiledSemanticQuery(
        statement=statement,
        parameters=(
            "closed_won",
            query.currency.value,
            query.start_date.isoformat(),
            query.end_date.isoformat(),
            query.top_n,
        ),
    )


class SqliteEnterpriseBenchRepository:
    """Read-only repository backed by the verified derived SQLite store."""

    def __init__(
        self,
        database_path: Path,
        *,
        source_root: Path | None = None,
        validate: bool = True,
    ) -> None:
        self.database_path = database_path.resolve()
        if validate:
            validate_database(self.database_path, source_root=source_root)

    def opportunity_metric_records(
        self, *, stage: str = "closed_won", currency: str = "USD"
    ) -> list[MetricRecord]:
        with _read_only_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT o.target_close_date, a.account_id, a.account_name, a.region, o.acv
                FROM opportunities AS o
                JOIN accounts AS a ON a.account_id = o.account_id
                WHERE o.stage = ? AND o.currency = ?
                ORDER BY o.source_order
                """,
                (stage, currency),
            ).fetchall()
        return [
            MetricRecord(
                date=date.fromisoformat(row["target_close_date"]),
                entity_id=row["account_id"],
                entity_name=row["account_name"],
                segment=row["region"],
                value=row["acv"],
            )
            for row in rows
        ]

    def rank_account_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 5,
    ) -> list[AccountRisk]:
        if top_n < 1:
            raise ValueError("top_n must be positive")
        if not priorities or not open_statuses:
            return []
        parameters = (*sorted(priorities), *sorted(open_statuses), top_n)
        with _read_only_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT a.account_id, a.account_name, a.region, a.arr, COUNT(*) AS ticket_count
                FROM tickets AS t
                JOIN accounts AS a ON a.account_id = t.account_id
                WHERE t.priority IN ({_placeholders(priorities)})
                  AND t.status IN ({_placeholders(open_statuses)})
                GROUP BY a.account_id, a.account_name, a.region, a.arr
                ORDER BY a.arr DESC, ticket_count DESC, a.account_name ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            AccountRisk(
                rank=index,
                account_id=row["account_id"],
                account_name=row["account_name"],
                region=row["region"],
                arr_at_risk=row["arr"],
                open_ticket_count=row["ticket_count"],
            )
            for index, row in enumerate(rows, start=1)
        ]

    def rank_product_area_risk(
        self,
        *,
        priorities: frozenset[str] = frozenset({"p0", "p1"}),
        open_statuses: frozenset[str] = frozenset({"open", "in_progress"}),
        top_n: int = 10,
    ) -> list[ProductAreaRisk]:
        if top_n < 1:
            raise ValueError("top_n must be positive")
        if not priorities or not open_statuses:
            return []
        filter_parameters = (*sorted(priorities), *sorted(open_statuses))
        parameters = (*filter_parameters, *filter_parameters, top_n)
        with _read_only_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                WITH affected_accounts AS (
                    SELECT DISTINCT tc.part_id, t.account_id
                    FROM tickets AS t
                    JOIN ticket_components AS tc ON tc.ticket_id = t.ticket_id
                    WHERE t.priority IN ({_placeholders(priorities)})
                      AND t.status IN ({_placeholders(open_statuses)})
                ),
                exposure AS (
                    SELECT aa.part_id, SUM(a.arr) AS arr_at_risk,
                           COUNT(*) AS accounts_at_risk
                    FROM affected_accounts AS aa
                    JOIN accounts AS a ON a.account_id = aa.account_id
                    GROUP BY aa.part_id
                ),
                ticket_counts AS (
                    SELECT tc.part_id, COUNT(*) AS open_ticket_count
                    FROM tickets AS t
                    JOIN ticket_components AS tc ON tc.ticket_id = t.ticket_id
                    WHERE t.priority IN ({_placeholders(priorities)})
                      AND t.status IN ({_placeholders(open_statuses)})
                    GROUP BY tc.part_id
                )
                SELECT p.part_id, p.title, e.arr_at_risk, e.accounts_at_risk,
                       c.open_ticket_count
                FROM exposure AS e
                JOIN ticket_counts AS c ON c.part_id = e.part_id
                JOIN product_parts AS p ON p.part_id = e.part_id
                ORDER BY e.arr_at_risk DESC, e.accounts_at_risk DESC, p.title ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [
            ProductAreaRisk(
                rank=index,
                component_id=row["part_id"],
                component_name=row["title"],
                arr_at_risk=row["arr_at_risk"],
                accounts_at_risk=row["accounts_at_risk"],
                open_ticket_count=row["open_ticket_count"],
            )
            for index, row in enumerate(rows, start=1)
        ]

    def query_closed_won_opportunity_acv(
        self, query: OpportunityBreakdownQuery
    ) -> list[OpportunityBreakdownRow]:
        compiled = compile_closed_won_opportunity_acv_query(query)
        with _read_only_connection(self.database_path) as connection:
            rows = connection.execute(compiled.statement, compiled.parameters).fetchall()
        return [
            OpportunityBreakdownRow(
                dimensions={
                    dimension.value: str(row[dimension.value])
                    for dimension in query.dimensions
                },
                closed_won_opportunity_acv=row["closed_won_opportunity_acv"],
            )
            for row in rows
        ]
