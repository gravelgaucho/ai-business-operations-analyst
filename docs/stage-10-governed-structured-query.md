# Stage 10: Governed structured query

## Objective

Stage 10 gives the analyst controlled flexibility over structured data without granting it
arbitrary SQL access. The first semantic query answers:

> How does closed-won opportunity ACV break down across approved business dimensions for an
> explicit period and currency?

This deliberately narrow slice proves the architecture needed for broader analytical queries:
a typed semantic request, reviewed compilation, read-only execution, deterministic results,
catalog governance, and complete evidence provenance.

## Query contract

`OpportunityBreakdownQuery` accepts only:

- an explicit inclusive start and end date;
- one or two dimensions from `account`, `region`, `close_month`, and `close_quarter`;
- `USD` or `GBP`;
- a top-row limit from 1 through 50.

Extra fields, reversed dates, duplicate dimensions, unknown dimensions, unknown currencies,
and excessive row limits are rejected. The one registered metric is the sum of current-final-
stage closed-won opportunity ACV by target close date. It is explicitly not recognized revenue.

The report returns its validated `semantic_query` alongside the typed rows. The evidence ledger
therefore preserves the exact analytical request twice: as executed method arguments and as the
request represented in the deterministic result. The evaluator requires them to agree.

## SQL safety boundary

The model and command line never submit SQL. Approved dimension enums map to reviewed SQL
expressions owned by application code. Stage, currency, dates, and row limit use bound `?`
parameters. Runtime connections retain SQLite read-only and query-only enforcement.

The accepted flow is:

```text
natural-language question
        -> typed semantic query
        -> schema validation
        -> application-owned dimension mapping
        -> parameterized read-only SQL
        -> typed bounded rows
        -> evidence record and cited conclusion
```

There is no escape hatch for arbitrary identifiers, predicates, joins, expressions, files,
database writes, or unbounded output. A new metric or dimension requires an explicit code and
catalog change plus tests.

## Independent reference implementation

The authenticated JSON adapter implements the same semantic query without SQL. Tests execute
the typed request through both JSON and SQLite repositories and require exact result parity.
This catches storage-specific drift while keeping the report, agent, and provenance contracts
model- and database-neutral.

## Investigation behavior

The capability catalog now advertises a fifth read-only analysis,
`query_closed_won_opportunity_acv`. The planner is instructed to use it for account, region,
close-month, or close-quarter breakdowns. When a question requests both a period comparison and
a dimensional breakdown, the plan must pair it with `compare_closed_won_pipeline`.

The new public scenario asks the analyst to compare Q1 2026 with Q4 2025 and then break Q1 down
by region. The application supplies the exact calendar-quarter boundaries from deterministic
date logic. The model chooses and sequences the analyses; it cannot reinterpret those dates.

## Verification

Fast verification covers:

- rejection of identifier and currency injection attempts;
- date, dimension-count, uniqueness, and row-limit validation;
- parameterized SQL compilation with only approved identifiers;
- JSON and SQLite result parity;
- controller execution and evidence-argument preservation;
- evaluator detection of action/evidence query drift;
- bounded typed rows using exactly the requested dimensions.

The Stage 10 suite retains the prior 20 evaluation gates and adds
`governed_query_contract` and `governed_query_result_bounds`. The milestone requires all three
public scenarios to pass all 22 gates with the local baseline before release.

## Qualification record

The final Stage 10 run used `mlx-community/Qwen3.8-27B-4bit` through the loopback-only
OpenAI-compatible endpoint on September 4, 2026.

| Scenario | Result | Analyses | Requests | Tokens | Time |
|---|---:|---:|---:|---:|---:|
| Causal attribution | 22/22 gates | 2 | 4 | 12,872 | 134.025 s |
| Support prioritization | 22/22 gates | 2 | 4 | 9,329 | 112.276 s |
| Governed opportunity analysis | 22/22 gates | 2 | 4 | 12,633 | 128.707 s |
| Full suite | 3/3 scenarios | 6 total | 12 | 34,834 | 375.009 s |

Every scenario produced two content-addressed evidence records and cited all material claims.
The new scenario executed `compare_closed_won_pipeline` followed by
`query_closed_won_opportunity_acv`. Its query evidence preserved:

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "dimensions": ["region"],
  "currency": "USD",
  "top_n": 10
}
```

The top deterministic row was `Americas/East` at $9,690,000 closed-won opportunity ACV.
The period report independently measured $80,700,000 in Q4 2025 and $31,175,000 in Q1 2026.

The controller transparently corrected the new scenario's model-proposed descriptive label to
comparative because the question explicitly said “compare.” It also corrected one use of
“revenue” back to the cataloged metric name. Neither correction changed query arguments,
calculations, evidence, or citations. This demonstrates why metric semantics and explicit-intent
guards live in application code rather than depending on prompt obedience.

All runs embedded catalog `stage-10-v1` with digest
`sha256:44e076bd66781c9768e58f67d94fc6215da24da7a20e70ae0b9d5be63ed20193`.
The portable audit identifiers were:

- causal attribution: `INV-779b6110b5314b1d`;
- support prioritization: `INV-9302fe062a971f77`;
- governed opportunity analysis: `INV-c900f0399a98580d`.

The complete machine-specific evidence is written to the ignored
`artifacts/stage10_qualification.json` file. The documented values above are the public
milestone record.

## Current limitation

This is not a general natural-language-to-SQL system. It provides one measure, four dimensions,
two currencies, one source snapshot, simple grouping, and no user-defined filters. It does not
add document retrieval, RAG, MCP, private data, write actions, a UI, causal analysis, forecasting,
or independent-source reconciliation.

Those limits are intentional. Stage 10 proves the safe semantic-query seam that later metrics,
dimensions, and approved sources can extend without weakening the execution or audit boundary.
