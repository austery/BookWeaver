"""Authorization rejects before constructing a metered client."""

import sys
import json
from pathlib import Path

import pytest

from ai.model_profiles import resolve_profile
from ai.runtime_factory import DefaultProviderFactory, PaidAuthorizationError


def test_config_cannot_authorize_paid_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(PaidAuthorizationError, match="non-interactive"):
        DefaultProviderFactory().create(
            resolve_profile(provider="api"),
            protocol="segment_tags",
            config={"allow_paid_api": True},
            allow_paid_api=False,
            remaining_chars=100,
        )


def test_paid_flag_is_invalid_for_subscription_provider() -> None:
    with pytest.raises(PaidAuthorizationError, match="requires"):
        DefaultProviderFactory().create(
            resolve_profile(),
            protocol="segment_tags",
            config={},
            allow_paid_api=True,
            remaining_chars=100,
        )


def test_authorized_api_failure_is_one_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from google import genai
    from google.genai import types
    from ai.ports.provider import ProviderUnavailableError

    calls: list[str] = []

    class Models:
        def generate_content(
            self, *, model: str, contents: str, config: types.GenerateContentConfig
        ) -> None:
            assert config.http_options is not None
            assert config.http_options.retry_options is not None
            assert config.http_options.retry_options.attempts == 1
            calls.append(model)
            raise RuntimeError("network unavailable")

    class Client:
        def __init__(self, *, api_key: str, http_options: types.HttpOptions) -> None:
            assert http_options.retry_options is not None
            assert http_options.retry_options.attempts == 1
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-secret")
    factory = DefaultProviderFactory(audit_directory=tmp_path)
    provider = factory.create(
        resolve_profile(provider="api"),
        protocol="segment_tags",
        config={},
        allow_paid_api=True,
        remaining_chars=100,
    )
    with pytest.raises(ProviderUnavailableError):
        provider.translate_batch(["one", "two"], system_prompt="Translate")
    assert calls == ["gemini-2.5-flash"]
    assert factory.usage_snapshot()[1] == {
        "request_count": 1,
        "input_tokens": None,
        "output_tokens": None,
    }
    audit = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert audit["requests"] == [
        {
            "model": "gemini-2.5-flash",
            "protocol": "segment_tags",
            "state": "failed",
            "input_tokens": None,
            "output_tokens": None,
        }
    ]
