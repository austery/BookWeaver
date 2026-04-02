from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ai.cli as cli_module


def test_detect_input_format_epub_and_directory(tmp_path: Path) -> None:
    epub_path = tmp_path / "book.epub"
    epub_path.write_bytes(b"epub")
    assert cli_module.detect_input_format(str(epub_path)) == "epub"
    assert cli_module.detect_input_format(str(tmp_path)) == "markdown"


def test_cli_resolve_api_key_prefers_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    config = {"gemini_api": {"api_key": "config-key"}}

    assert cli_module._resolve_api_key(config) == "env-key"


def test_cli_resolve_api_key_reads_config_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = {"gemini_api": {"api_key": "config-key"}}

    assert cli_module._resolve_api_key(config) == "config-key"
    assert cli_module._resolve_api_key({"gemini_api": "invalid-shape"}) is None


def test_create_provider_wires_cli_resilience_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RawCLIProvider:
        def __init__(self, model: str) -> None:
            self.model = model

    class FakeProviderFactory:
        def __init__(self, config: dict[str, object]) -> None:
            self._config = config

        def create(
            self,
            model: str,
            provider_name: str = "cli",
            api_key: str | None = None,
            cli_api_fallback_enabled: bool = False,
        ) -> SimpleNamespace:
            captured["model"] = model
            captured["provider_name"] = provider_name
            captured["api_key"] = api_key
            captured["cli_api_fallback_enabled"] = cli_api_fallback_enabled
            return SimpleNamespace(primary=RawCLIProvider(model), fallback=None)

    class FakeGeminiCLIAdapter:
        def __init__(
            self,
            raw_provider: object,
            *,
            timeout_seconds: int,
            rate_limit_backoff: tuple[int, ...],
            transient_backoff: tuple[int, ...],
        ) -> None:
            captured["raw_provider_type"] = type(raw_provider).__name__
            captured["raw_provider_model"] = getattr(raw_provider, "model", None)
            captured["timeout_seconds"] = timeout_seconds
            captured["rate_limit_backoff"] = rate_limit_backoff
            captured["transient_backoff"] = transient_backoff

    monkeypatch.setattr("ai.provider_factory.ProviderFactory", FakeProviderFactory)
    monkeypatch.setattr(cli_module, "GeminiCLIAdapter", FakeGeminiCLIAdapter)

    config = {
        "epub_resilience": {
            "rate_limit_backoff_seconds": [12, 34],
            "transient_backoff_seconds": [7],
        }
    }
    provider = cli_module.create_provider(
        "cli",
        "gemini-2.5-pro",
        is_pro=True,
        config=config,
    )

    assert isinstance(provider, FakeGeminiCLIAdapter)
    assert captured["model"] == "gemini-2.5-pro"
    assert captured["provider_name"] == "cli"
    assert captured["raw_provider_type"] == "RawCLIProvider"
    assert captured["raw_provider_model"] == "gemini-2.5-pro"
    assert captured["timeout_seconds"] == 300
    assert captured["rate_limit_backoff"] == (12, 34)
    assert captured["transient_backoff"] == (7,)


def test_create_provider_api_uses_env_key_and_default_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeGeminiAPIProvider:
        def __init__(
            self, api_key: str | None, model: str, config: dict[str, object] | None
        ) -> None:
            captured["api_key"] = api_key
            captured["model"] = model
            captured["config"] = config

    class FakeGeminiAPIAdapter:
        def __init__(self, raw_provider: object, *, timeout_seconds: int) -> None:
            captured["raw_provider_type"] = type(raw_provider).__name__
            captured["timeout_seconds"] = timeout_seconds

    import ai.gemini_api_provider as gemini_api_provider_module

    monkeypatch.setattr(gemini_api_provider_module, "GeminiAPIProvider", FakeGeminiAPIProvider)
    monkeypatch.setattr(cli_module, "GeminiAPIAdapter", FakeGeminiAPIAdapter)
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")

    provider = cli_module.create_provider(
        "api",
        "gemini-2.5-flash",
        is_pro=False,
        config={"gemini_api": {"api_key": "config-key"}},
    )

    assert isinstance(provider, FakeGeminiAPIAdapter)
    assert captured["api_key"] == "env-key"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["raw_provider_type"] == "FakeGeminiAPIProvider"
    assert captured["timeout_seconds"] == 180
