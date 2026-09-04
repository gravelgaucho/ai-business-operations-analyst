from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpportunityDimension(StrEnum):
    ACCOUNT = "account"
    REGION = "region"
    CLOSE_MONTH = "close_month"
    CLOSE_QUARTER = "close_quarter"


class OpportunityCurrency(StrEnum):
    USD = "USD"
    GBP = "GBP"


class OpportunityBreakdownQuery(QueryModel):
    start_date: date
    end_date: date
    dimensions: tuple[OpportunityDimension, ...] = Field(min_length=1, max_length=2)
    currency: OpportunityCurrency = OpportunityCurrency.USD
    top_n: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def range_and_dimensions_are_valid(self) -> OpportunityBreakdownQuery:
        if self.start_date > self.end_date:
            raise ValueError("query start_date must not be after end_date")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("query dimensions must be distinct")
        return self


class OpportunityBreakdownRow(QueryModel):
    dimensions: dict[str, str]
    closed_won_opportunity_acv: int = Field(ge=0)
