# Stage 9: Source and analytical-capability catalog

## Objective

Stage 9 gives the analyst one governed answer to four questions:

1. Which data sources are approved?
2. Which business entities and metrics do they contain?
3. Which deterministic analyses may operate on them?
4. What can each analysis legitimately establish?

Earlier stages encoded parts of this information in planner prompts, evidence mappings,
report code, and documentation. The new typed catalog becomes their shared contract without
adding a new source, document retrieval, generated SQL, MCP, or an interface.

## Catalog contents

The `stage-9-v1` catalog contains:

- one authenticated public synthetic Maple Payments source snapshot;
- four business entities: account, opportunity, support ticket, and product part;
- five semantic metric definitions, including ARR at risk, closed-won opportunity ACV, and
  support/pipeline overlap;
- four deterministic read-only analytical capabilities;
- JSON-file and SQLite-table locators for each capability;
- input parameters, returned evidence categories, implementation identities, method versions,
  supported question types, and interpretation boundaries.

The downloaded public archive also contains unstructured files, but Stage 9 does not register
them as an approved usable modality because no retrieval capability exists yet. Presence in an
archive is not execution authority. The agent can use only explicitly registered deterministic
capabilities.

## One definition across the system

The planner and single-tool analyst receive a compact view containing source identity,
classification, capabilities, metrics, parameters, outputs, and limitations. The full catalog
does not expose local filesystem paths.

When a report executes, provenance resolves the method version, implementation identity, and
logical source locators from the same capability definition. The evaluator then checks that:

- every planned and executed analysis exists in the approved catalog;
- each evidence method matches the registered implementation and version;
- each evidence source matches the registered source identity;
- JSON or SQLite evidence locators match the selected access mode.

This removes the prior duplicated provenance dictionaries and prevents planning, execution,
and evidence metadata from silently drifting apart.

## Tamper-evident catalog snapshot

The catalog has a SHA-256 content digest covering all source, entity, metric, and capability
definitions. Pydantic validation rejects altered definitions when the digest is unchanged.
Every `InvestigationState` and portable `AuditBundle` includes the exact catalog snapshot used
for that investigation, and the investigation identifier covers its digest.

This preserves two different audit layers:

- evidence IDs prove which deterministic results support the conclusion;
- the catalog digest proves which governed sources, methods, and semantics were available to
  produce those results.

Inspect the catalog locally with:

```bash
business-ops-catalog --planning-view
business-ops-catalog
```

Both commands print JSON so a future UI or policy service can consume the same contract.

## Evaluation gates

Stage 9 retains all 18 Stage 8 gates and adds:

1. `capability_catalog_integrity` — the embedded catalog definitions reproduce their digest;
2. `catalog_execution_alignment` — plan steps, actions, evidence methods, source identities,
   and source locators agree with the approved catalog.

Unit tests also change a metric boundary without updating the catalog digest and substitute an
unapproved evidence implementation. Both modifications are detected.

## Qualification record

The final Stage 9 run used `mlx-community/Qwen3.8-27B-4bit` through the loopback-only
OpenAI-compatible endpoint on September 4, 2026.

| Scenario | Result | Analyses | Requests | Tokens | Time |
|---|---:|---:|---:|---:|---:|
| Causal attribution | 20/20 gates | 2 | 4 | 12,396 | 132.952 s |
| Support prioritization | 20/20 gates | 2 | 4 | 9,219 | 107.832 s |
| Full suite | 2/2 scenarios | 4 total | 8 | 21,615 | 240.783 s |

Both runs embedded catalog `stage-9-v1` with digest
`sha256:751fe257545d0404576471e4e1a8caa30ad2afc0728f3d28839216d9feaf1836`.
The causal audit bundle validated as `INV-8c4efa932358ed74`; the support bundle validated as
`INV-3fff3da40be2ce27`. Each contained seven cited claims and two evidence records.

The causal controller transparently corrected the business implication, recommendation, and
one unresolved question to remain inside the association-only decision boundary. It did not
alter calculations, evidence, or citations. The support result required no conclusion-policy
correction.

The complete machine-specific evidence is written to the ignored
`artifacts/stage9_qualification.json` file. The documented values above are the public
milestone record.

## Current limitation

The runtime function dispatch remains ordinary application code, intentionally. The catalog
describes and governs capabilities; it does not dynamically import or execute arbitrary code.
Adding a capability still requires reviewed code, tests, an explicit registry entry, and
evaluation coverage.

There is still one source snapshot and no independent-source reconciliation. Stage 10 later
used this catalog seam to add a governed query capability without rewriting planning or evidence
contracts. Document indexing and RAG remain deferred until the structured query boundary is
qualified.
