# Architecture through Stage 12

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
        OpenAI-compatible API       governed capability execution
                 |                                   |
        local model server      reports + semantic query + cited retrieval
                 |                                   |
     Qwen3.8 weights (replaceable)      data repository protocol
                                                     |
                                      +--------------+--------------+
                                      |                             |
                                 JSON reference               SQLite read-only
                                      |                             |
                                      +------ verified source ------+
                                                    |
                                      +-------------+-------------+
                                      |                           |
                                      v                           v
                         source + semantic catalog      business evidence testbed
                                      |                  (coverage contract only)
                                      v
                         content-addressed evidence ledger
                                      |
                                      v
                         typed claims + portable audit bundle
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

Stage 8 makes provenance a first-class application contract. After each deterministic report,
Python creates an immutable evidence record containing the approved source snapshot, logical
file or table locators, executed method and arguments, reported record identifiers, complete
result, and SHA-256 result digest. The evidence ID is derived from that content rather than
invented by the model. Synthesis receives this ledger and must cite its exact evidence IDs.

The conclusion now separates verified facts, analytical findings, hypothesis assessments,
business implications, recommendations, and confidence. Every material claim cites at least
one evidence record. Recommendations state their rationale and whether human review is
required. Confidence records evidence coverage, source agreement, and data quality instead of
presenting an unexplained score. Application validation rejects unknown evidence citations,
tampered records, incomplete ledgers, and conclusions that violate the existing causal or
statistical boundaries.

A completed state can be exported as a portable audit bundle. It includes the source snapshot
descriptors, evidence ledger, normalized claim index, execution trace, and final conclusion.
It intentionally uses logical source locators rather than exposing machine-specific absolute
paths.

A narrow deterministic conclusion policy enforces governance rules that should not depend on
prompt obedience. It calibrates source agreement, preserves source-defined metric names, and
keeps underidentified causal implications and recommendations inside a human-review boundary.
Every policy correction is represented in investigation state and exported with the audit
bundle. Evidence records, calculations, and citations remain unchanged. Invalid evidence IDs,
missing hypothesis assessments, unsupported statistics, and unjustified causal confidence are
not papered over; they remain validation failures or model retries.

Stage 9 replaces duplicated source and tool descriptions with a typed capability catalog. A
content digest covers the approved source snapshot, business entities, metric definitions,
analytical capabilities, parameters, outputs, source locators, implementations, and
interpretation boundaries. The planner and direct analyst receive a compact catalog view.
Evidence construction reads its source locator, method version, and implementation identity
from the same definitions, and evaluation confirms that the plan, execution trace, and
evidence ledger remain aligned with them.

The complete catalog snapshot is stored in investigation state and portable audit bundles.
This answers an important audit question: not only “what evidence supported the answer?” but
also “what sources and tools were approved when the system formed its plan?” A catalog digest
changes whenever a governed definition changes, so an earlier investigation cannot silently
inherit later semantics.

Stage 10 adds a governed semantic query between the capability layer and repository boundary.
The model never supplies SQL, column names, table names, operators, or expressions. It emits a
typed request for one registered metric, an explicit period and currency, one or two approved
dimensions, and a bounded row limit. Pydantic rejects extra or invalid inputs before execution.

For SQLite, application-owned mappings compile the dimension enums into reviewed expressions;
all user/model values remain bound parameters. The connection is still opened in read-only and
query-only modes. The JSON repository independently executes the same typed request and serves
as a parity oracle. The report returns the validated semantic request with its rows, metric
definition, calculation, source, and interpretation boundary, so provenance captures what was
asked as well as what was returned.

This is the first capability that is flexible inside a controlled semantic envelope. It proves
that broader business questions do not require either a fixed report for every phrasing or
unrestricted model-generated SQL. Adding another metric or dimension remains a reviewed code,
catalog, test, and evaluation change.

Stage 11 adds a second deterministic evidence path for unstructured files. It does not crawl the
dataset directory. A typed manifest identifies approved internal documents; ingestion accepts
only published, internal, Markdown entries with a single local filename. Paths are resolved
inside the governed directory, symbolic links and oversized files are rejected, and duplicate
document IDs or filenames invalidate the corpus. Draft and unlisted files are never searchable.

