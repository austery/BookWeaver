from __future__ import annotations

import pytest

from ai.gemini_provider import GeminiProvider
from ai.provider_factory import ProviderFactory


def test_cli_creates_gemini_provider_no_fallback() -> None:
    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="cli")
    assert isinstance(pair.primary, GeminiProvider)
    assert pair.primary.model == "gemini-2.5-flash"
    assert pair.fallback is None


def test_cli_with_fallback_creates_provider_pair() -> None:
    from ai.gemini_api_provider import GeminiAPIProvider

    factory = ProviderFactory({})
    pair = factory.create(
        "gemini-2.5-pro",
        provider_name="cli",
        api_key="test-key",
        cli_api_fallback_enabled=True,
    )
    assert isinstance(pair.primary, GeminiProvider)
    assert pair.primary.model == "gemini-2.5-pro"
    assert isinstance(pair.fallback, GeminiAPIProvider)
    assert pair.fallback.model == "gemini-2.5-pro"


def test_api_creates_gemini_api_provider_no_fallback() -> None:
    from ai.gemini_api_provider import GeminiAPIProvider

    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="api", api_key="test-key")
    assert isinstance(pair.primary, GeminiAPIProvider)
    assert pair.primary.model == "gemini-2.5-flash"
    assert pair.fallback is None


def test_invalid_provider_raises_value_error() -> None:
    factory = ProviderFactory({})
    with pytest.raises(ValueError, match="Unknown provider 'grpc'"):
        factory.create("gemini-2.5-flash", provider_name="grpc")


def test_cli_without_fallback_flag_has_no_fallback() -> None:
    factory = ProviderFactory({})
    pair = factory.create("gemini-2.5-flash", provider_name="cli", api_key="test-key")
    assert pair.fallback is None
