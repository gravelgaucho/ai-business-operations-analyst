# Local runbook

## One-time setup

```bash
make setup
cp .env.example .env
make data
```

The environment is stored in `.venv` and ignored by Git. Dependencies are bounded in
`pyproject.toml`; the exact installed versions are captured in each qualification artifact.
The downloaded Maple Payments corpus is stored in `data/enterprise_bench`, verified against
its pinned checksum, and ignored by Git.

## Start and stop

Start the local server in its own terminal:

```bash
make server
```

The first run downloads the model. A ready server listens only at `127.0.0.1:8080`.
Stop it with Control-C.

Run qualification from another terminal:

```bash
make qualify
```

Ask a business question through the Stage 1 Python client:

```bash
business-ops "Revenue fell 12% while customer count stayed flat. What should we investigate?"
```

Convert a question into the Stage 2 validated type:

```bash
business-ops-classify "Why did Northeast revenue decline last quarter?"
```

The command prints JSON only, so a later application can consume it directly. The local
model receives a native JSON Schema derived from `BusinessQuestion`. Invalid output is
returned to the model for correction up to two times before the command fails clearly.

Run deterministic Stage 3 analysis without starting the model server:

```bash
business-ops-analytics account-risk
business-ops-analytics product-risk --top 5
business-ops-analytics pipeline-change --top 5
make qualify-analytics
```

`account-risk` ranks distinct account ARR exposed to matching open tickets. `product-risk`
joins accounts, tickets, and product components. `pipeline-change` compares opportunity ACV
by target close date; its output explicitly warns that this is not recognized revenue.

Run a Stage 4 single-tool question:

```bash
business-ops-analyze "Which five accounts have the most ARR exposed to open P1 tickets?"
make qualify-tools
```

Run the Stage 5 controlled multi-analysis investigation:

```bash
business-ops-investigate \
  "Did open P1 support issues explain the Q1 2026 closed-won USD ACV decline versus Q4 2025?"
make qualify-investigation
```

The investigation prints its plan, model-selected decisions, deterministic observations,
stop reason, typed conclusion, and usage as JSON. On the qualified 27B baseline, allow about
three minutes for this multi-request workflow.

Inspect both sides of the API boundary:

```bash
business-ops "Analyze the revenue change" --show-request --raw
```

`--temperature`, `--max-tokens`, `--system`, `--model`, and `--base-url` make the
important protocol controls visible without changing source code.

Run fast repository checks without loading the model:

```bash
make lint
make test
```

## Change the baseline without changing code

Edit `.env`:

```text
MODEL_ID=another-org/another-mlx-model
BASE_URL=http://127.0.0.1:8080/v1
```

Restart the server and rerun qualification. A replacement is not accepted merely because
it answers prompts; it must pass the full tool and structure contract.

## Troubleshooting

- `Connection refused`: keep the server terminal running and wait for model loading.
- First start seems idle: confirm disk/network activity; the model is about 16.1 GB.
- Out of memory: stop other large ML workloads and reduce `MAX_KV_SIZE` in `.env`.
- Tool continuation fails: keep assistant tool-call `content` as a string; the qualification
  harness already applies this compatibility guard.
- Classification fails after retries: rerun once, then inspect the schema and server log;
  the command never returns an unvalidated partial object.
- Investigation fails an evidence or causal gate: inspect the validation feedback rather
  than weakening the gate. The controller will not publish an under-evidenced conclusion.
- Dataset missing: run `make data`. The importer will not overwrite an existing directory
  whose source marker is absent or does not match the pinned release.
- Port busy: set matching `PORT` and `BASE_URL` values in `.env`.
- Custom binding: use `SERVER_HOST`; zsh reserves `HOST` for the Mac's hostname.

## Local data and cleanup

Generated evidence in `artifacts/` is ignored. Model weights live in the standard Hugging
Face cache outside this repository. Removing `.venv` is safe and does not remove the model.
No cleanup command is automated because cached weights may be shared with other projects.
