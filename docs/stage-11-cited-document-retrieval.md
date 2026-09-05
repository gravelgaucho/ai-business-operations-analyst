# Stage 11: Cited document retrieval

## Objective

Stage 11 lets the analyst use unstructured internal evidence while preserving the same governed,
auditable architecture as structured analysis. It proves one cross-modal behavior:

> Rank accounts with current open P1 support exposure, retrieve the published Standard MSA's P1
> response terms, and produce a management recommendation grounded in both evidence types.

This is a document-retrieval subsystem, not a conversion of the product into a RAG pipeline.

## Governed corpus

The approved synthetic Maple Payments snapshot contains 8 internal manifest entries. Stage 11
indexes only the 7 marked `published`; the draft MSA is excluded. The manifest itself and the
seven published Markdown files are registered in catalog `stage-11-v1`.

Ingestion enforces:

- the already-pinned source commit and archive checksum;
- a typed manifest with unique document IDs and filenames;
- `published`, `internal`, and `markdown` metadata;
- one local `.md` filename with no traversal or subdirectory components;
- resolution inside the approved `internal_docs` directory;
- no symbolic links and a per-document size limit;
- no directory crawling or implicit trust based on file presence.

The draft, standalone `CANARY.md`, knowledge-base articles, transcripts, and any unlisted files
are outside this capability. The source is publicly available synthetic benchmark data even
when a fictional document labels itself internal or confidential.

## Retrieval and citations

HTML comments are removed while retaining their newline count. This prevents benchmark canary
comments from entering model context without shifting source lines. Markdown is split at heading
boundaries and capped at 2,400 characters per passage. A dependency-free deterministic BM25
implementation ranks title-, section-, and passage-level terms.

`DocumentSearchQuery` accepts a plain-text query of 3–500 characters and a `top_k` of 1–8. It
accepts no paths, patterns, filters, SQL, code, or retrieval instructions.

Every result provides:

- document ID, title, published status, and modified timestamp;
- logical repository-relative file locator;
- section name and exact inclusive line range;
- complete bounded excerpt;
- SHA-256 digest of that exact excerpt;
- deterministic lexical relevance score.

Pydantic validation recomputes each excerpt digest. The evidence record then adds a second hash
over the complete result and derives a stable evidence ID from its source, method, arguments,
and result. A future reviewer can follow a claim to its evidence record and from there to the
exact source lines.

## Untrusted-content boundary

Document text is always evidence, never instruction. The direct analyst, next-step selector,
and synthesizer are all told not to follow imperative text inside a retrieved passage. Retrieval
cannot add tools, change the investigation plan, access another path, invoke code, or modify
data. The controller supplies the original user question as the exact search string so a model
reformulation cannot silently change what was searched.

Lexical relevance is not authority or applicability. A template may not govern a particular
customer, amendments may exist, and publication status does not prove correctness. The result
and final conclusion must retain that interpretation boundary and require human review for a
consequential contractual decision.

## Cross-modal evaluation

The fourth public scenario requires exactly:

1. `get_account_support_risk` for the deterministic current P1 exposure ranking;
2. `search_internal_documents` for the cited published Standard MSA passage.

Its deterministic anchors include 8 affected accounts, $1,041,000 of distinct ARR exposure,
document `MSA-005`, section `3.2 Response & Resolution Targets`, and the exact passage hash. The
passage states a 1-hour initial response, 24-hour resolution target, and 24/7 coverage for P1.

Stage 11 retains the 22 Stage 10 gates and adds:

- `document_retrieval_contract` — action arguments, evidenced query, and row bound agree;
- `document_citation_integrity` — citations are published, cataloged, line-addressable,
  correctly hashed, and free of stripped canary content.
- `evidence_content_scope` — material numbers and sensitive business consequences must already
  appear in the exact evidence records cited by the claim; synthesis cannot borrow a matching
  number from unrelated evidence, invent arithmetic, or hide arithmetic behind concentration or
  aggregation language;
- `document_applicability_restraint` — template terms remain conditional on human verification
  of the applicable executed agreement or service tier, and confidence is calibrated to the
  missing account-to-agreement mapping.

The milestone requires all four public scenarios to pass all 26 gates with the local baseline.

## Accepted qualification

The accepted September 4, 2026 local run used `mlx-community/Qwen3.8-27B-4bit` and passed every
scenario at 26/26 gates:

| Scenario | Time | Requests | Tokens | Tool calls |
|---|---:|---:|---:|---:|
| Causal attribution | 144.997 s | 5 | 15,224 | 2 |
| Support prioritization | 139.073 s | 6 | 14,850 | 2 |
| Governed opportunity analysis | 129.295 s | 5 | 14,584 | 2 |
| Document-grounded support review | 151.752 s | 5 | 16,629 | 2 |
| **Total** | **565.117 s** | **21** | **61,287** | **8** |

The catalog digest was
`sha256:78e89be13639ca185a2897c8633698645b9f42a50eac8210923e80c1ddf318e4`.
The final document case cited evidence records `EV-25f9165fcbec78c3` and
`EV-405938f24afb2fc8`. It reported the Standard MSA terms, required account-specific agreement
or tier verification, and ended with low confidence and limited data quality because that mapping
is absent. All 108 fast tests passed without loading the model.

The live qualification was deliberately not accepted on automated scores alone. Manual review
of intermediate outputs found an invented `$612,000` subtotal, a number that accidentally matched
unrelated evidence, implicit majority and collective-total calculations, unconditional template
language, contract language in runs with no document evidence, and overconfident applicability.
Those failures became plan guards, claim-to-citation scope checks, deterministic correction rules,
confidence calibration, and regression tests. Corrections are recorded in investigation state;
evidence records, calculations, citations, and hashes are never rewritten.

The 565-second result is a framework qualification measurement, not a product-latency target.
The local baseline satisfies the governed behavior contract, but its planning and structured-output
repair cost remains a measured reason to benchmark stronger or faster replacement models later.

## Current limitation

Only the internal-document manifest is searchable. There are no embeddings, semantic reranker,
vector database, OCR, PDF parser, transcript index, knowledge-base index, access-control service,
document version reconciliation, or independent source. BM25 lexical retrieval is sufficient
for this precise first benchmark but is not assumed to be sufficient for the eventual product.

The next retrieval expansion should be driven by evaluation failures, not by adding infrastructure
for its own sake.
