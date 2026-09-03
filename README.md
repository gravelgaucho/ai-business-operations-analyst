# AI Business Operations Analyst

A local-first AI system designed to investigate business performance questions,
test hypotheses against evidence, and produce decision-ready findings with human
oversight.

## Progress

| Milestone | Status | Proof |
|---|---:|---|
| Stage 0 — local inference | Complete | Tagged `stage-0` |
| Stage 1 — Python model client | Complete | Tagged `v0.2-python-client` |
| Stage 2 — typed business questions | Next | Not started |

This repository contains two completed foundations:

- **Stage 0 — Local Model Qualification:** prove a capable open model runs privately on
  Apple silicon behind a standard HTTP interface.
- **Stage 1 — Model Boundary:** send, inspect, validate, and handle those HTTP requests
  in our own Python application before introducing an agent framework.

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

## Reproduce it

Requirements: Apple silicon, Homebrew Python 3.13, and roughly 20 GB of free disk
space for packages plus the model cache.

```bash
make setup
cp .env.example .env
make server
```

In a second terminal:

```bash
business-ops "Revenue fell while customer count stayed flat. What should we investigate?"
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
src/business_ops/client.py  Model-neutral OpenAI-compatible Python client
src/business_ops/cli.py     Inspectable business-question command line
tests/                      Fast tests that do not load the model
docs/architecture.md        Design boundary and deliberate non-goals
docs/qualification.md       Hardware, versions, evidence, and measured results
docs/stage-1-model-boundary.md  Request/response learning walkthrough
docs/runbook.md             Setup, operation, troubleshooting, and cleanup
```

## Scope boundary

Stages 0–1 intentionally do **not** include an agent framework, Pydantic AI, MCP, RAG,
business datasets, or a user interface. Those layers should only be added after the
local model contract is understood and proven.

## Safety note

The included development server is for local qualification, not production. It binds
to loopback by default and has no authentication. Do not expose it to a network.
