from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DateRange(AnalyticsModel):
    start: date
    end: date

    @model_validator(mode="after")
    def dates_are_ordered(self) -> DateRange:
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        return self

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end


class MetricRecord(AnalyticsModel):
    date: date
    entity_id: str = Field(min_length=1)
    entity_name: str = Field(min_length=1)
    segment: str = Field(min_length=1)
    value: int = Field(ge=0)


class Variance(AnalyticsModel):
    baseline: int
    current: int
    absolute_change: int
    percent_change: float | None
    direction: Literal["increase", "decrease", "flat"]


class RankedMetric(AnalyticsModel):
    rank: int = Field(ge=1)
    entity_id: str
    entity_name: str
    segment: str
    value: int


class SegmentMetric(AnalyticsModel):
    segment: str
    value: int
    share_percent: float


class EntityChange(AnalyticsModel):
    entity_id: str
    entity_name: str
    segment: str
    variance: Variance


class PeriodComparison(AnalyticsModel):
    current_period: DateRange
    previous_period: DateRange
    total: Variance
    contributors: list[EntityChange]


class ConcentrationAnalysis(AnalyticsModel):
    total_value: int
    top_n: int
    top_n_value: int
    top_n_share_percent: float
    herfindahl_index: float
    leaders: list[RankedMetric]
