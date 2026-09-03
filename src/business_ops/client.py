from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from business_ops.config import Settings

Message = dict[str, Any]


class ModelServerError(RuntimeError):
    """A stable application error for transport, protocol, and server failures."""


@dataclass(frozen=True)
class ModelResponse:
    content: str
    model: str
    finish_reason: str | None
    usage: dict[str, Any]
    raw: dict[str, Any]


class ModelServerClient:
    """Small client for the OpenAI-compatible Chat Completions boundary."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or Settings.from_environment()
        self._client = httpx.Client(
            timeout=self.settings.timeout_seconds,
            transport=transport,
            headers={"Content-Type": "application/json"},
        )

    def __enter__(self) -> ModelServerClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/models")
        models = payload.get("data")
        if not isinstance(models, list):
            raise ModelServerError("Model server response is missing the 'data' list.")
        return models

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> ModelResponse:
        if not messages:
            raise ValueError("At least one message is required.")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2.")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive.")

        payload = self._request(
            "POST",
            "/chat/completions",
            json={
                "model": self.settings.model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelServerError("Model server returned an unexpected response shape.") from exc
        if not isinstance(content, str):
            raise ModelServerError("Model server returned non-text content.")
        usage = payload.get("usage", {})
        return ModelResponse(
            content=content,
            model=str(payload.get("model", self.settings.model_id)),
            finish_reason=choice.get("finish_reason"),
            usage=usage if isinstance(usage, dict) else {},
            raw=payload,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        try:
            response = self._client.request(method, url, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except httpx.ConnectError as exc:
            raise ModelServerError(
                f"Cannot reach the local model server at {self.settings.base_url}. "
                "Start it with 'make server'."
            ) from exc
        except httpx.TimeoutException as exc:
            timeout = self.settings.timeout_seconds
            raise ModelServerError(f"Model request timed out after {timeout}s.") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ModelServerError(
                f"Model server returned HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except ValueError as exc:
            raise ModelServerError("Model server returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ModelServerError("Model server response was not a JSON object.")
        return payload
