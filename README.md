# Local AI Business Analyst

A local-first, evidence-grounded AI business analyst and internal strategy consultant.
It is designed to investigate ambiguous business questions across organizational data,
use governed analytical tools, test hypotheses, and produce decision-ready findings whose
important claims can be audited back to internal evidence.

## Progress

| Milestone | Status | Proof |
|---|---:|---|
| Stage 0 — local inference | Complete | Tagged `stage-0` |
| Stage 1 — Python model client | Complete | Tagged `v0.2-python-client` |
| Stage 2 — typed business questions | Complete | Tagged `v0.3-structured-output` |
| Stage 3 — deterministic analytics | Complete | Tagged `v0.4-analytics-engine` |
| Stage 4 — bounded tool calling | Complete | Tagged `v0.5-tool-calling` |
| Stage 5 — controlled investigation agent | Complete | Tagged `v0.6-investigation-agent` |
| Stage 6 — verified relational data layer | Complete | Tagged `v0.7-sql-data-layer` |
| Stage 7 — repeatable reliability evaluation | Complete | Tagged `v0.8-evaluation-suite` |
| Stage 8 — claim-level evidence provenance | Complete | Tagged `v0.9-evidence-provenance` |
| Stage 9 — source and capability catalog | Complete | Tagged `v0.10-source-capability-catalog` |
| Stage 10 — governed structured query | Complete | Tagged `v0.11-governed-structured-query` |
| Stage 11 — cited document retrieval | Complete | Tagged `v0.12-cited-document-retrieval` |
| Stage 12 — business evidence testbed | Complete | Tagged `v0.13-business-evidence-testbed` |

This repository contains thirteen foundations:

- **Stage 0 — Local Model Qualification:** prove a capable open model runs privately on
  Apple silicon behind a standard HTTP interface.
- **Stage 1 — Model Boundary:** send, inspect, validate, and handle those HTTP requests
  in our own Python application before introducing an agent framework.
- **Stage 2 — Typed Business Questions:** use Pydantic and Pydantic AI to turn natural
  language into a validated application object, including retrying malformed output.
- **Stage 3 — Deterministic Analytics:** safely import a public synthetic enterprise
  dataset and calculate rankings, comparisons, segmentation, variance, and concentration
  without asking an LLM to do arithmetic or data joins.
- **Stage 4 — Bounded Tool Calling:** let the model select from read-only, typed
  analytics tools, then return a grounded answer with an auditable call trace.
- **Stage 5 — Controlled Investigation Agent:** classify a question, build a bounded plan,
  select multiple analyses adaptively, preserve every observation, enforce evidence and
  causal-restraint gates, and produce a typed decision-ready conclusion.
- **Stage 6 — Verified Relational Data Layer:** atomically normalize the authenticated JSON
  snapshot into SQLite, preserve source provenance, enforce relationships and indexes, and
  expose the same typed reports through a read-only repository boundary.
- **Stage 7 — Repeatable Reliability Evaluation:** run versioned public scenarios through
  the same investigation contract and score classification, evidence selection, provenance,
  deterministic values, citation grounding, causal restraint, and execution budgets.
- **Stage 8 — Claim-Level Evidence Provenance:** turn every deterministic observation into a
  content-addressed evidence record, require material claims and recommendations to cite
  stable evidence IDs, and export a portable audit bundle for independent review.
- **Stage 9 — Source and Capability Catalog:** give planning, execution, provenance, and
  evaluation one typed, content-addressed definition of approved sources, business entities,
  metric semantics, analytical capabilities, and interpretation limits.
- **Stage 10 — Governed Structured Query:** let the analyst answer approved dimensional
  breakdown questions through a typed semantic request that compiles to parameterized,
  read-only SQL while preserving JSON parity and evidence provenance.
- **Stage 11 — Cited Document Retrieval:** search only published, manifest-approved internal
  documents; return bounded passages with document identity, exact lines, and content hashes;
  and combine those citations with structured evidence in one controlled investigation.
- **Stage 12 — Business Evidence Testbed:** inventory the complete authenticated Maple source,
  distinguish executable, available, and absent data, define a canonical cross-system entity
  spine, and make future financial-scenario readiness a versioned, machine-checked contract.

## What Stage 0 proves

| Capability | Why it matters to the future product |
|---|---|
| Local inference | Sensitive business evidence can remain on-device. |
| OpenAI-compatible API | The model can be replaced without rewriting the application. |
| Schema-constrained JSON | Findings can move reliably into reports and workflows. |
| Native tool calls | The model can request evidence instead of inventing it. |
| Multi-turn continuation | It can use returned evidence and finish an investigation. |
| Measured speed and memory | Architecture decisions are grounded in this Mac's real limits. |

## Qualified baseline

- Model: `mlx-community/Qwen3.8-27B-4bit`
- Upstream: `Qwen/Qwen3.8-27B`
- Runtime: MLX + MLX-LM + MLX-VLM
- Interface: OpenAI-compatible `/v1/chat/completions`
- Default binding: `127.0.0.1:8080` (local machine only)
- Qualification: 5/5 checks passed; 26.3–28.8 warm decode tokens/s; 15.697 GiB peak RSS

