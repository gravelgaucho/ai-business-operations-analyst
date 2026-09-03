# AI Business Operations Analyst

A local-first AI system designed to investigate business performance questions,
test hypotheses against evidence, and produce decision-ready findings with human
oversight.

This repository currently contains **Stage 0: Local Model Qualification**. It proves
that a capable open model can run privately on Apple silicon behind a standard HTTP
interface before any application framework or data layer is introduced.

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
src/stage0/                 Model-neutral configuration and validation code
tests/                      Fast tests that do not load the model
docs/architecture.md        Design boundary and deliberate non-goals
docs/qualification.md       Hardware, versions, evidence, and measured results
docs/runbook.md             Setup, operation, troubleshooting, and cleanup
```

## Scope boundary

Stage 0 intentionally does **not** include an agent framework, Pydantic AI, MCP, RAG,
business datasets, or a user interface. Those layers should only be added after the
local model contract is proven.

## Safety note

The included development server is for local qualification, not production. It binds
to loopback by default and has no authentication. Do not expose it to a network.
