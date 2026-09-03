"""Deterministic business analytics independent of models and datasets."""

from business_ops.analytics.core import (
    analyze_concentration,
    calculate_variance,
    compare_baseline,
    compare_periods,
    rank_accounts,
    segment_performance,
)
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

__all__ = [
    "ConcentrationAnalysis",
    "DateRange",
    "EntityChange",
    "MetricRecord",
    "PeriodComparison",
    "RankedMetric",
    "SegmentMetric",
    "Variance",
    "analyze_concentration",
    "calculate_variance",
    "compare_baseline",
    "compare_periods",
    "rank_accounts",
    "segment_performance",
]
