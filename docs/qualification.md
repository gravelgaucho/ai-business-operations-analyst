# Stage 0 qualification record

Status: **qualified — 5/5 checks passed on 2026-09-03**

## Test machine

- Mac Studio (`Mac16,9`)
- Apple M4 Max, 16 CPU cores
- 128 GB unified memory
- macOS 15.6.1 (arm64)
- Python 3.13.15 isolated in `.venv`

## Candidate

- `mlx-community/Qwen3.8-27B-4bit`
- Converted from `Qwen/Qwen3.8-27B`
- Approximate model download: 16.1 GB
- License: Apache-2.0

## Resolved runtime

- MLX 0.32.2
- MLX-LM 0.31.3
- MLX-VLM 0.6.17
- Transformers 5.16.1

## Required evidence

| Check | Result | Evidence |
|---|---:|---|
| OpenAI-compatible server discovery | Pass | `GET /v1/models` returned the configured model in 0.02 s |
| Basic inference | Pass | Exact `LOCAL MODEL READY` response in 1.82 s |
| Structured JSON | Pass | Strict four-field finding validated in 3.06 s |
| Native tool calling | Pass | Correct function and arguments returned in 2.92 s |
| Multi-turn continuation | Pass | Used supplied `$1,842,500` evidence in 2.77 s |
| Speed | Captured | Warm decode 26.3–28.8 tokens/s; warm prefill 178.7–236.8 tokens/s |
| Peak memory | Captured | 15.697 GiB sampled peak server RSS |

## Interpretation

The server completed all four inference requests in 1.82–3.06 seconds. The basic
request included first-generation warm-up and prefilling at 16.7 tokens/s. Once warm,
prefill reached 178.7–236.8 tokens/s and decode reached 26.3–28.8 tokens/s, as reported
by the server. These are single-request local-development measurements, not a concurrency
or production-throughput benchmark.

Peak memory is the server process's resident-set size sampled every 100 ms through the
full suite. On Apple silicon, RSS is a useful whole-process observation but is not the
same as MLX allocator peak telemetry; the report labels it accordingly.

The ignored local artifact `artifacts/qualification.json` contains the exact responses,
token counts, latencies, package inventory, and timestamp for the run.

## Acceptance conclusion

`mlx-community/Qwen3.8-27B-4bit` qualifies as the Stage 0 baseline on this Mac. It can
serve as the replaceable reasoning engine for the next milestone without introducing an
agent framework, data architecture, or user interface prematurely.

## Source record

- [Official Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [MLX community 4-bit conversion](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit)
- [MLX-LM repository and releases](https://github.com/ml-explore/mlx-lm)
- [MLX-VLM server documentation](https://github.com/Blaizzy/mlx-vlm)
