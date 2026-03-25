from __future__ import annotations

import importlib
import subprocess

import pytest


def test_gemini_provider_module_exists() -> None:
    try:
        module = importlib.import_module("ai.gemini_provider")
    except ModuleNotFoundError as exc:
        raise AssertionError("Expected module ai.gemini_provider to exist") from exc

    assert hasattr(module, "GeminiProvider"), "GeminiProvider class should be defined"


def test_gemini_provider_accepts_valid_model() -> None:
    module = importlib.import_module("ai.gemini_provider")
    provider = module.GeminiProvider(model="gemini-2.5-flash")
    assert provider.model == "gemini-2.5-flash"


def test_gemini_provider_accepts_unknown_model_name() -> None:
    module = importlib.import_module("ai.gemini_provider")
    provider = module.GeminiProvider(model="gemini-3-pro-preview")
    assert provider.model == "gemini-3-pro-preview"


def test_translate_chunk_raises_on_nonzero_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that GeminiProvider.translate_chunk raises RuntimeError with stderr when CLI fails."""
    module = importlib.import_module("ai.gemini_provider")
    provider = module.GeminiProvider(model="gemini-3-pro-preview")

    # Mock subprocess.run to return error
    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess(
            args=["gemini"], returncode=1, stdout="", stderr="API error: model not found"
        )
        return result

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Verify it raises RuntimeError with stderr included
    with pytest.raises(RuntimeError) as exc_info:
        provider.translate_chunk(
            text="test chunk", chunk_size=100, system_prompt="Translate to Chinese"
        )

    assert "API error" in str(exc_info.value)


def test_rate_limit_error_raised_on_resource_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.gemini_provider import GeminiProvider, RateLimitError

    provider = GeminiProvider(model="gemini-3-pro-preview")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gemini"],
            returncode=1,
            stdout="",
            stderr='{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}',
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(RateLimitError):
        provider.translate_chunk(text="hello", chunk_size=5, system_prompt="translate")


def test_rate_limit_error_is_subclass_of_runtime_error() -> None:
    from ai.gemini_provider import RateLimitError

    assert issubclass(RateLimitError, RuntimeError)


def test_rate_limit_error_stores_retry_after() -> None:
    from ai.gemini_provider import RateLimitError

    err = RateLimitError("rate limited", retry_after_seconds=45)
    assert err.retry_after_seconds == 45


def test_rate_limit_error_retry_after_defaults_to_none() -> None:
    from ai.gemini_provider import RateLimitError

    err = RateLimitError("rate limited")
    assert err.retry_after_seconds is None


def test_non_rate_limit_failure_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.gemini_provider import GeminiProvider, RateLimitError

    provider = GeminiProvider(model="gemini-3-pro-preview")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gemini"], returncode=1, stdout="", stderr="model not found"
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    with pytest.raises(RuntimeError) as exc_info:
        provider.translate_chunk(text="hello", chunk_size=5, system_prompt="translate")
    assert not isinstance(exc_info.value, RateLimitError)


def test_abort_error_raised_as_transient_cli_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.gemini_provider import GeminiProvider, TransientCLIError

    provider = GeminiProvider(model="gemini-3-pro-preview")

    def mock_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gemini"],
            returncode=1,
            stdout="",
            stderr="AbortError: The user aborted a request.",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(TransientCLIError):
        provider.translate_chunk(text="hello", chunk_size=5, system_prompt="translate")


def test_parse_retry_after_json_format() -> None:
    from ai.gemini_provider import _parse_retry_after

    assert _parse_retry_after('"retryDelay": "45s"') == 45


def test_parse_retry_after_natural_language() -> None:
    from ai.gemini_provider import _parse_retry_after

    assert _parse_retry_after("Please retry after 30 seconds.") == 30


def test_parse_retry_after_returns_none_when_absent() -> None:
    from ai.gemini_provider import _parse_retry_after

    assert _parse_retry_after("RESOURCE_EXHAUSTED: quota exceeded") is None
