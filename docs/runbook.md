# Local runbook

## One-time setup

```bash
make setup
cp .env.example .env
```

The environment is stored in `.venv` and ignored by Git. Dependencies are bounded in
`pyproject.toml`; the exact installed versions are captured in each qualification artifact.

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
- Port busy: set matching `PORT` and `BASE_URL` values in `.env`.
- Custom binding: use `SERVER_HOST`; zsh reserves `HOST` for the Mac's hostname.

## Local data and cleanup

Generated evidence in `artifacts/` is ignored. Model weights live in the standard Hugging
Face cache outside this repository. Removing `.venv` is safe and does not remove the model.
No cleanup command is automated because cached weights may be shared with other projects.
