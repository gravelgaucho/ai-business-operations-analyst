# Stage 5: controlled investigation agent

Stage 5 turns the single-tool analyst into a bounded investigation workflow. The model still
uses judgment to frame hypotheses and select the next analysis, while the application owns
execution, evidence state, stopping, and acceptance.

## What the workflow does

```text
Business question
      |
      v
Typed classification + bounded plan
      |
      v
Model selects one unused planned analysis
      |
      v
Python validates inputs and executes a deterministic report
      |
      v
Observation is recorded and supplied to the next decision
      |
      v
Evidence gate: two distinct analyses + required overlap test
      |
      v
Typed synthesis + citation and causal-restraint validation
```

The sequence is not hard-coded. For the qualification question, the generated plan listed
the overlap analysis first and the pipeline comparison third. After considering the plan,
the model chose to establish the pipeline baseline first, then chose the overlap test after
seeing those results.

## Controlled state

Each completed run returns:

- the original question and typed investigation plan;
- each model decision and its rationale;
- validated analysis names and arguments;
- the complete deterministic observation from every executed analysis;
- the explicit stop reason;
- findings, hypothesis assessments, limitations, unresolved questions, and recommendation;
- model request, token, and analysis-call counts.

The application permits at most four distinct planned analyses. It has no file, shell,
network, write, or arbitrary-query tool. The pinned dataset is verified before any model
request is made.

## Cross-system validation

Stage 5 adds `test_support_pipeline_overlap`. Python—not the language model—joins the account
IDs of the largest closed-won ACV decliners with accounts that have matching open priority
tickets. It returns overlap count, share of accounts, share of decline value, and the matching
account details.

This is an association screen. It does not test ticket timing, historical ticket status,
opportunity stage history, or causal identification.

## Why the application owns the loop

The first live attempt let Pydantic AI and the model manage the complete native tool loop.
The model called one analysis, submitted a conclusion too early, and repeated that conclusion
after explicit retry messages. That behavior failed the evidence gate.

The final design separates three model judgments—planning, next-analysis selection, and
synthesis—from deterministic control. This is both more reliable and easier to audit:
an early conclusion is structurally impossible, an unplanned or repeated analysis is rejected,
and synthesis cannot begin until the evidence gate passes.

## Verified local-model result

On 2026-09-03, `mlx-community/Qwen3.8-27B-4bit` investigated:

> Did open P1 support issues explain the Q1 2026 decline in closed-won USD opportunity ACV
> versus Q4 2025?

All 9 qualification checks passed:

| Measurement | Result |
|---|---:|
| Model-selected analyses | `compare_closed_won_pipeline` → `test_support_pipeline_overlap` |
| Distinct completed analyses | 2 |
| Model requests | 6 |
| Model tokens | 16,261 |
| End-to-end elapsed time | 162.77 s |
| Peak server RSS | 15.259 GiB |
| Controller checks | 9/9 passed |

The deterministic evidence showed:

- closed-won USD opportunity ACV fell from $80,700,000 to $31,175,000, a 61.37% decrease;
- 1 of the top 10 decline contributors had an open P1 ticket;
- that account represented 8.57% of the top-10 absolute decline value.

The accepted conclusion rated both hypotheses **inconclusive** with **low confidence**. The
observed overlap does not support attributing the overall decline to open P1 issues, but the
available data cannot establish or rule out causation because ticket timing and history are
missing.

The six requests include one safety retry. The initial synthesis overstated the evidence;
the semantic gate rejected it and the model corrected the final result. The 162.77-second
latency is acceptable for framework qualification but too slow for a polished interactive
experience without later optimization.

## Run it

With the loopback-only model server running:

```bash
business-ops-investigate \
  "Did open P1 support issues explain the Q1 2026 decline in closed-won USD opportunity ACV versus Q4 2025?"
```

To reproduce the qualification and write machine-specific evidence to the ignored
`artifacts/stage5_qualification.json` file:

```bash
make qualify-investigation
```

## Deliberate non-goals

This stage does not add MCP, RAG, embeddings, private data, a UI, write actions, autonomous
external actions, long-lived memory, or statistical causal inference.
