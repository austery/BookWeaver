"""Real any-llm requests against an offline local Anthropic-shaped endpoint (SPEC-024 §12).

These tests pin the library behavior BookWeaver relies on, so an any-llm upgrade that
changes retries, effort passthrough, truncation, or error classes fails here first.
No network beyond 127.0.0.1 and no real credentials are used.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ai.model_profiles import resolve_profile
from ai.ports.provider import (
    OutputTruncatedError,
    ProviderAuthenticationError,
    ProviderUnavailableError,
    RateLimitError,
)
from ai.runtime_factory import RequestUsage, _MeteredProvider

_ERROR_TYPES = {401: "authentication_error", 429: "rate_limit_error", 529: "overloaded_error"}
SOURCE = ["garden", "moon"]


class _FakeAnthropic:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.status = 200
        self.stop_reason = "end_turn"
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                fake.requests.append(json.loads(self.rfile.read(length)))
                if fake.status != 200:
                    self.send_response(fake.status)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    error = {"type": _ERROR_TYPES[fake.status], "message": "synthetic"}
                    self.wfile.write(json.dumps({"type": "error", "error": error}).encode())
                    return
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                for name, data in fake.events():
                    self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def events(self) -> Iterator[tuple[str, dict[str, object]]]:
        start = {
            "id": "msg_offline",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": [],
            "stop_reason": None,
            "usage": {"input_tokens": 120, "output_tokens": 1},
        }
        yield "message_start", {"type": "message_start", "message": start}
        block = {"type": "text", "text": ""}
        yield (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": block},
        )
        for text in ('<segment id="1">花园</segment>\n', '<segment id="2">月亮</segment>'):
            delta = {"type": "text_delta", "text": text}
            yield "content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta}
        yield "content_block_stop", {"type": "content_block_stop", "index": 0}
        delta = {"stop_reason": self.stop_reason}
        yield (
            "message_delta",
            {"type": "message_delta", "delta": delta, "usage": {"output_tokens": 42}},
        )
        yield "message_stop", {"type": "message_stop"}

    def close(self) -> None:
        self._server.shutdown()


@pytest.fixture
def endpoint() -> Iterator[_FakeAnthropic]:
    fake = _FakeAnthropic()
    yield fake
    fake.close()


def _provider(endpoint: _FakeAnthropic, usage: list[RequestUsage]) -> _MeteredProvider:
    return _MeteredProvider(
        resolve_profile("flash", provider="anthropic"),
        "test-only-not-a-secret",
        "segment_tags",
        usage,
        lambda: None,
        timeout_seconds=30,
        api_base=endpoint.base,
    )


def test_request_shape_text_and_usage(endpoint: _FakeAnthropic) -> None:
    usage: list[RequestUsage] = []
    provider = _provider(endpoint, usage)

    assert provider.translate_batch(SOURCE, system_prompt="Translate") == ["花园", "月亮"]
    assert provider.backend == "any_llm"
    [body] = endpoint.requests
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 128_000
    assert body["stream"] is True
    assert body["output_config"] == {"effort": "low"}
    assert "thinking" not in body
    system = body["system"]
    assert isinstance(system, str)
    assert system.startswith("Translate") and "<segment" in system
    assert (usage[0].state, usage[0].input_tokens, usage[0].output_tokens) == (
        "responded",
        120,
        42,
    )


def test_output_cap_stop_is_truncation_not_translation(endpoint: _FakeAnthropic) -> None:
    endpoint.stop_reason = "max_tokens"
    usage: list[RequestUsage] = []

    with pytest.raises(OutputTruncatedError, match="--max-batch-chars"):
        _provider(endpoint, usage).translate_batch(SOURCE, system_prompt="Translate")
    assert len(endpoint.requests) == 1
    assert (usage[0].state, usage[0].output_tokens) == ("truncated", 42)


@pytest.mark.parametrize(
    "status,error",
    [
        (401, ProviderAuthenticationError),
        (429, RateLimitError),
        (529, ProviderUnavailableError),
    ],
)
def test_vendor_failures_are_typed_single_attempts(
    endpoint: _FakeAnthropic, status: int, error: type[Exception]
) -> None:
    endpoint.status = status
    usage: list[RequestUsage] = []

    with pytest.raises(error) as caught:
        _provider(endpoint, usage).translate_batch(SOURCE, system_prompt="Translate")
    assert len(endpoint.requests) == 1
    assert usage[0].state == "failed"
    assert not any(word in str(caught.value) for word in SOURCE)