Markdown is split at heading boundaries into bounded passages while retaining source line
numbers. HTML comments are removed with line preservation, which excludes benchmark canaries
from model context without changing citation coordinates. Deterministic BM25 lexical ranking
returns at most eight passages. Every passage contains document ID, title, publication status,
modified time, logical locator, section, line range, excerpt hash, relevance score, and text.

Retrieved text is always labeled untrusted evidence. It is never executed, interpreted as an
agent instruction, or allowed to expand tool authority. The model may choose the retrieval
capability, but the controller uses the original business question as the exact search request;
the action trace, result, and evidence method must agree. A claim cites the immutable evidence
record, which in turn contains the independently checkable line-level document citations.

Stage 12 adds a separate business evidence testbed contract alongside the executable capability
catalog. It inventories the full authenticated Maple snapshot and classifies every source asset,
entity, relationship, metric requirement, and flagship scenario as active, available but not
onboarded, or planned. The testbed is content-addressed and self-validating, and its inventory
reauthenticates the pinned dataset before counting records.

This contract is deliberately not a planning catalog. Only `CapabilityCatalog` definitions grant
execution authority. A testbed item can describe a future booking or revenue source without
allowing the model to query it, cite it, or infer that it exists. Qualification verifies that all
active primary locators already belong to cataloged capabilities and every planned finance locator
remains outside them.

The testbed supplies the canonical business entity spine needed for a multi-system analyst while
preserving source-specific records. It defines the planned chain from account and opportunity
through executed contract, booking, subscription, invoice, revenue event, and payment. Semantic
boundaries keep opportunity ACV, bookings, billings, recognized revenue, and cash distinct.

Scenario readiness is derived from the coverage status of required metrics. The existing
support/pipeline and cited-document scenarios qualify; product-issue/customer-impact analysis is
partial; and bookings-versus-revenue plus transaction review remain blocked until their synthetic
finance evidence is implemented and approved.

## Revised product boundary

The product direction is now a general local AI business analyst, not a Maple-specific support
and pipeline workflow. The completed stages form its initial execution and governance core.
The next architectural layers can first onboard existing product issues, knowledge-base articles,
and transcripts, then add the minimum safe synthetic commercial chain needed for bookings and
recognized-revenue analysis. Retrieval recall, embeddings, and cross-source reconciliation remain
separate evaluated decisions.
RAG, when introduced, will remain one capability; it will not replace the controller,
deterministic analytics, or evidence ledger. Maple Payments remains the first evaluation domain,
and transaction/contract/pricing review remains a future benchmark domain and possible vertical
package.

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
- No embeddings, vector store, or open-ended RAG
- No private or proprietary business dataset
- No UI
- No production serving claims
- No vision qualification yet
- No proprietary scenario library or product-specific scoring logic
- No generated finance or operations extension records yet

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

The Stage 10 suite qualifies the end-to-end investigation separately: every public scenario
must pass behavior, source provenance, evidence integrity, claim-level citation, grounding,
safety, catalog alignment, governed-query contract and result-bound checks, and request-budget
gates. The new comparative scenario requires both the fixed period-comparison report and the
governed regional breakdown. The September 4, 2026 milestone run passed all three scenarios at
22/22 gates each in 375.009 seconds using the local 27B baseline.

The Stage 11 suite adds a fourth cross-modal scenario and four gates: the executed document query
must match its action and evidence record; every passage must validate against its hash,
published status, catalog locator, line range, and content-sanitization boundary; material
numbers and sensitive consequences must exist in the exact evidence cited by each claim; and
template terms cannot be applied to accounts without agreement or tier verification. Planning
also rejects ranking-only hypotheses that require unavailable concentration math. Narrow,
deterministic conclusion corrections remove unsupported claim content or document-language
leakage and record the exact rule without modifying evidence. Template-based confidence is
calibrated to the missing account-to-agreement mapping. The accepted September 4, 2026 run passed
all four scenarios at 26/26 gates in 565.117 seconds using the local 27B baseline.

Stage 12 qualifies independently without loading the model. The inventory must authenticate the
source; match the 12 pinned asset counts; partition 21 assets into five active, seven available,
and nine planned assets; resolve all 11 declared cross-source integrity checks; prove active
locators are registered; prove planned locators are not executable; and derive the expected
readiness for all five flagship scenarios. The accepted run passed all nine checks and counted
50,411 records. Its testbed digest is
`sha256:ad96e291eaf9d428e4017dda36f5bd73f2d02dad204072c17d6a3ff2adb9c4d8`.
