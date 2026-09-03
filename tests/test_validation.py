from stage0.validation import validate_finding


def test_valid_finding() -> None:
    assert validate_finding({
        "finding": "Revenue declined",
        "metric": "revenue_change_percent",
        "value": -12.5,
        "confidence": "high",
    }) == []


def test_rejects_missing_extra_and_wrong_types() -> None:
    errors = validate_finding({"finding": 12, "metric": "revenue", "extra": True})
    assert any("missing keys" in error for error in errors)
    assert any("unexpected keys" in error for error in errors)
    assert "finding is not a string" in errors

