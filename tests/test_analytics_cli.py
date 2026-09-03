from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_ops.analytics_cli import main


def write_records(root: Path, relative_path: str, records: list[dict[str, object]]) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def test_account_risk_command_returns_reproducible_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_records(
        tmp_path,
        "crm_json_data/accounts.json",
        [{"account_id": "A", "account_name": "Alpha", "region": "East", "arr": 1000}],
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
            }
        ],
    )

    assert main(["--data-root", str(tmp_path), "account-risk"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["source"]["synthetic"] is True
    assert output["summary"] == {"affected_accounts": 1, "total_arr_at_risk": 1000}
    assert output["results"][0]["account_name"] == "Alpha"
