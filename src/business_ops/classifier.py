from __future__ import annotations

import asyncio

from openai import AsyncOpenAI
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from business_ops.config import Settings
from business_ops.questions import BusinessQuestion

CLASSIFIER_INSTRUCTIONS = """
Classify the user's business question; do not answer it.

Use only details stated or clearly implied by the question. Never invent company names,
dates, metrics, entities, or causes. Use null for an unstated metric or time period and an
empty list when no entities are named. Scope must be a concise snake_case business area.
List concrete missing information that would be needed to answer responsibly.

Set requires_investigation to true whenever an answer depends on inspecting business data
or other evidence. Questions about actual performance, comparisons, causes, forecasts, or
recommended actions normally require investigation even when the wording is specific.
""".strip()


class QuestionClassificationError(RuntimeError):
    """Stable application error for failed typed classification."""


def create_question_classifier(
    model: Model,
    *,
    output_retries: int = 2,
) -> Agent[None, BusinessQuestion]:
    """Create the typed agent independently of any particular model provider."""

    if output_retries < 0:
        raise ValueError("output_retries cannot be negative.")
    return Agent(
        model,
        output_type=NativeOutput(
            BusinessQuestion,
            name="business_question",
            description="A validated interpretation of the user's business question.",
            strict=True,
        ),
        instructions=CLASSIFIER_INSTRUCTIONS,
        model_settings={"temperature": 0.0, "max_tokens": 512},
        retries={"output": output_retries},
    )


def build_question_classifier(
    settings: Settings | None = None,
    *,
    output_retries: int = 2,
) -> Agent[None, BusinessQuestion]:
    """Build a classifier for an OpenAI-compatible model endpoint."""

    runtime = settings or Settings.from_environment()
    openai_client = AsyncOpenAI(
        api_key="local-not-required",
        base_url=runtime.base_url,
        timeout=runtime.timeout_seconds,
    )
    model = OpenAIChatModel(
        runtime.model_id,
        provider=OpenAIProvider(openai_client=openai_client),
    )
    return create_question_classifier(model, output_retries=output_retries)


def classify_question(
    question: str,
    *,
    agent: Agent[None, BusinessQuestion] | None = None,
    settings: Settings | None = None,
) -> BusinessQuestion:
    """Convert a natural-language question into the validated application type."""

    question = question.strip()
    if not question:
        raise ValueError("question cannot be empty.")

    classifier = agent or build_question_classifier(settings)
    try:
        with asyncio.Runner() as runner:
            return runner.run(classifier.run(question)).output
    except (AgentRunError, UserError) as exc:
        raise QuestionClassificationError(f"Question classification failed: {exc}") from exc
