# Stage 12: Unified Business Evidence Testbed foundation

## Objective

Stage 12 turns the project's business-data concern into a versioned, executable coverage
contract. It answers four different questions without conflating them:

1. What data exists in the authenticated Maple Payments snapshot?
2. What data is currently exposed through governed analytical capabilities?
3. What existing data has not yet been onboarded?
4. What data is genuinely absent and must be supplied by a safe synthetic extension?

This milestone does not manufacture finance records, expose roadmap data to the model, or claim
that the flagship financial investigation is supported. It defines and verifies the foundation
on which those records can be built.

## Why the product does not need one giant table

The target product must reconcile evidence across CRM, support, product, contract, finance,
billing, and document systems. Those records should retain their source identity and native
semantic boundaries. A canonical entity spine supplies stable relationships; it does not erase
provenance by flattening every source into one table.

```text
CRM + support + product + documents       Finance/operations extension
                  |                                  |
                  +-----------+----------------------+
                              |
                  canonical entities and joins
                              |
                   governed metrics/capabilities
                              |
                  evidence ledger and conclusions
```

The current capability catalog remains the authority for execution. The testbed specification
is a coverage and roadmap contract. An asset marked `available_not_onboarded` or
`planned_extension` cannot be selected by the investigation agent.

## Verified source inventory

The deterministic Stage 12 inventory reauthenticates the pinned Enterprise-Bench snapshot before
reading any source asset. It found 50,411 manifest or structured records across 12 existing
assets:

| Coverage state | Asset | Records | Current meaning |
|---|---|---:|---|
| Active | CRM accounts | 42 | Queryable through approved reports |
| Active | CRM opportunities | 8,704 | Queryable as opportunity ACV, not revenue |
| Active | Support tickets | 32,768 | Queryable through approved support reports |
| Active | Product parts | 40 | Used in support/product joins |
| Active | Internal-document manifest | 8 / 7 published | Seven published files searchable |
| Available | CRM users | 289 | Present but not exposed |
| Available | Product-management users | 5 | Present but not exposed |
| Available | Product issues | 8,448 | Present but not exposed |
| Available | Product conversations | 23 | Present but not exposed |
| Available | Product comments | 26 | Present but not exposed |
| Available | Knowledge articles | 55 | Present but not exposed |
| Available | Account transcripts | 3 | Present but not exposed |

The specification also registers nine planned finance and operations assets. They are absent by
design and are machine-reported with `present: false`:

- account-specific contract assignments;
- bookings and order lines;
- subscriptions;
- invoices;
- revenue schedules;
- payments and collections;
- implementation milestones;
- product usage;
- attributed cost records.

This distinction is a governance control. A missing finance asset cannot be mistaken for an empty
result or silently inferred from opportunity ACV.

## Canonical business entity spine

The versioned testbed defines 19 canonical entities. Existing identifiers are preserved rather
than replaced with invented cross-system keys.

| State | Entities |
|---|---|
| Active | account, opportunity, support ticket, product part, internal document |
| Available to onboard | person, product issue, conversation, knowledge article, transcript |
| Planned extension | executed contract, booking, subscription, invoice, revenue event, payment, implementation milestone, usage event, cost record |

The first verified relationships are account-to-opportunity, account-to-ticket, and
ticket-to-product-part. Maple also supplies usable but not-yet-onboarded product-issue/component
and transcript/account/opportunity links. The financial extension will complete the commercial
chain:

```text
account
  -> opportunity
  -> executed contract
  -> booking / order line
  -> subscription
  -> invoice
  -> revenue event
  -> payment
```

Implementation milestones link back to bookings; usage and cost records link to accounts and
products. Each relationship retains an interpretation boundary. For example, an invoice is not
recognized revenue, and a payment is not either.

## Metric completeness

All 11 declared integrity checks passed with zero unresolved references. They cover account links
from opportunities, tickets, and transcripts; product-component links from tickets and issues;
conversation links from tickets, issues, and comments; transcript opportunity links; conversation
parents; and person references across both user directories.

The testbed currently classifies 14 business evidence requirements:

| State | Metrics or evidence |
|---|---|
| Active | account ARR, closed-won opportunity ACV, support exposure, published document evidence |
| Available to onboard | product-issue backlog, transcript evidence, knowledge-base evidence |
| Planned extension | bookings, recognized revenue, billing and collections, price and discount, implementation timing, product adoption, gross margin |

The semantic definitions explicitly separate:

- opportunity ACV from bookings;
- bookings from billings;
- billings from recognized revenue;
- recognized revenue from cash;
- price from volume and product mix;
- operational timing from accounting treatment;
- attributed cost from an unexplained margin calculation.

These definitions are prerequisites for a credible management conclusion, not presentation
details to add later.

