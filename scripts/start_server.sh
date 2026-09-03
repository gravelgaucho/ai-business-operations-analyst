#!/bin/zsh
set -euo pipefail

project_dir="${0:A:h:h}"
if [[ -f "$project_dir/.env" ]]; then
  set -a
  source "$project_dir/.env"
  set +a
fi

model_id="${MODEL_ID:-mlx-community/Qwen3.8-27B-4bit}"
server_host="${SERVER_HOST:-127.0.0.1}"
port="${PORT:-8080}"
max_kv_size="${MAX_KV_SIZE:-32768}"

exec "$project_dir/.venv/bin/python" -m mlx_vlm.server \
  --model "$model_id" \
  --host "$server_host" \
  --port "$port" \
  --max-kv-size "$max_kv_size"
