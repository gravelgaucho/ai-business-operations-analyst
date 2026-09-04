# Stage 7: repeatable reliability evaluation

Stage 7 turns a successful demonstration into a repeatable qualification contract. The
suite asks the local model more than one kind of business question, runs each through the
same controlled investigation workflow, and scores observable behavior rather than writing
style.

## Why this milestone comes now

A single strong answer does not establish reliability. Before adding more data access, a UI,
or product-specific workflows, the project needs a way to detect regressions when the model,
prompt, controller, or storage implementation changes.

The committed suite is intentionally small and safe to publish. It proves the evaluation
architecture without publishing a future commercial product's full scenario library,
scoring strategy, or domain-specific operating knowledge.

## Public qualification scenarios

| Scenario | Required evidence path | Primary behavior under test |
|---|---|---|
| `causal_attribution` | Pipeline comparison + support/pipeline overlap | Exact metrics, grounded citations, and causal restraint |
| `support_prioritization` | Account risk + product-area risk | Correct cross-functional evidence selection and review-oriented recommendations |

Both scenarios use only the pinned synthetic Maple Payments dataset and the four existing
read-only reports. No new data permission or model tool is introduced.

## Reliability gates

Every scenario is evaluated independently against eleven gates:

1. the question classification falls within the accepted intent family;
2. every scenario-required analysis was executed;
3. execution remained bounded and did not repeat an analysis;
4. every completed action has a matching observation;
5. every observation identifies the pinned synthetic source and commit;
6. deterministic evidence anchors match the verified dataset values;
7. every planned hypothesis is assessed exactly once;
8. every finding and assessment cites only an executed analysis;
9. the conclusion does not claim an unperformed statistical test;
10. causal scenarios remain explicitly limited;
11. every run stays within its model-request budget.

The suite passes only when every gate in every scenario passes. A percentage is reported for
diagnosis, but a high average cannot conceal a failed safety or grounding gate.

## Architecture

```text
Versioned public scenario
          |
          v
Existing bounded investigation controller
          |
          v
Typed state + deterministic observations
          |
          v
Model-neutral evaluator
          |
          +---- behavioral checks
          +---- source-provenance checks
          +---- exact evidence anchors
          +---- safety and grounding checks
          |
          v
Auditable scenario and suite result
```

The evaluator receives `InvestigationState`; it does not know whether Qwen, another local
model, or a remote test endpoint produced that state. This keeps future model comparisons
fair and makes model replacement a measured decision.

## Verified local-model result

On 2026-09-03, `mlx-community/Qwen3.8-27B-4bit` passed both scenarios and all 22 individual
gates in one current-code run:

| Scenario | Analyses selected | Score | Elapsed | Model requests | Model tokens |
|---|---|---:|---:|---:|---:|
| Causal attribution | Pipeline comparison → support overlap | 100% | 122.30 s | 5 | 11,557 |
| Support prioritization | Account risk → product risk → support overlap | 100% | 99.14 s | 5 | 8,217 |
| **Suite** | **2 scenarios** | **100%** | **221.44 s** | **10** | **19,774** |

The causal run measured the verified 61.37% closed-won ACV decline and one-account overlap,
then kept attribution unresolved. The model initially labeled the plainly causal question as
predictive; the deterministic intent guard enforced `causal` and preserved that correction in
the returned audit state.

Qualification also caught a more serious date failure during development: one model run used
the same six-month range for both comparison periods and therefore produced a false flat
result. Stage 7 moved explicit quarter resolution into ordinary code. Q1 2026 now always maps
to 2026-01-01 through 2026-03-31 and Q4 2025 to 2025-10-01 through 2025-12-31 before a report
runs. This is exactly why release gates evaluate deterministic evidence rather than accepting
a plausible narrative.

## Run it

With the loopback-only model server running and the Stage 6 database built:

```bash
make qualify-evaluation
```

Run one diagnostic scenario when iterating:

```bash
.venv/bin/python scripts/qualify_evaluation.py --scenario causal_attribution
```

At the Stage 7 tag, the complete local evidence artifact was written to the ignored
`artifacts/stage7_qualification.json` file. The current `make qualify-evaluation` target now
runs the expanded Stage 8 suite and writes `artifacts/stage8_qualification.json`. These
artifacts are ignored because model transcripts and machine-specific measurements should be
reviewed before publication.

## Commercial boundary

The public scenarios establish engineering credibility, not the complete product moat. A
larger private suite can later test proprietary workflows, industry-specific operating
knowledge, customer configurations, adversarial cases, service-level objectives, and
business outcome quality without changing the evaluator contract.

## Deliberate non-goals

This stage does not add MCP, RAG, embeddings, another dataset, write actions, long-lived
memory, production serving, or a user interface. It also does not claim that two public
scenarios constitute production readiness.
