# Architecture through Stage 3

## Decision

The application boundary is the OpenAI-compatible Chat Completions HTTP contract.
The model runtime sits behind that boundary and can be changed through environment
configuration.

```text
                         CLI / future application
                                   |
                 +-----------------+-----------------+
                 |                                   |
                 v                                   v
       typed-question path                  deterministic path
                 |                                   |
        Pydantic AI adapter                  analytics functions
                 |                                   |
        OpenAI-compatible API              Maple Payments adapter
                 |                                   |
        local model server                 verified local JSON data
                 |
     Qwen3.8 weights (replaceable)
```

Qwen3.8 is a vision-language model, so MLX-VLM supplies the correct loader and server.
It builds on the same MLX and MLX-LM stack; Stages 0–2 exercise text only. The application
has no MLX or Qwen imports and only knows a model identifier plus a base URL.

Stage 1 formalizes this boundary in `business_ops.client.ModelServerClient`. It exposes
small application types while preserving the complete raw response for learning and
diagnostics. Transport-specific exceptions do not leak past this module.

Stage 2 adds a second adapter in `business_ops.classifier`. Pydantic AI translates the
`BusinessQuestion` schema into the provider's native structured-output request and parses
the response back into that application type. The classifier accepts any Pydantic AI
model implementation; the default builder supplies an OpenAI-compatible localhost model.

Stage 3 creates a separate deterministic path. Generic analytics operate on normalized
`MetricRecord` objects; the Enterprise-Bench adapter owns the source-specific field names
and joins. This keeps business calculations reusable when another approved public dataset
is introduced. The LLM cannot call these functions yet.

## Why this baseline

`Qwen3.8-27B` is the current dense 27B model in the requested Qwen3.8 class. The MLX
community conversion is Apache-2.0 licensed, approximately 16.1 GB at 4-bit precision,
and fits comfortably in the test Mac's 128 GB unified memory. A dense model also makes
this first performance result straightforward to interpret.

The selection is a baseline, not a permanent dependency. Future candidates must pass
the same external qualification contract before replacement.

## Deliberate non-goals

- No MCP protocol or external tools
- No retrieval, embeddings, vector store, or RAG
- No private or proprietary business dataset
- No UI
- No production serving claims
- No vision qualification yet

Pydantic AI is currently used only for one typed classification request. No tools are
registered and no autonomous loop is present.

The Maple Payments corpus is downloaded locally and ignored by Git. Its importer pins the
official upstream commit and archive checksum and rejects unapproved archive contents.

The `lookup_account_metrics` function used in qualification is a deterministic fixture.
It proves protocol behavior; it is not a data integration.

## Acceptance policy

A model qualifies only when all five automated checks pass in one run: server discovery,
basic inference, schema-constrained JSON, native tool-call emission, and continuation
after a tool result. The run must also record per-check latency, token usage when exposed,
package versions, and sampled peak server RSS.
