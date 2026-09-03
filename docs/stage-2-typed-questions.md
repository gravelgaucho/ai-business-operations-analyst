# Stage 2: typed business questions

Stage 1 returned model text. Stage 2 creates the first stable business object in the
application: `BusinessQuestion`. The model proposes the values, but Pydantic decides
whether the result is valid.

## From language to a contract

```text
"Why did Northeast revenue decline last quarter?"
                    |
                    v
        native JSON Schema request
                    |
                    v
          local model generation
                    |
                    v
       Pydantic validation and parsing
                    |
                    v
           BusinessQuestion object
```

The contract records:

- analytical intent: descriptive, causal, comparative, predictive, prescriptive,
  lookup, or ambiguous
- a snake_case business scope
- metric and time period when stated
- named business entities
- whether evidence must be investigated
- information missing from the question
- a concise normalized question

Extra fields, unsupported question types, invalid scopes, and missing required fields are
rejected. The application never silently treats a malformed model response as valid data.

## Framework boundary

`create_question_classifier` accepts any Pydantic AI model object. The default
`build_question_classifier` constructs an `OpenAIChatModel` pointed at `BASE_URL` and
`MODEL_ID`. Qwen and MLX remain runtime configuration rather than imports in business
logic.

The classifier uses Pydantic AI's native structured-output mode, which sends the generated
JSON Schema to the compatible server. If returned JSON does not validate, Pydantic AI adds
the validation errors to a retry request. Two repair attempts are allowed. Exhaustion is
translated into the stable application exception `QuestionClassificationError`.

The test suite disables real model requests and uses a deterministic fake model. It proves
both a malformed-then-correct response and permanent failure, so retry behavior is tested
without loading model weights.

## Verified local run

On 2026-09-03, Pydantic 2.13.5 and Pydantic AI 2.38.0 were run against the qualified
`mlx-community/Qwen3.8-27B-4bit` server. This command completed in one model request:

```bash
business-ops-classify "Why did Northeast revenue decline last quarter?"
```

The validated result classified the question as causal, identified revenue as the metric,
preserved “last quarter” and “Northeast,” required investigation, and listed the evidence
missing from the prompt. A second verified example used 118 input tokens and 157 output
tokens and also validated on its first request.

## Deliberate limits

Classification is not analysis. Stage 2 does not query data, test a hypothesis, call a
tool, remember a conversation, or recommend an action. Those capabilities will build on
this type rather than being mixed into it.

References: [Pydantic AI OpenAI-compatible models](https://pydantic.dev/docs/ai/models/openai/),
[Pydantic AI output modes](https://pydantic.dev/docs/ai/core-concepts/output/), and
[Pydantic AI testing](https://pydantic.dev/docs/ai/guides/testing/).
