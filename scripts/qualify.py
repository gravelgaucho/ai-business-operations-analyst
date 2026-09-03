#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psutil

from business_ops.config import Settings
from business_ops.validation import FINDING_SCHEMA, validate_finding

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "qualification.json"


@dataclass
class Check:
    name: str
    passed: bool
    elapsed_seconds: float
    evidence: dict[str, Any]
    error: str | None = None


class PeakMemoryMonitor:
    def __init__(self, port: int) -> None:
        self.port = port
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _server_pids(self) -> set[int]:
        result = subprocess.run(
            ["lsof", "-t", f"-iTCP:{self.port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {int(line) for line in result.stdout.splitlines() if line.isdigit()}

    def _sample(self) -> None:
        while not self._stop.is_set():
            total = 0
            try:
                pids = self._server_pids()
            except OSError:
                pids = set()
            for pid in pids:
                try:
                    proc = psutil.Process(pid)
                    total += proc.memory_info().rss
                    total += sum(c.memory_info().rss for c in proc.children(recursive=True))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self.peak_bytes = max(self.peak_bytes, total)
            self._stop.wait(0.1)

    def __enter__(self) -> PeakMemoryMonitor:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


def timed_check(name: str, operation: Callable[[], dict[str, Any]]) -> Check:
    started = time.perf_counter()
    try:
        evidence = operation()
        return Check(name, True, time.perf_counter() - started, evidence)
    except Exception as exc:  # each check must leave evidence even if another fails
        return Check(name, False, time.perf_counter() - started, {}, f"{type(exc).__name__}: {exc}")


def response_json(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError("server response was not a JSON object")
    return value


def message_from(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["choices"][0]["message"]


def usage_from(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("usage", {})


def main() -> int:
    settings = Settings.from_environment()
    port = int(settings.base_url.rsplit(":", 1)[-1].split("/", 1)[0])
    client = httpx.Client(timeout=settings.timeout_seconds)
    endpoint = f"{settings.base_url}/chat/completions"
    checks: list[Check] = []

    checks.append(timed_check("server_ready", lambda: {
        "models": response_json(client.get(f"{settings.base_url}/models")).get("data", [])
    }))

    def basic() -> dict[str, Any]:
        payload = response_json(client.post(endpoint, json={
            "model": settings.model_id,
            "messages": [{"role": "user", "content": "Reply with exactly: LOCAL MODEL READY"}],
            "temperature": 0,
            "max_tokens": 32,
        }))
        content = message_from(payload).get("content", "")
        if "LOCAL MODEL READY" not in content.upper():
            raise AssertionError(f"unexpected answer: {content!r}")
        return {"content": content, "usage": usage_from(payload)}

    with PeakMemoryMonitor(port) as memory:
        checks.append(timed_check("basic_inference", basic))

        def structured() -> dict[str, Any]:
            payload = response_json(client.post(endpoint, json={
                "model": settings.model_id,
                "messages": [{"role": "user", "content": (
                    "Report this business fact: Northeast revenue fell 12.5 percent. "
                    "Use high confidence."
                )}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "business_finding",
                        "strict": True,
                        "schema": FINDING_SCHEMA,
                    },
                },
                "temperature": 0,
                "max_tokens": 256,
            }))
            content = message_from(payload)["content"]
            parsed = json.loads(content)
            errors = validate_finding(parsed)
            if errors:
                raise AssertionError("; ".join(errors))
            return {"parsed": parsed, "usage": usage_from(payload)}

        checks.append(timed_check("structured_json", structured))

        tool_messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": "Use the available tool to get Acme Corp's Q2 revenue. Do not guess.",
        }]
        tools = [{
            "type": "function",
            "function": {
                "name": "lookup_account_metrics",
                "description": "Look up verified account metrics for a fiscal quarter.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account": {"type": "string"},
                        "quarter": {"type": "string"},
                    },
                    "required": ["account", "quarter"],
                    "additionalProperties": False,
                },
            },
        }]
        captured_call: dict[str, Any] = {}

        def tool_call() -> dict[str, Any]:
            payload = response_json(client.post(endpoint, json={
                "model": settings.model_id,
                "messages": tool_messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": 256,
            }))
            message = message_from(payload)
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content")
                raise AssertionError(f"no native tool_calls returned; content={content!r}")
            call = calls[0]
            if call["function"]["name"] != "lookup_account_metrics":
                raise AssertionError(f"unexpected tool: {call['function']['name']}")
            arguments = json.loads(call["function"]["arguments"])
            if "acme" not in arguments.get("account", "").lower():
                raise AssertionError(f"unexpected arguments: {arguments}")
            captured_call.update(call)
            tool_messages.append({
                "role": "assistant",
                "content": message.get("content") or " ",
                "tool_calls": calls,
            })
            return {"tool_call": call, "usage": usage_from(payload)}

        checks.append(timed_check("native_tool_call", tool_call))

        def continuation() -> dict[str, Any]:
            if not captured_call:
                raise RuntimeError("native tool-call check did not produce a call")
            tool_messages.append({
                "role": "tool",
                "tool_call_id": captured_call["id"],
                "name": captured_call["function"]["name"],
                "content": json.dumps({
                    "account": "Acme Corp",
                    "quarter": "Q2",
                    "revenue_usd": 1842500,
                    "source": "verified_finance_warehouse",
                }),
            })
            payload = response_json(client.post(endpoint, json={
                "model": settings.model_id,
                "messages": tool_messages,
                "tools": tools,
                "temperature": 0,
                "max_tokens": 256,
            }))
            content = message_from(payload).get("content", "")
            normalized = content.replace(",", "").replace("$", "")
            if not any(value in normalized for value in ("1842500", "1.8425", "1.84")):
                raise AssertionError(f"answer did not use tool evidence: {content!r}")
            return {"content": content, "usage": usage_from(payload)}

        checks.append(timed_check("multi_turn_tool_continuation", continuation))

    version_output = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    report = {
        "stage": 0,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": settings.model_id,
        "base_url": settings.base_url,
        "system": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "machine": platform.machine(),
        },
        "checks": [asdict(check) for check in checks],
        "summary": {
            "passed": sum(check.passed for check in checks),
            "total": len(checks),
            "peak_server_rss_bytes": memory.peak_bytes,
            "peak_server_rss_gib": round(memory.peak_bytes / (1024**3), 3),
            "note": (
                "Peak RSS is sampled process resident memory, including child processes; "
                "it is not MLX allocator telemetry."
            ),
        },
        "packages": version_output,
    }
    ARTIFACT.parent.mkdir(exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    for check in checks:
        state = "PASS" if check.passed else "FAIL"
        print(f"{state:4} {check.name:30} {check.elapsed_seconds:8.2f}s")
        if check.error:
            print(f"     {check.error}")
    print(f"Evidence: {ARTIFACT}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
