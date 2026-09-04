# Architecture through Stage 7

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
       typed-question path                investigation path
                 |                                   |
        Pydantic AI adapter          plan -> select -> observe -> stop
                 |                                   |
        OpenAI-compatible API        bounded read-only report catalog
                 |                                   |
        local model server                analytics functions
                 |                                   |
     Qwen3.8 weights (replaceable)      data repository protocol
                                                     |
                                      +--------------+--------------+
                                      |                             |
                                 JSON reference               SQLite read-only
                                      |                             |
                                      +------ verified source ------+
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
is introduced.

Stage 4 adds a narrow tool adapter around typed reports. The local model may select a tool
and validated inputs, but it cannot change calculation logic, issue arbitrary queries, or
access files directly. Each run verifies the pinned dataset before model work, enforces
request and tool-call limits, and returns an audit trace. Provider construction remains at
the application edge; the tool functions and analytics do not import MLX or Qwen.

Stage 5 adds an explicit controller in `business_ops.investigation`. The model proposes a
typed plan and chooses the next analysis from the plan after seeing prior observations.
Python validates that choice, executes the deterministic report, records both the decision
and observation, and evaluates a fixed evidence gate. Synthesis begins only after at least
two distinct analyses complete and, when planned, the cross-system overlap test has run.

This separation is deliberate. Qualification showed that the local baseline could emit a
valid conclusion before completing enough native tool calls and would not reliably resume
tool use after an output retry. Moving the loop into the application preserves model-selected
analysis while making progress, stopping, and audit state deterministic. A separate semantic
gate rejects citations to unexecuted analyses, unsupported statistical claims, and decisive
causal conclusions when timing and history evidence is absent.

Stage 6 inserts a model-neutral repository protocol beneath the reports. The original JSON
adapter remains the reference implementation. A separate builder authenticates the pinned
source, imports five normalized SQLite tables atomically, enforces foreign keys and checks,
and records source provenance inside the database. Runtime SQL connections use read-only and
query-only modes. Reports and agent tools receive the repository interface rather than SQL,
so storage can change without changing prompts, schemas, or investigation control.

Stage 7 adds a model-neutral evaluator after the investigation boundary. Versioned scenarios
declare accepted question types, required analyses, exact deterministic evidence anchors,
and execution budgets. The evaluator scores the completed typed state, so it can compare
models and controller versions without importing MLX, Qwen, provider, or data-storage
internals. The small public suite proves this contract; a larger product evaluation library
can remain private.

Two deterministic input guards sit inside the controller. Explicit causal, predictive,
prescriptive, or comparative wording takes precedence over a contradictory model label, and
the correction is recorded in `InvestigationState`. When a question names exactly two
calendar quarters, ordinary date logic supplies their non-overlapping start and end dates to
pipeline reports. The model still chooses the analysis and explains its rationale; it cannot
silently reinterpret explicit periods.

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
- No proprietary scenario library or product-specific scoring logic

The application owns the bounded investigation loop. There is typed planning state, but no
long-lived memory, delegation, self-modifying plan, or open-ended autonomy.

The Maple Payments corpus is downloaded locally and ignored by Git. Its importer pins the
official upstream commit and archive checksum and rejects unapproved archive contents.
The derived SQLite database is also ignored by Git and can be rebuilt from that authenticated
snapshot. It is not a new source of truth.

The `lookup_account_metrics` function used in qualification is a deterministic fixture.
It proves protocol behavior; it is not a data integration.

## Acceptance policy

A model qualifies only when all five automated checks pass in one run: server discovery,
basic inference, schema-constrained JSON, native tool-call emission, and continuation
after a tool result. The run must also record per-check latency, token usage when exposed,
package versions, and sampled peak server RSS.

The relational layer qualifies separately: source provenance and row counts must match,
every report must equal the JSON reference, runtime writes must fail, and the period query
must use its composite index.

The Stage 7 suite qualifies the end-to-end investigation separately: every public scenario
must pass all behavior, provenance, evidence, grounding, safety, and request-budget gates.
