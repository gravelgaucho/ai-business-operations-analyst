from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from business_ops.classifier import (
    QuestionClassificationError,
    classify_question,
    create_question_classifier,
)
from business_ops.questions import BusinessQuestion, QuestionType

VALID_OUTPUT = {
    "question_type": "causal",
    "scope": "regional_sales",
    "metric": "revenue",
    "time_period": "last quarter",
    "entities": ["Northeast"],
    "requires_investigation": True,
    "missing_information": ["Revenue by account", "Customer and operational drivers"],
    "normalized_question": "Why did Northeast revenue decline last quarter?",
}


def response(payload: dict[str, object]) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=json.dumps(payload))])


def test_business_question_validates_expected_contract() -> None:
    question = BusinessQuestion.model_validate(VALID_OUTPUT)

    assert question.question_type is QuestionType.CAUSAL
    assert question.scope == "regional_sales"
    assert question.requires_investigation is True


@pytest.mark.parametrize(
    "change",
    [
        {"question_type": "opinion"},
        {"scope": "Regional Sales"},
        {"surprise": "extra field"},
    ],
)
def test_business_question_rejects_invalid_contract(change: dict[str, object]) -> None:
    payload = VALID_OUTPUT | change

    with pytest.raises(ValidationError):
        BusinessQuestion.model_validate(payload)


def test_classifier_returns_a_typed_result_without_a_real_model() -> None:
    def classify(_messages: object, _info: AgentInfo) -> ModelResponse:
        return response(VALID_OUTPUT)

    agent = create_question_classifier(FunctionModel(classify))
    result = classify_question("Why did Northeast revenue decline?", agent=agent)

    assert isinstance(result, BusinessQuestion)
    assert result.metric == "revenue"


def test_invalid_model_output_is_retried_and_then_validated() -> None:
    calls = 0

    def classify(_messages: object, _info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response({"question_type": "causal", "scope": "regional_sales"})
        return response(VALID_OUTPUT)

    agent = create_question_classifier(FunctionModel(classify), output_retries=1)
    result = classify_question("Why did revenue decline?", agent=agent)

    assert calls == 2
    assert result.question_type is QuestionType.CAUSAL


def test_retry_exhaustion_becomes_an_application_error() -> None:
    def classify(_messages: object, _info: AgentInfo) -> ModelResponse:
        return response({"not": "the schema"})

    agent = create_question_classifier(FunctionModel(classify), output_retries=1)

    with pytest.raises(QuestionClassificationError, match="classification failed"):
        classify_question("Why did revenue decline?", agent=agent)


def test_empty_question_fails_before_calling_the_model() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        classify_question("  ")
