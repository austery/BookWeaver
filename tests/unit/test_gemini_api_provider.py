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

    # Mock the Google GenAI SDK
    with patch("ai.gemini_api_provider.genai") as mock_genai:
        # Setup mock response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "这是翻译后的文本"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        result = provider.translate_chunk(
            text="This is source text",
            chunk_size=100,
            system_prompt="Translate to Chinese",
        )

        assert result == "这是翻译后的文本"
        mock_model.generate_content.assert_called_once()


def test_rate_limit_error_raised_on_429() -> None:
    """Test that RateLimitError is raised on 429 response."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError
    from google.api_core.exceptions import ResourceExhausted

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch("ai.gemini_api_provider.genai") as mock_genai:
        mock_model = MagicMock()
        # Simulate 429 ResourceExhausted error
        mock_model.generate_content.side_effect = ResourceExhausted("Rate limit exceeded")
        mock_genai.GenerativeModel.return_value = mock_model

        with pytest.raises(RateLimitError, match="Rate limit"):
            provider.translate_chunk(
                text="test", chunk_size=10, system_prompt="translate", timeout_seconds=60
            )


def test_rate_limit_error_extracts_retry_after() -> None:
    """Test that retry_after_seconds is extracted from error details."""
    from ai.gemini_api_provider import GeminiAPIProvider, RateLimitError
    from google.api_core.exceptions import ResourceExhausted

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch("ai.gemini_api_provider.genai") as mock_genai:
        mock_model = MagicMock()
        # Simulate error with retry delay
        error = ResourceExhausted("Quota exceeded. Retry in 30 seconds.")
        mock_model.generate_content.side_effect = error
        mock_genai.GenerativeModel.return_value = mock_model

        with pytest.raises(RateLimitError) as exc_info:
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")

        # Verify retry_after_seconds is parsed
        assert exc_info.value.retry_after_seconds == 30


def test_handles_internal_server_error() -> None:
    """Test that 5xx errors are wrapped as RuntimeError."""
    from ai.gemini_api_provider import GeminiAPIProvider
    from google.api_core.exceptions import InternalServerError

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch("ai.gemini_api_provider.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = InternalServerError("Server error")
        mock_genai.GenerativeModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="Gemini API.*error"):
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")


def test_handles_timeout() -> None:
    """Test that timeout is respected and raises error."""
    from ai.gemini_api_provider import GeminiAPIProvider
    from google.api_core.exceptions import DeadlineExceeded

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch("ai.gemini_api_provider.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = DeadlineExceeded("Request timeout")
        mock_genai.GenerativeModel.return_value = mock_model

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


def test_rate_limit_error_is_subclass_of_runtime_error() -> None:
    """Test that RateLimitError inherits from RuntimeError for compatibility."""
    from ai.gemini_api_provider import RateLimitError

    assert issubclass(RateLimitError, RuntimeError)


def test_empty_response_raises_error() -> None:
    """Test that empty response text raises an error."""
    from ai.gemini_api_provider import GeminiAPIProvider

    provider = GeminiAPIProvider(api_key="test-key", model="gemini-2.5-flash")

    with patch("ai.gemini_api_provider.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""  # Empty response
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="[Ee]mpty.*response"):
            provider.translate_chunk(text="test", chunk_size=10, system_prompt="translate")
