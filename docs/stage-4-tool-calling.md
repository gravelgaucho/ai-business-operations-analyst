# Stage 4: bounded analytics tool calling

Stage 4 connects the qualified local model to the deterministic analytics built in Stage 3.
The model chooses an analysis and explains its result; ordinary Python still performs every
filter, join, ranking, and calculation.

## Available tools

| Tool | Evidence returned | Bounded inputs |
|---|---|---|
| `get_account_support_risk` | Distinct account ARR exposed to open priority tickets | 1–20 results; P0–P3 |
| `get_product_area_support_risk` | Product-area exposure through account, ticket, and component joins | 1–20 results; P0–P3 |
| `compare_closed_won_pipeline` | Closed-won opportunity ACV variance, contributors, segments, and concentration | Explicit periods; USD or GBP; 1–20 results |

The catalog has no write tool, arbitrary query language, filesystem access, shell access,
network access, or generic code execution. The dataset is authenticated against its pinned
source manifest and file hashes before the model runs.

## Execution path

```text
Business question
      |
      v
Local model selects a typed tool and arguments
      |
      v
Pydantic validates names, dates, enums, and bounds
      |
      v
Deterministic Python reads the verified synthetic dataset
      |
      v
Typed evidence returns to the same model run
      |
      v
Concise answer plus auditable tool-call trace
```

The run is limited to five model requests and four tool calls. A model answer that completes
without at least one successful analytics tool return is rejected rather than presented as
evidence-backed analysis.

## Run it

Start the loopback-only model server:

```bash
make server
```

In another terminal:

```bash
business-ops-analyze \
  "Which five accounts have the most ARR exposed to open P1 support tickets?"
```

The command returns JSON containing the question, answer, tool names and validated arguments,
whether each call returned successfully, and request/token counts reported by the runtime.

Run the three-case local-model qualification with:

```bash
make qualify-tools
```

Machine-specific evidence is written to `artifacts/stage4_qualification.json` and is ignored
by Git. The committed milestone notes summarize the verified run without publishing a large
generated artifact.

## Verified local-model results

On 2026-09-03, `mlx-community/Qwen3.8-27B-4bit` passed all three cases against the pinned
Maple Payments corpus:

| Case | Expected and selected tool | Requests | Tool calls | Elapsed |
|---|---|---:|---:|---:|
| Account support risk | `get_account_support_risk` | 2 | 1 | 21.84 s |
| Product-area support risk | `get_product_area_support_risk` | 2 | 1 | 19.58 s |
| Q1 2026 vs Q4 2025 pipeline | `compare_closed_won_pipeline` | 2 | 1 | 28.63 s |

The answers preserved the expected evidence: Vantara at $432,000 ARR exposure,
Subscription Lifecycle Management at $732,000, and a 61.37% closed-won opportunity ACV
decline led by MercadoPay with a $2,810,000 decrease. Total elapsed time was 70.05 seconds.

This qualification demonstrates correct tool selection and continuation for three fixed
representative questions. It is not yet a broad model-quality evaluation; a larger scenario
suite belongs with the later investigation-controller milestone.

## Interpretation boundaries

- ARR at risk is exposure associated with matching open tickets, not predicted churn or loss.
- Multiple tickets do not multiply the same account ARR within an account ranking.
- Product exposure counts an account once per affected component.
- Opportunity ACV is grouped by target close date and current final stage; it is not recognized
  revenue.
- These tools identify patterns and contributors. They do not establish causation.

## Deliberate non-goals

This stage does not add an investigation planner, long-lived memory, MCP, RAG, embeddings,
private data, arbitrary dataset queries, write actions, or a UI. Coordinating a broader,
multi-step investigation remains a later milestone.
