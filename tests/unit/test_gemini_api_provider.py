"""Tests for Gemini API provider (alternative to CLI provider)."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


def test_gemini_api_provider_module_exists() -> None:
    """Test that GeminiAPIProvider module can be imported."""
    try:
        module = importlib.import_module("ai.gemini_api_provider")
    except ModuleNotFoundError as exc:
        raise AssertionError("Expected module ai.gemini_api_provider to exist") from exc

    assert hasattr(module, "GeminiAPIProvider"), "GeminiAPIProvider class should be defined"


def test_gemini_api_provider_requires_api_key() -> None:
    """Test that GeminiAPIProvider requires API key."""
    from ai.gemini_api_provider import GeminiAPIProvider

    with pytest.raises(ValueError, match="API key.*required"):
        GeminiAPIProvider(api_key="", model="gemini-2.5-flash")


def test_gemini_api_provider_accepts_valid_model() -> None:
    """Test that GeminiAPIProvider accepts valid model name."""
    from ai.gemini_api_provider import GeminiAPIProvider

    provider = GeminiAPIProvider(api_key="test-key-123", model="gemini-2.5-flash")
    assert provider.model == "gemini-2.5-flash"


def test_translate_chunk_returns_translated_text() -> None:
    """Test successful translation using Gemini API."""
    from ai.gemini_api_provider import GeminiAPIProvider

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client.models, "generate_content") as mock_generate:
        mock_response = MagicMock()
        mock_response.text = "这是翻译后的文本"
        mock_generate.return_value = mock_response

        result = provider.translate_chunk(
            text="This is source text",
            chunk_size=100,
            system_prompt="Translate to Chinese",
        )

        assert result == "这是翻译后的文本"
        mock_generate.assert_called_once()


def test_rate_limit_error_raised_on_429() -> None:
    """Test that RateLimitError is raised on 429 response."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError
    from google.genai import errors

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client.models, "generate_content") as mock_generate:
        mock_generate.side_effect = errors.ClientError(
            429, {"error": {"message": "Rate limit exceeded"}}
        )

        with pytest.raises(RateLimitError, match="Rate limit"):
            provider.translate_chunk(
                text="test", chunk_size=10, system_prompt="translate", timeout_seconds=60
            )


def test_rate_limit_error_extracts_retry_after() -> None:
    """Test that retry_after_seconds is extracted from error details."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError
    from google.genai import errors

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client.models, "generate_content") as mock_generate:
        error = errors.ClientError(
            429, {"error": {"message": "Quota exceeded. Retry in 30 seconds."}}
        )
        mock_generate.side_effect = error

        with pytest.raises(RateLimitError) as exc_info:
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")

        # Verify retry_after_seconds is parsed
        assert exc_info.value.retry_after_seconds == 30


def test_handles_internal_server_error() -> None:
    """Test that 5xx errors are wrapped as RuntimeError."""
    from ai.gemini_api_provider import GeminiAPIProvider
    from google.genai import errors

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client.models, "generate_content") as mock_generate:
        mock_generate.side_effect = errors.ServerError(500, {"error": {"message": "Server error"}})

        with pytest.raises(RuntimeError, match="Gemini API.*error"):
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")


def test_handles_timeout() -> None:
    """Test that timeout is respected and raises error."""
    from ai.gemini_api_provider import GeminiAPIProvider
    from google.genai import errors

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client.models, "generate_content") as mock_generate:
        mock_generate.side_effect = errors.ClientError(
            408, {"error": {"message": "Request timeout"}}
        )

        with pytest.raises(RuntimeError, match="timeout|Timeout"):
            provider.translate_chunk(
                text="test", chunk_size=10, system_prompt="translate", timeout_seconds=10
            )


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that API key can be loaded from environment variable."""
    from ai.gemini_api_provider import GeminiAPIProvider

    monkeypatch.setenv("GEMINI_API_KEY", "env-api-key-123")

    provider = GeminiAPIProvider(model="gemini-2.5-flash")
    # Should use env var API key without explicit parameter
    assert provider.api_key == "env-api-key-123"


def test_api_key_from_config_file() -> None:
    """Test that API key can be loaded from config dict."""
    from ai.gemini_api_provider import GeminiAPIProvider

    config = {
        "gemini_api": {
            "api_key": "config-api-key-456",
            "model": "gemini-2.5-pro",
        }
    }

    provider = GeminiAPIProvider(model="gemini-2.5-flash", config=config)
    assert provider.api_key == "config-api-key-456"
    # Model should NOT be overridden when explicitly provided
    assert provider.model == "gemini-2.5-flash"


def test_api_key_priority_explicit_over_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that explicit api_key parameter has priority over config."""
    from ai.gemini_api_provider import GeminiAPIProvider

    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    config = {"gemini_api": {"api_key": "config-key"}}

    # Explicit parameter should win
    provider = GeminiAPIProvider(api_key="explicit-key", config=config)
    assert provider.api_key == "explicit-key"

    # Env var should be next
    provider = GeminiAPIProvider(config=config)
    assert provider.api_key == "env-key"

    # Config should be last
    monkeypatch.delenv("GEMINI_API_KEY")
    provider = GeminiAPIProvider(config=config)
    assert provider.api_key == "config-key"


def test_rate_limit_error_is_subclass_of_runtime_error() -> None:
    """Test that RateLimitError inherits from RuntimeError for compatibility."""
    from ai.gemini_api_provider import RateLimitError

    assert issubclass(RateLimitError, RuntimeError)


def test_empty_response_raises_error() -> None:
    """Test that empty response text raises an error."""
    from ai.gemini_api_provider import GeminiAPIProvider

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client, "generate_content") as mock_generate:
        mock_response = MagicMock()
        mock_response.text = ""  # Empty response
        mock_generate.return_value = mock_response

        with pytest.raises(RuntimeError, match="[Ee]mpty.*response"):
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")


def test_translate_chunk_retries_on_rate_limit() -> None:
    """Test that translate_chunk retries on RateLimitError and eventually succeeds."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client, "generate_content") as mock_generate:
        mock_response = MagicMock()
        mock_response.text = "这是翻译后的文本"
        mock_generate.side_effect = [
            RateLimitError("Rate limit exceeded", retry_after_seconds=1),
            mock_response,
        ]

        with patch("time.sleep") as mock_sleep:
            result = provider.translate_chunk(
                text="This is source text",
                chunk_size=100,
                system_prompt="Translate to Chinese",
                max_retries=2,
                retry_delay_seconds=0,
            )

            assert result == "这是翻译后的文本"
            assert mock_generate.call_count == 2
            mock_sleep.assert_called_once_with(1)


def test_translate_chunk_fails_after_max_retries() -> None:
    """Test that translate_chunk fails after all retries are exhausted."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch.object(provider._client, "generate_content") as mock_generate:
        mock_generate.side_effect = RateLimitError("Rate limit exceeded", retry_after_seconds=1)

        with patch("time.sleep"), pytest.raises(RateLimitError):
            provider.translate_chunk(
                text="This is source text",
                chunk_size=100,
                system_prompt="Translate to Chinese",
                max_retries=3,
                retry_delay_seconds=0,
            )

        assert mock_generate.call_count == 3
