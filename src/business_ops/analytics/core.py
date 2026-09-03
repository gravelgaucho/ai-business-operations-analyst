from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from business_ops.analytics.types import (
    ConcentrationAnalysis,
    DateRange,
    EntityChange,
    MetricRecord,
    PeriodComparison,
    RankedMetric,
    SegmentMetric,
    Variance,
)


def calculate_variance(current: int, baseline: int) -> Variance:
    """Calculate absolute and percentage change without inventing a zero baseline rate."""

    change = current - baseline
    direction = "increase" if change > 0 else "decrease" if change < 0 else "flat"
    percent_change = None if baseline == 0 and current != 0 else 0.0
    if baseline != 0:
        percent_change = round(change / baseline * 100, 2)
    return Variance(
        baseline=baseline,
        current=current,
        absolute_change=change,
        percent_change=percent_change,
        direction=direction,
    )


def _in_period(records: Iterable[MetricRecord], period: DateRange | None) -> list[MetricRecord]:
    return [record for record in records if period is None or period.contains(record.date)]


def _entity_totals(
    records: Iterable[MetricRecord],
) -> tuple[dict[str, int], dict[str, tuple[str, str]]]:
    totals: dict[str, int] = defaultdict(int)
    labels: dict[str, tuple[str, str]] = {}
    for record in records:
        totals[record.entity_id] += record.value
        labels[record.entity_id] = (record.entity_name, record.segment)
    return dict(totals), labels


def rank_accounts(
    records: Iterable[MetricRecord],
    *,
    period: DateRange | None = None,
    top_n: int = 5,
) -> list[RankedMetric]:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    totals, labels = _entity_totals(_in_period(records, period))
    ordered = sorted(totals.items(), key=lambda item: (-item[1], labels[item[0]][0]))[:top_n]
    return [
        RankedMetric(
            rank=index,
            entity_id=entity_id,
            entity_name=labels[entity_id][0],
            segment=labels[entity_id][1],
            value=value,
        )
        for index, (entity_id, value) in enumerate(ordered, start=1)
    ]


def segment_performance(
    records: Iterable[MetricRecord], *, period: DateRange | None = None
) -> list[SegmentMetric]:
    totals: dict[str, int] = defaultdict(int)
    for record in _in_period(records, period):
        totals[record.segment] += record.value
    grand_total = sum(totals.values())
    return [
        SegmentMetric(
            segment=segment,
            value=value,
            share_percent=round(value / grand_total * 100, 2) if grand_total else 0.0,
        )
        for segment, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def compare_baseline(
    current_records: Iterable[MetricRecord], baseline_records: Iterable[MetricRecord]
) -> list[EntityChange]:
    current, current_labels = _entity_totals(current_records)
    baseline, baseline_labels = _entity_totals(baseline_records)
    labels = baseline_labels | current_labels
    changes = [
        EntityChange(
            entity_id=entity_id,
            entity_name=labels[entity_id][0],
            segment=labels[entity_id][1],
            variance=calculate_variance(current.get(entity_id, 0), baseline.get(entity_id, 0)),
        )
        for entity_id in current.keys() | baseline.keys()
    ]
    return sorted(
        changes,
        key=lambda result: (result.variance.absolute_change, result.entity_name),
    )


def compare_periods(
    records: Sequence[MetricRecord], current: DateRange, previous: DateRange
) -> PeriodComparison:
    current_records = _in_period(records, current)
    previous_records = _in_period(records, previous)
    return PeriodComparison(
        current_period=current,
        previous_period=previous,
        total=calculate_variance(
            sum(record.value for record in current_records),
            sum(record.value for record in previous_records),
        ),
        contributors=compare_baseline(current_records, previous_records),
    )


def analyze_concentration(
    records: Sequence[MetricRecord],
    *,
    period: DateRange | None = None,
    top_n: int = 5,
) -> ConcentrationAnalysis:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    filtered = _in_period(records, period)
    totals, _ = _entity_totals(filtered)
    total_value = sum(totals.values())
    leaders = rank_accounts(filtered, top_n=top_n)
    top_n_value = sum(item.value for item in leaders)
    shares = [value / total_value for value in totals.values()] if total_value else []
    return ConcentrationAnalysis(
        total_value=total_value,
        top_n=top_n,
        top_n_value=top_n_value,
        top_n_share_percent=round(top_n_value / total_value * 100, 2) if total_value else 0.0,
        herfindahl_index=round(sum(share**2 for share in shares), 6),
        leaders=leaders,
    )