## Financial and operations extension contract

The next data implementation should be deterministic, synthetic, reproducible from a fixed seed,
and connected only to existing synthetic Maple identifiers. Every file must be versioned and
hashed. Currency amounts should use integer minor units or another exact decimal representation;
currency and business dates must always be explicit.

Minimum required fields are:

| Asset | Required business fields |
|---|---|
| Contract assignment | contract, account, opportunity, governing document/version, tier, effective/end dates, amendments |
| Booking line | booking, account, opportunity, contract, product, signed date, quantity, list price, contracted price, discount, currency, term |
| Subscription | subscription, booking, account, product, service dates, activation date, billing cadence, status |
| Invoice | invoice, subscription, account, invoice/due dates, service period, amount, currency, status |
| Revenue event | event, booking/subscription/invoice/account, recognition period, amount, currency, policy identifier |
| Payment | payment, invoice, account, timestamp, amount, currency, status, event type |
| Implementation milestone | milestone, booking, account, planned/actual dates, status, delay category |
| Product usage | observation, account, product, period, governed adoption measures |
| Cost record | record, account/product, period, cost type, amount, currency, allocation method |

Acceptance must enforce primary-key uniqueness, foreign-key integrity, date ordering, explicit
currency, nonnegative values where applicable, controlled status vocabularies, and reconciliation
rules between line totals and their summaries. Exceptions and reversals must be represented as
typed events rather than unexplained negative numbers.

## Evaluation-world design

The extension must behave like a controlled business simulation, not a spreadsheet constructed to
make the agent look correct. Its generator and validator should create:

- multiple periods and business segments;
- price, volume, product-mix, timing, and implementation effects;
- a small number of known material drivers;
- plausible distractor correlations;
- missing and late-arriving records;
- amendments and conflicting document versions;
- currency and fiscal-period edge cases;
- negative controls where a popular hypothesis is false;
- scenarios whose correct result is explicitly inconclusive.

A separate evaluation manifest will record expected facts, required evidence, permitted
inferences, planted distractors, and known limitations. That manifest must never enter model
context. The public repository can include transparent example cases; future robustness tests may
use withheld parameter combinations generated from the same published contract.

## Flagship scenario readiness

Readiness is derived from required metric coverage rather than manually claimed:

| Scenario | Readiness | Reason |
|---|---|---|
| Support/pipeline causal screen | Qualified | All required metrics are active |
| Document-grounded support review | Qualified | Structured and cited-document evidence active |
| Product-issue/customer-impact analysis | Partial | Product issues exist but are not onboarded |
| Bookings up, revenue flat | Blocked on planned data | Bookings, revenue, pricing, and implementation data absent |
| Transaction/contract/pricing review | Blocked on planned data | Order, invoice, price, and contract assignment chain incomplete |

## Phased implementation plan

The smallest credible sequence is:

1. **Stage 12 — coverage contract:** completed here; no new evidence authority.
2. **Stage 13 — existing-source expansion:** onboard product issues first, then knowledge articles
   and transcripts, with new cross-source evaluation cases.
3. **Stage 14 — commercial-chain seed:** generate and verify contract assignments, bookings,
   subscriptions, invoices, and revenue schedules for the flagship finance question.
4. **Stage 15 — operational-driver expansion:** add implementation, usage, payments, and cost
   records only as required by evaluated questions.
5. **Stage 16 — analytical methods:** expose governed variance decomposition, mix analysis,
   cohorts, unit economics, and scenarios over the validated commercial chain.

This order uses existing safe data before generating more, proves the minimum finance chain before
adding every operational source, and keeps each new data asset behind a reviewed capability.

## Qualification

The accepted local inventory used testbed `stage-12-v1` with digest
`sha256:ad96e291eaf9d428e4017dda36f5bd73f2d02dad204072c17d6a3ff2adb9c4d8`.
All nine qualification checks passed:

- the approved snapshot and every file digest were verified;
- all 12 existing asset counts matched the pinned source;
- all 21 assets belonged to exactly one coverage state;
- all 11 cross-source integrity checks resolved with zero orphans;
- all active primary locators were registered by current capabilities;
- all planned locators were absent from executable capabilities;
- the two current scenarios remained qualified;
- the product-issue scenario remained explicitly partial;
- the two finance scenarios remained explicitly blocked.

All 114 fast repository tests also passed without loading the model.

Run the inventory and acceptance checks without starting the model server:

```bash
make testbed
make qualify-testbed
```

## Current boundary

Stage 12 adds no finance records, new model tools, database tables, document access, embeddings,
arbitrary SQL, generated Python, or UI. The local model sees the unchanged Stage 11 capability
catalog. This milestone makes the data roadmap executable and auditable; it does not present the
roadmap as product functionality.
