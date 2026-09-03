# Stage 1: understand the model boundary

Stage 0 proved the model server works. Stage 1 makes the request/response boundary
explicit in application code before an agent framework abstracts it away.

## The complete path

```text
business question
      |
      v
Python builds messages + generation controls
      |
      v
POST /v1/chat/completions
      |
      v
local model server generates a response
      |
      v
Python validates the envelope and extracts content + usage
```

The application imports neither Qwen nor MLX. Its dependency is the HTTP contract.
Changing `MODEL_ID` and `BASE_URL` can point it at another compatible server without
changing `ModelServerClient` or the command-line program.

## Request anatomy

Run:

```bash
business-ops \
  "Revenue fell 12% while customer count stayed flat. What should we investigate?" \
  --show-request
```

The important fields are:

```json
{
  "model": "mlx-community/Qwen3.8-27B-4bit",
  "messages": [
    {"role": "system", "content": "Behavior and decision rules"},
    {"role": "user", "content": "The business question"}
  ],
  "temperature": 0.0,
  "max_tokens": 512
}
```

- `system` establishes durable behavior for this request.
- `user` carries the business question.
- `temperature` influences sampling variability; `0` is useful for repeatable analysis.
- `max_tokens` is an output budget, not a target response length.

## Response anatomy

Use `--raw` to inspect the full JSON envelope. The application currently retains:

- `choices[0].message.content`: the assistant's text
- `choices[0].finish_reason`: why generation stopped
- `usage`: input, output, and total token counts
- `model`: which model served the request
- the complete raw object for diagnostics

Parsing this envelope ourselves is intentional. In later stages, frameworks will reduce
the plumbing, but the model is still receiving messages and returning a protocol object.

## Failure boundary

`ModelServerClient` translates low-level failures into one application exception:
`ModelServerError`. It distinguishes:

- server unreachable
- timeout
- HTTP error with a bounded diagnostic body
- invalid JSON
- unexpected response shape
- non-text content when text was requested

Generation controls are validated before making a network call. This prevents a caller
from sending an invalid temperature or token budget and makes failures easier to locate.

## What this does not do

This client is not an agent. It does not plan, call tools, retain state, access business
data, or guarantee factual correctness. It demonstrates the portable model boundary that
those capabilities will build upon.

## Verified milestone run

On 2026-09-03 the command was run against the qualified local Qwen3.8 baseline with both
`--show-request` and `--raw`. The request asked which evidence categories should be
investigated when revenue falls while customer count remains flat.

The response correctly proposed pricing/product mix, usage/engagement, and cohort/churn
dynamics. The raw envelope reported 65 input tokens, 160 output tokens, and a local decode
rate of 28.39 tokens/s. Its `finish_reason` was `length`, demonstrating an important API
lesson: the output token budget can truncate an otherwise useful answer, and callers must
inspect the envelope rather than assuming every response ended naturally.

An underspecified request—“Why did revenue decline?”—also produced an explicit statement
that company, period, and financial evidence were missing instead of fabricating a cause.
