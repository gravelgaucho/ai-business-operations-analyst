# Stage 0 architecture

## Decision

The application boundary is the OpenAI-compatible Chat Completions HTTP contract.
The model runtime sits behind that boundary and can be changed through environment
configuration.

```text
Python client / qualification client
        |
        | OpenAI-compatible JSON over localhost
        v
MLX-VLM server -> MLX-LM generation utilities -> MLX -> Apple unified memory
        |
        v
Qwen3.8-27B 4-bit weights (replaceable)
```

Qwen3.8 is a vision-language model, so MLX-VLM supplies the correct loader and server.
It builds on the same MLX and MLX-LM stack; Stages 0–1 exercise text only. The clients
have no MLX or Qwen imports and only know a model identifier plus a base URL.

Stage 1 formalizes this boundary in `business_ops.client.ModelServerClient`. It exposes
small application types while preserving the complete raw response for learning and
diagnostics. Transport-specific exceptions do not leak past this module.

## Why this baseline

`Qwen3.8-27B` is the current dense 27B model in the requested Qwen3.8 class. The MLX
community conversion is Apache-2.0 licensed, approximately 16.1 GB at 4-bit precision,
and fits comfortably in the test Mac's 128 GB unified memory. A dense model also makes
this first performance result straightforward to interpret.

The selection is a baseline, not a permanent dependency. Future candidates must pass
the same external qualification contract before replacement.

## Deliberate non-goals

- No Pydantic AI or other agent framework
- No MCP protocol or external tools
- No retrieval, embeddings, vector store, or RAG
- No business dataset
- No UI
- No production serving claims
- No vision qualification yet

The `lookup_account_metrics` function used in qualification is a deterministic fixture.
It proves protocol behavior; it is not a data integration.

## Acceptance policy

A model qualifies only when all five automated checks pass in one run: server discovery,
basic inference, schema-constrained JSON, native tool-call emission, and continuation
after a tool result. The run must also record per-check latency, token usage when exposed,
package versions, and sampled peak server RSS.
