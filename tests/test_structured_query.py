from __future__ import annotations

import pytest
from pydantic import ValidationError

from business_ops.datasets.query_types import OpportunityBreakdownQuery


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dimensions", ["region; DROP TABLE accounts;--"]),
        ("currency", "USD' OR 1=1 --"),
        ("top_n", 51),
    ],
)
def test_governed_query_rejects_unapproved_identifiers_and_bounds(
    field: str, value: object
) -> None:
    payload = {
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "dimensions": ["region"],
        "currency": "USD",
        "top_n": 10,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        OpportunityBreakdownQuery.model_validate(payload)


def test_governed_query_rejects_reversed_period_and_duplicate_dimensions() -> None:
    with pytest.raises(ValidationError, match="start_date"):
        OpportunityBreakdownQuery(
            start_date="2026-04-01",
            end_date="2026-03-31",
            dimensions=["region"],
        )

    with pytest.raises(ValidationError, match="distinct"):
        OpportunityBreakdownQuery(
            start_date="2026-01-01",
            end_date="2026-03-31",
            dimensions=["region", "region"],
        )
