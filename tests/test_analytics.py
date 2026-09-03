from datetime import date

import pytest

from business_ops.analytics import (
    DateRange,
    MetricRecord,
    analyze_concentration,
    calculate_variance,
    compare_baseline,
    compare_periods,
    rank_accounts,
    segment_performance,
)


def record(day: date, entity: str, segment: str, value: int) -> MetricRecord:
    return MetricRecord(
        date=day,
        entity_id=entity,
        entity_name=f"Account {entity}",
        segment=segment,
        value=value,
    )


RECORDS = [
    record(date(2025, 12, 1), "A", "East", 100),
    record(date(2025, 12, 1), "B", "West", 200),
    record(date(2026, 1, 1), "A", "East", 80),
    record(date(2026, 1, 1), "B", "West", 50),
    record(date(2026, 1, 1), "C", "East", 100),
]
PREVIOUS = DateRange(start=date(2025, 10, 1), end=date(2025, 12, 31))
CURRENT = DateRange(start=date(2026, 1, 1), end=date(2026, 3, 31))


def test_calculate_variance_handles_growth_decline_and_zero_baseline() -> None:
    assert calculate_variance(80, 100).percent_change == -20.0
    assert calculate_variance(80, 100).direction == "decrease"
    assert calculate_variance(10, 0).percent_change is None
    assert calculate_variance(0, 0).percent_change == 0.0


def test_compare_periods_identifies_decline_contributors() -> None:
    result = compare_periods(RECORDS, CURRENT, PREVIOUS)

    assert result.total.absolute_change == -70
    assert [item.entity_id for item in result.contributors] == ["B", "A", "C"]
    assert result.contributors[0].variance.absolute_change == -150


def test_rank_accounts_and_segments_are_deterministic() -> None:
    ranking = rank_accounts(RECORDS, period=CURRENT, top_n=2)
    segments = segment_performance(RECORDS, period=CURRENT)

    assert [(item.entity_id, item.value) for item in ranking] == [("C", 100), ("A", 80)]
    assert [(item.segment, item.value) for item in segments] == [("East", 180), ("West", 50)]
    assert sum(item.share_percent for item in segments) == 100.0


def test_compare_baseline_includes_new_and_missing_accounts() -> None:
    result = compare_baseline(RECORDS[2:], RECORDS[:2])

    assert result[0].entity_id == "B"
    assert result[-1].entity_id == "C"
    assert result[-1].variance.percent_change is None


def test_concentration_reports_top_share_and_hhi() -> None:
    result = analyze_concentration(RECORDS, period=CURRENT, top_n=2)

    assert result.total_value == 230
    assert result.top_n_value == 180
    assert result.top_n_share_percent == 78.26
    assert result.herfindahl_index == pytest.approx(0.357278)


def test_rejects_invalid_period_and_ranking_limit() -> None:
    with pytest.raises(ValueError):
        DateRange(start=date(2026, 2, 1), end=date(2026, 1, 1))
    with pytest.raises(ValueError, match="top_n"):
        rank_accounts(RECORDS, top_n=0)
