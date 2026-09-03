from __future__ import annotations

import json

import httpx
import pytest

from business_ops.client import ModelServerClient, ModelServerError
from business_ops.config import Settings


def settings() -> Settings:
    return Settings(model_id="test-model", base_url="http://model.test/v1", timeout_seconds=1)


def test_chat_sends_openai_compatible_request_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "test-model",
            "choices": [{
                "message": {"role": "assistant", "content": "Revenue declined."},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        })

    with ModelServerClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.chat(
            [{"role": "user", "content": "Analyze revenue."}],
            temperature=0.2,
            max_tokens=100,
        )

    assert captured == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Analyze revenue."}],
        "temperature": 0.2,
        "max_tokens": 100,
    }
    assert result.content == "Revenue declined."
    assert result.finish_reason == "stop"
    assert result.usage["total_tokens"] == 15


def test_list_models_parses_discovery_response() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"object": "list", "data": [{"id": "test-model"}]})
    )
    with ModelServerClient(settings(), transport=transport) as client:
        assert client.list_models() == [{"id": "test-model"}]


def test_http_error_becomes_stable_application_error() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(503, text="model is still loading")
    )
    with (
        ModelServerClient(settings(), transport=transport) as client,
        pytest.raises(ModelServerError, match="HTTP 503"),
    ):
        client.chat([{"role": "user", "content": "Hello"}])


def test_connection_error_explains_how_to_start_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with (
        ModelServerClient(settings(), transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ModelServerError, match="Start it with 'make server'"),
    ):
        client.chat([{"role": "user", "content": "Hello"}])


def test_invalid_json_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not-json"))
    with (
        ModelServerClient(settings(), transport=transport) as client,
        pytest.raises(ModelServerError, match="invalid JSON"),
    ):
        client.chat([{"role": "user", "content": "Hello"}])


def test_unexpected_response_shape_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []}))
    with (
        ModelServerClient(settings(), transport=transport) as client,
        pytest.raises(ModelServerError, match="unexpected response shape"),
    ):
        client.chat([{"role": "user", "content": "Hello"}])


@pytest.mark.parametrize(
    ("temperature", "max_tokens", "message"),
    [(-0.1, 10, "temperature"), (2.1, 10, "temperature"), (0.0, 0, "max_tokens")],
)
def test_invalid_generation_controls_fail_before_request(
    temperature: float, max_tokens: int, message: str
) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called")

    with (
        ModelServerClient(settings(), transport=httpx.MockTransport(unexpected)) as client,
        pytest.raises(ValueError, match=message),
    ):
        client.chat(
            [{"role": "user", "content": "Hello"}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
