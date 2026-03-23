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
