# Stage 6: verified relational data layer

Stage 6 adds SQL without changing the business answers. The authenticated Maple Payments
JSON snapshot remains the source of truth; SQLite is a reproducible, derived analytical
store behind a model-neutral repository interface.

## Relational schema

```text
accounts
   | 1
   +----------------< opportunities
   |
   +----------------< tickets
                          |
                          +----< ticket_components >---- product_parts
```

The importer creates five strict tables:

| Table | Purpose | Qualified rows |
|---|---|---:|
| `accounts` | Account identity, region, and ARR | 42 |
| `opportunities` | Stage, currency, ACV, account, and target-close date | 8,704 |
| `tickets` | Account, priority, and current status | 32,768 |
| `product_parts` | Product and component identity | 40 |
| `ticket_components` | Many-to-many ticket/component relationship | 32,768 |

Primary keys, foreign keys, nonnegative value checks, unique source-order fields, and a
composite opportunity period index make the data assumptions executable rather than
implicit. Ticket/component links cannot reference missing tickets or product parts, and
opportunities and tickets cannot reference missing accounts.

## Trust boundary

The build process:

1. verifies the pinned source manifest and every source-file digest;
2. builds the database in a temporary file;
3. imports typed records inside a transaction;
4. validates foreign keys and database integrity;
5. records dataset name, source commit, archive SHA-256, license, and schema version;
6. atomically installs the completed derived database.

Analysis connections use SQLite `mode=ro` plus `PRAGMA query_only = ON`. There is no generic
SQL tool exposed to the language model. The model can still select only the four approved,
typed business reports.

## Repository boundary

Both storage implementations satisfy the same `BusinessDataRepository` protocol:

```text
typed report
     |
     v
BusinessDataRepository
     |
     +---- JSON reference adapter
     |
     +---- read-only SQLite adapter
```

The report layer does not know which storage engine supplied its normalized metric and risk
records. The agent and investigation controller therefore remain unchanged and model-agnostic.

## Qualification results

On 2026-09-03, SQLite 3.53.4 built the 7,245,824-byte database in 312.52 milliseconds. All
five acceptance checks passed:

- approved source provenance matched;
- every imported row count matched;
- all four typed reports exactly matched the JSON reference;
- a runtime write attempt failed;
- the period filter used `idx_opportunities_stage_currency_date`.

Single-run report timings were:

| Report | JSON | SQLite | Parity |
|---|---:|---:|---:|
| Account risk | 49.347 ms | 0.457 ms | Pass |
| Product risk | 52.699 ms | 0.543 ms | Pass |
| Pipeline change | 20.828 ms | 45.135 ms | Pass |
| Support/pipeline overlap | 71.493 ms | 14.621 ms | Pass |

These are qualification observations, not a statistically rigorous performance benchmark.
The pipeline report is slower through SQLite because the current repository deliberately
returns thousands of normalized opportunity records to the existing generic Python analytics
engine. Account and product joins move substantially less data because SQL performs their
grouping. Future optimization can push more pipeline aggregation into the repository without
changing the report contract.

## Run it

Build or validate the database:

```bash
make database
```

Use it for deterministic analysis:

```bash
business-ops-analytics \
  --database data/derived/maple_payments.sqlite3 \
  pipeline-change --top 10
```

Run the parity and safety qualification:

```bash
make qualify-database
```

Machine-specific evidence is written to the ignored
`artifacts/stage6_qualification.json` file.

## Deliberate non-goals

This stage does not expose free-form SQL to the model, import private data, add migrations for
a production service, introduce RAG or embeddings, add MCP, or build a UI. Unstructured files
remain outside SQLite until the later retrieval milestone.
