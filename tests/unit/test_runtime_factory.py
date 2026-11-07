"""Authorization rejects before constructing a metered client."""

import sys
import json
from pathlib import Path

import pytest

from ai.model_profiles import resolve_profile
from ai.runtime_config import validate_config
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


@pytest.mark.parametrize("provider", ["cli", "api"])
def test_audit_distinguishes_unavailable_usage_from_zero_paid_work(
    tmp_path: Path, provider: str
) -> None:
    factory = DefaultProviderFactory(audit_directory=tmp_path)
    factory.persist_audit({"provider": provider, "runtime_version": None})
    audit = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert audit["usage_scope"] == "paid_api_requests"
    assert audit["runtime"]["runtime_version"] is None
    if provider == "cli":
        assert audit["summary"] is None
        assert factory.usage_snapshot() is None
    else:
        assert audit["summary"] == {"request_count": 0, "input_tokens": 0, "output_tokens": 0}


def test_paid_failure_survives_usage_audit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai
    from google.genai import types
    from ai.ports.provider import ProviderUnavailableError

    class Models:
        def generate_content(
            self, *, model: str, contents: str, config: types.GenerateContentConfig
        ) -> None:
            raise RuntimeError("synthetic network failure")

    class Client:
        def __init__(self, *, api_key: str, http_options: types.HttpOptions) -> None:
            self.models = Models()

    class Factory(DefaultProviderFactory):
        writes = 0

        def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
            self.writes += 1
            if self.writes > 1:
                raise OSError("synthetic audit disk failure")

    monkeypatch.setattr(genai, "Client", Client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-secret")
    provider = Factory().create(
        resolve_profile(provider="api"),
        protocol="segment_tags",
        config={},
        allow_paid_api=True,
        remaining_chars=100,
    )
    with pytest.raises(ProviderUnavailableError) as caught:
        provider.translate_batch(["Source"], system_prompt="Translate")
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "Usage audit also failed: OSError" in caught.value.__cause__.__notes__


@pytest.mark.parametrize("configured,expected", [(None, 600.0), (1800, 1800.0), (90.5, 90.5)])
def test_antigravity_timeout_reaches_executable_boundary(
    monkeypatch: pytest.MonkeyPatch, configured: float | None, expected: float
) -> None:
    from ai import antigravity_provider

    calls: list[tuple[list[str], float]] = []

    def execute(args: list[str], *, cwd: object, timeout: float) -> str:
        calls.append((args, timeout))
        if args[1:] == ["--version"]:
            return "1.1.27"
        if args[1:] == ["models"]:
            return "gemini-3.8-flash-low\tGemini 3.8 Flash (Low)"
        return '<segment id="1">花园</segment>\n<segment id="2">月亮</segment>'

    monkeypatch.setattr(antigravity_provider, "_execute", execute)
    config: dict[str, object] = (
        {} if configured is None else {"antigravity": {"timeout_seconds": configured}}
    )
    provider = DefaultProviderFactory().create(
        resolve_profile(),
        protocol="segment_tags",
        config=validate_config(config),
        allow_paid_api=False,
        remaining_chars=1,
    )

    assert provider.translate_batch(["garden", "moon"], system_prompt="Translate") == [
        "花园",
        "月亮",
    ]
    args, outer_deadline = calls[-1]
    assert args[args.index("--print-timeout") + 1] == f"{expected:g}s"
    assert outer_deadline == expected + 30


@pytest.mark.parametrize("value", [0, -5, 86401, "600", True])
def test_invalid_antigravity_timeout_is_rejected_before_execution(value: object) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        validate_config({"antigravity": {"timeout_seconds": value}})


def test_unknown_antigravity_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="print_timeout"):
        validate_config({"antigravity": {"print_timeout": 600}})
