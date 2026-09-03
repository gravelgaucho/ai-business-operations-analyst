# Stage 3: deterministic business analytics

Stage 3 deliberately removes the LLM from the calculation path. The model may classify a
question in Stage 2, but these results come from ordinary Python transformations whose
inputs, joins, filters, metric definitions, and outputs can be tested exactly.

## Data boundary

The source-specific adapter reads four Maple Payments object types:

```text
accounts ------+------ opportunities
   |           |
   +-------- tickets -------- product components
```

Generic analytics never depend on those source field names. The adapter converts relevant
records into a normalized `MetricRecord` containing date, entity, segment, and value.

## Implemented calculations

- `calculate_variance`: absolute and percentage movement, with undefined growth from a zero
  baseline represented as `null` rather than infinity.
- `compare_periods`: current versus previous totals and account-level contributors.
- `compare_baseline`: account-level changes, including new and missing accounts.
- `rank_accounts`: deterministic top-N ranking with stable tie-breaking.
- `segment_performance`: grouped values and share of total.
- `analyze_concentration`: top-N share plus Herfindahl concentration index.
- `rank_account_risk`: distinct account ARR exposed to matching open support tickets.
- `rank_product_area_risk`: explicit account → ticket → component join, counting each
  account's ARR once per affected component.

Money is never silently mixed across currencies. Opportunity analysis defaults to USD and
filters currency before aggregation.

## Verified Maple Payments results

Using the pinned Enterprise-Bench archive on 2026-09-03:

- Eight accounts had at least one open P1 ticket, representing **$1,041,000 in distinct
  account ARR**.
- The five highest-ARR affected accounts were Vantara ($432,000), TechFlow Payments
  ($180,000), GlobalCommerce Solutions ($120,000), GlobalMart ($95,000), and PayStream
  International ($85,000).
- Subscription Lifecycle Management ranked first by product-area exposure: **$732,000 ARR
  across three affected accounts and three open priority tickets**.
- Comparing closed-won USD opportunity ACV by target close date, Q1 2026 was $31.175M versus
  $80.7M in Q4 2025, a 61.37% decline. MercadoPay was the largest account-level decline
  contributor at -$2.81M.

The last metric is opportunity ACV grouped by target close date and current final stage. It
is explicitly **not recognized revenue**, and the calculation does not claim causation.

## Why this matters

An LLM should decide which analysis may answer a question; it should not invent the result
of a join or perform important arithmetic from context. Stage 4 will expose selected,
validated analytics as tools while keeping these implementations deterministic.

## Milestone boundary

Stage 3 does not add model tool calling, an agent loop, MCP, RAG, unstructured retrieval,
private data, or UI. The full benchmark runner is also intentionally excluded.
