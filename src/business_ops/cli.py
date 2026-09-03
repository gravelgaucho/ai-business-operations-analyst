from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from business_ops.client import ModelServerClient, ModelServerError
from business_ops.config import Settings

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful business operations analyst. Distinguish facts from assumptions, "
    "state what evidence is missing, and keep the response concise."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-ops",
        description="Send a business question directly to an OpenAI-compatible model server.",
    )
    parser.add_argument("question", help="The business question to analyze.")
    parser.add_argument("--system", default=DEFAULT_SYSTEM_PROMPT, help="System-role instruction.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument(
        "--raw", action="store_true", help="Print the complete JSON response envelope."
    )
    parser.add_argument(
        "--show-request", action="store_true", help="Print the outgoing JSON request."
    )
    parser.add_argument("--model", help="Override MODEL_ID for this request.")
    parser.add_argument("--base-url", help="Override BASE_URL for this request.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    defaults = Settings.from_environment()
    settings = Settings(
        model_id=args.model or defaults.model_id,
        base_url=(args.base_url or defaults.base_url).rstrip("/"),
        timeout_seconds=defaults.timeout_seconds,
    )
    messages = [
        {"role": "system", "content": args.system},
        {"role": "user", "content": args.question},
    ]
    request = {
        "model": settings.model_id,
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    if args.show_request:
        print("REQUEST")
        print(json.dumps(request, indent=2))
        print("\nRESPONSE")
    try:
        with ModelServerClient(settings) as client:
            response = client.chat(
                messages,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
    except (ModelServerError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.raw:
        print(json.dumps(response.raw, indent=2, ensure_ascii=False))
    else:
        print(response.content)
        if response.usage:
            prompt_tokens = response.usage.get("prompt_tokens", "?")
            completion_tokens = response.usage.get("completion_tokens", "?")
            print(
                f"\n[{response.model} · "
                f"{prompt_tokens} input / {completion_tokens} output tokens]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
