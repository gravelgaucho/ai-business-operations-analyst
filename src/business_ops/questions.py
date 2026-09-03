from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class QuestionType(StrEnum):
    """Business intent expressed by a question."""

    DESCRIPTIVE = "descriptive"
    CAUSAL = "causal"
    COMPARATIVE = "comparative"
    PREDICTIVE = "predictive"
    PRESCRIPTIVE = "prescriptive"
    LOOKUP = "lookup"
    AMBIGUOUS = "ambiguous"


class BusinessQuestion(BaseModel):
    """Validated interpretation of a natural-language business question."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_type: QuestionType = Field(
        description="The analytical intent of the question."
    )
    scope: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Concise snake_case business area, such as regional_sales.",
    )
    metric: str | None = Field(
        description="Primary business metric explicitly named or clearly implied."
    )
    time_period: str | None = Field(
        description="Time period stated by the user, without inventing dates."
    )
    entities: list[str] = Field(
        description="Named regions, segments, products, teams, accounts, or other entities."
    )
    requires_investigation: bool = Field(
        description="Whether answering requires business evidence beyond the question text."
    )
    missing_information: list[str] = Field(
        description="Specific inputs needed before the question can be answered responsibly."
    )
    normalized_question: str = Field(
        min_length=1,
        description="A concise restatement that preserves the user's intent.",
    )
