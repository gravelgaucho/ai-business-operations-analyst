# Stage 8: Evidence provenance and audit bundles

## Objective

Stage 8 turns provenance from a tool-name citation into a validated application contract.
Important factual claims, analytical findings, hypothesis assessments, business implications,
and recommendations must now resolve to immutable evidence records produced by executed tools.

This milestone does not add another data source, RAG, generated SQL, or a user interface. It
strengthens the existing Maple Payments investigation before the architecture becomes broader.

## Evidence contract

Each deterministic report creates one `EvidenceRecord` containing:

- a content-derived `EV-` identifier;
- the matching observation identifier;
- the approved dataset, repository, commit, archive checksum, license, and synthetic-data flag;
- logical source file or SQLite table locators;
- the tool, implementation, method version, and validated arguments;
- the calculation or metric definition when the report supplies one;
- identifiers reported in the result;
- the complete deterministic result and its SHA-256 digest.

The identifier covers the source descriptor, method, arguments, observation, and result digest.
Changing the result, query arguments, source snapshot, or method therefore invalidates the
record. The application constructs these records; the language model cannot choose their IDs
or change their contents.

## Claim contract

The conclusion explicitly separates:

1. `verified_fact` — a value or state directly returned by an approved source-backed report;
2. `analytical_finding` — a deterministic comparison, aggregation, or cross-source result;
3. hypothesis assessment — supported, rejected, or inconclusive;
4. business implication — what the verified analysis may mean for management attention;
5. recommendation — a proposed next step, its rationale, and a human-review flag;
6. confidence — level, rationale, evidence coverage, source agreement, and data quality.

Every material claim contains one or more evidence IDs. Application validation rejects a
conclusion that cites an ID absent from the ledger. The earlier causal and unsupported-statistic
gates still apply.

Evidence provenance does not turn a recommendation into a fact. Its citations identify the
facts and findings that motivate the recommendation. Likewise, an association remains an
association even when it has perfect source provenance.

## Portable audit bundle

Run an investigation with `--audit-output` to create an independent JSON artifact:

```bash
business-ops-investigate \
  "Did open P1 issues explain the Q1 2026 closed-won ACV decline versus Q4 2025?" \
  --audit-output artifacts/example-audit.json
```

The command refuses to overwrite an existing audit file. The bundle contains:

- a deterministic investigation identifier;
- the original question;
- unique source snapshot descriptors;
- the complete evidence ledger;
- a normalized claim-to-evidence index;
- the decision, action, observation, and evidence linkage for every executed step;
- the typed final conclusion.

Logical paths and table names are preserved, while local absolute filesystem paths are omitted.
This makes the artifact useful for portfolio review without publishing workstation details.

## Evaluation gates

The Stage 8 evaluator adds checks for:

- correct question classification and question-relevant analysis scope;
- bounded, distinct tool execution with a complete action/observation trace;
- exactly one evidence record per observation and executed analysis;
- agreement between the visible observation and immutable evidence result;
- valid content-derived evidence IDs and result digests;
- the pinned synthetic source commit and archive checksum;
- deterministic scenario anchors read from the ledger;
- valid evidence citations for every material claim;
- recommendation provenance and complete claim citation coverage;
- calibrated source agreement and preservation of metric definitions;
- complete hypothesis assessment, causal restraint, question-appropriate language,
  unsupported-statistics detection, and request budgets.

Unit tests also alter a recorded result without updating its digest and confirm that validation
rejects the tampered record.

## Deterministic policy boundary

The model still drafts the conclusion, but a narrow controller policy owns non-negotiable
semantic boundaries. It prevents one dataset snapshot from being described as independent
source agreement, prevents closed-won opportunity ACV from being relabeled as revenue, and
keeps a causal-screen recommendation limited to human review and collection of missing timing
and history. Any correction is stored in `conclusion_correction` and the portable audit bundle;
the controller does not alter evidence records, calculations, or citations.

This is intentionally different from silently rewriting an answer. The audit record identifies
which sections changed, which rule triggered, and why. More substantive failures—unknown
evidence IDs, missing hypothesis assessments, unsupported statistics, or high confidence on
an underidentified causal question—still fail validation or return to the model for correction.

## Qualification record

The final Stage 8 run used `mlx-community/Qwen3.8-27B-4bit` through the local
OpenAI-compatible endpoint on September 4, 2026.

| Scenario | Result | Analyses | Requests | Tokens | Time |
|---|---:|---:|---:|---:|---:|
| Causal attribution | 18/18 gates | 2 | 5 | 12,882 | 136.636 s |
| Support prioritization | 18/18 gates | 2 | 4 | 7,290 | 104.008 s |
| Full suite | 2/2 scenarios | 4 total | 9 | 20,172 | 240.645 s |

The causal run created audit bundle `INV-669fd1730f6bd0ba`; the support run created
`INV-ddecc6402830dd64`. Each bundle contained seven cited claims and two evidence records and
successfully round-tripped through independent schema validation. The causal controller
recorded a `causal_decision_boundary` correction to the business implication and
recommendation. No deterministic result, citation, or evidence record changed.

The complete machine-specific result is written to the ignored
`artifacts/stage8_qualification.json` file when `make qualify-evaluation` runs. The documented
values above are the public milestone record; the large raw output stays local because model
wording, token counts, and timings can vary between runs.

## Current limitation

The present evidence records locate the authenticated files or read-only tables used by each
report and include the identifiers returned in the result. They do not yet cite a document
passage or an arbitrary SQL result cell because those capabilities do not exist yet. Later
source adapters will extend the same `SourceLocator` boundary with row, page, slide, section,
and passage locators without changing the claim contract.

The current validator proves that cited evidence exists, is untampered, and came from an
executed analysis. It does not yet prove semantic entailment for every possible natural-language
claim. The bounded evaluation scenarios independently check their known deterministic values;
future scenario contracts will add expected claim-to-evidence mappings as the domain library
grows.