The model identifier, URL, and context limit are configuration—not application logic.
See [docs/architecture.md](docs/architecture.md) for the boundary.

Stage 4 qualified all three analytics tools with the local baseline. Each case required one
native tool call and one continuation request; all 3/3 selected the expected tool and carried
the required evidence into the final answer. See
[docs/stage-4-tool-calling.md](docs/stage-4-tool-calling.md).

Stage 5 qualified a real multi-step investigation in 162.77 seconds with 15.259 GiB peak
server RSS. The model selected a pipeline baseline followed by the cross-system support
overlap test; all 9 controller checks passed. The result correctly remained causally
inconclusive because ticket timing and opportunity history are absent. See
[docs/stage-5-investigation-agent.md](docs/stage-5-investigation-agent.md).

Stage 6 imported 42 accounts, 8,704 opportunities, 32,768 tickets, 40 product parts, and
32,768 ticket-component links into a 6.9 MiB SQLite database. All four reports matched the
JSON reference exactly; source, row-count, read-only, and index checks all passed. See
[docs/stage-6-sql-data-layer.md](docs/stage-6-sql-data-layer.md).

Stage 7 ran two end-to-end business scenarios against 11 reliability gates each. Both passed
at 100% in 221.44 seconds total. Qualification also proved that the controller can correct an
unambiguous intent-label error and enforce exact quarter boundaries before executing a
report. See [docs/stage-7-evaluation-suite.md](docs/stage-7-evaluation-suite.md).

Stage 8 reran both scenarios against 18 gates each. Both passed at 100% in 240.645 seconds
total using the local `Qwen3.8-27B-4bit` baseline. Each run executed exactly the two relevant
analyses, produced two tamper-evident evidence records, cited every material claim, and
round-tripped as a self-validating audit bundle. The causal case also preserved the
closed-won opportunity ACV metric and recorded the controller's conservative causal-policy
correction. See
[docs/stage-8-evidence-provenance.md](docs/stage-8-evidence-provenance.md).

Stage 9 added two catalog-governance gates and passed both scenarios at 20/20 in 240.783
seconds. The model planned from the approved catalog, executed exactly the four expected
scenario analyses, and produced evidence whose registered method versions, implementations,
read-only tables, and source identity all matched the embedded catalog snapshot. See
[docs/stage-9-source-capability-catalog.md](docs/stage-9-source-capability-catalog.md).

Stage 10 adds a fifth capability for closed-won opportunity ACV breakdowns by one or two
approved dimensions: account, region, close month, or close quarter. Dates, currency, and row
limits are validated; SQL values are parameterized; identifiers come only from application
code; and the JSON and SQLite implementations must return identical typed results. All three
public scenarios passed 22/22 gates in 375.009 seconds with the local baseline. See
[docs/stage-10-governed-structured-query.md](docs/stage-10-governed-structured-query.md).

Stage 11 adds deterministic lexical retrieval over the seven published internal documents in
the approved synthetic snapshot. Drafts, unlisted files, standalone canaries, and HTML comments
are excluded. Every returned passage carries a logical file locator, section, exact line range,
and SHA-256 hash. The first cross-modal scenario combines P1 account exposure with the published
Standard MSA's response commitments. All four public scenarios passed 26/26 gates in 565.117
seconds with 21 model requests, 61,287 tokens, and eight deterministic tool calls. The 108 fast
tests also cover claim-to-citation number scope, hidden synthesis arithmetic, document-language
leakage, template applicability, and calibrated confidence. See
[docs/stage-11-cited-document-retrieval.md](docs/stage-11-cited-document-retrieval.md).

Stage 12 verifies 50,411 records across 12 existing Maple assets and all 11 declared cross-source
integrity checks. Five assets already support approved capabilities, seven are present but
deliberately not onboarded, and nine finance and
operations assets are explicitly planned and absent. Two current scenarios remain qualified, a
product-issue scenario is partial, and the bookings-versus-revenue and transaction-review cases
are machine-blocked until their required data exists. The testbed defines 19 canonical entities,
14 metric requirements, 16 relationships, and five flagship scenarios without granting the model
new source authority. See
[docs/stage-12-business-evidence-testbed.md](docs/stage-12-business-evidence-testbed.md).
All nine deterministic qualification checks and all 114 fast repository tests pass without
loading the model.

## Reproduce it

Requirements: Apple silicon, Homebrew Python 3.13, and roughly 20 GB of free disk
space for packages plus the model cache.

```bash
make setup
cp .env.example .env
make data
make database
make server
```

In a second terminal:

```bash
business-ops "Revenue fell while customer count stayed flat. What should we investigate?"
business-ops-classify "Why did Northeast revenue decline last quarter?"
business-ops-catalog --planning-view
business-ops-testbed
business-ops-documents "Standard MSA P1 initial response resolution"
business-ops-query --start 2026-01-01 --end 2026-03-31 --dimension region
business-ops-analytics account-risk
business-ops-analytics product-risk --top 5
business-ops-analytics pipeline-change --top 5
business-ops-analytics --database data/derived/maple_payments.sqlite3 account-risk
business-ops-analyze "Which accounts have the most ARR exposed to open P1 tickets?"
business-ops-investigate \
  "Did open P1 issues explain the Q1 2026 closed-won ACV decline versus Q4 2025?"
business-ops-investigate \
  "Did open P1 issues explain the Q1 2026 closed-won ACV decline versus Q4 2025?" \
  --audit-output artifacts/example-audit.json
make qualify-evaluation
make qualify-testbed
business-ops "Analyze the same question" --show-request --raw
make qualify
```

The first server start downloads about 16.1 GB. Later starts use the local Hugging
Face cache. Qualification results are written to `artifacts/qualification.json` and
intentionally ignored by Git because they are machine- and run-specific. The verified
snapshot for this milestone is summarized in [docs/qualification.md](docs/qualification.md).

## Repository map

```text
scripts/start_server.sh     Local-only model server launcher
scripts/qualify.py          End-to-end API and performance qualification
scripts/qualify_testbed.py  Verified business-data coverage acceptance checks
src/business_ops/client.py  Model-neutral OpenAI-compatible Python client
src/business_ops/catalog.py Approved source, entity, metric, and analytical-capability catalog
src/business_ops/catalog_cli.py Human- and machine-readable catalog inspection
src/business_ops/testbed.py Versioned business-data coverage and canonical-entity contract
src/business_ops/testbed_cli.py Verified source inventory and scenario-readiness inspection
src/business_ops/document_cli.py Bounded published-document search with exact citations
src/business_ops/query_cli.py Governed semantic-query inspection
src/business_ops/cli.py     Inspectable business-question command line
src/business_ops/questions.py  Validated business-question contract
src/business_ops/classifier.py Pydantic AI structured-output boundary
src/business_ops/analytics/    Model-free calculations and result types
src/business_ops/reports.py    Typed, reusable business-analysis reports
src/business_ops/analyst.py    Bounded tool catalog and model continuation loop
src/business_ops/investigation.py Typed plan, controlled evidence loop, and conclusion gates
src/business_ops/provenance.py Content-addressed evidence ledger and portable audit contract
src/business_ops/evaluation.py Versioned scenarios and model-neutral reliability gates
src/business_ops/datasets/     Verified JSON import, repository boundary, and SQLite adapter
tests/                      Fast tests that do not load the model
docs/architecture.md        Design boundary and deliberate non-goals
docs/data-safety.md          Public test-data acceptance policy
docs/qualification.md       Hardware, versions, evidence, and measured results
docs/stage-1-model-boundary.md  Request/response learning walkthrough
docs/stage-2-typed-questions.md Typed-output design and verified example
docs/stage-3-analytics-engine.md Deterministic analysis and verified findings
docs/stage-4-tool-calling.md  Tool contracts, controls, and interpretation boundaries
docs/stage-5-investigation-agent.md Multi-step controller and verified investigation
docs/stage-6-sql-data-layer.md Relational schema, parity proof, and measured results
docs/stage-7-evaluation-suite.md Public scenario contract and commercial evaluation boundary
docs/stage-8-evidence-provenance.md Claim-level citations and audit-bundle walkthrough
docs/stage-9-source-capability-catalog.md Governed discovery and semantic-boundary walkthrough
docs/stage-10-governed-structured-query.md Typed query contract and SQL safety boundary
docs/stage-11-cited-document-retrieval.md Governed ingestion, retrieval, and citation boundary
docs/stage-12-business-evidence-testbed.md Unified data coverage and extension specification
docs/runbook.md             Setup, operation, troubleshooting, and cleanup
```

## Scope boundary

Stage 12 retains six read-only analytical capabilities over DevRev's synthetic, Apache-2.0
licensed Maple Payments data. Its investigation loop is capped at four distinct analyses.
The catalog and evidence contracts are general, but the current source adapter and analyses
are not. Cataloging an entity or modality does not make it queryable; execution requires an
explicitly registered capability.
The semantic query is not arbitrary SQL: it exposes one approved metric, four approved
dimensions, two currencies, explicit dates, and a maximum of 50 rows. It does **not** add MCP,
embeddings, a vector database, broad filesystem access, RAG over arbitrary sources, private
business data, write actions, arbitrary SQL,
long-lived memory, or a user interface. The testbed registers available and planned data for
coverage analysis only; neither state makes that data visible to the model or executable.

## Safety note

The included development server is for local qualification, not production. It binds
to loopback by default and has no authentication. Do not expose it to a network.

## Copyright and permitted use

Copyright © 2026 Julio Campos. All rights reserved. This public repository is available for
portfolio review; it does not grant permission to reuse or commercialize the original project
code. Third-party models, dependencies, and datasets retain their own licenses. Earlier
versions released under MIT remain subject to the terms that accompanied those versions.
See [COPYRIGHT.md](COPYRIGHT.md) for the complete notice.
