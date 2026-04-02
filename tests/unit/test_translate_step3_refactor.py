from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from ai import cli
from ai.core.batcher import TextBatcher
from ai.core.engine import EngineConfig, TranslationEngine
from ai.ports.provider import ITranslationProvider, TranslationError
from ai.ports.source import IBookSource, Segment, TranslatedSegment


class _Probe:
    def __init__(self, availability: dict[str, bool]) -> None:
        self._availability = availability

    def probe(self, candidates: list[str]) -> dict[str, bool]:
        return {candidate: self._availability.get(candidate, False) for candidate in candidates}


class _RecordingProvider(ITranslationProvider):
    def __init__(self, *, fail_on_batch_size_above: int | None = None) -> None:
        self.calls: list[list[str]] = []
        self.prompts: list[str] = []
        self._fail_on_batch_size_above = fail_on_batch_size_above

    def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
        self.calls.append(list(segments))
        self.prompts.append(system_prompt)
        if (
            self._fail_on_batch_size_above is not None
            and len(segments) > self._fail_on_batch_size_above
        ):
            raise TranslationError("simulated batch failure")
        return [f"T:{segment}" for segment in segments]


class _MemorySource(IBookSource):
    def __init__(self, segments: list[str]) -> None:
        self._segments = [Segment(id=f"s{i}", text=text) for i, text in enumerate(segments)]
        self.applied: list[TranslatedSegment] = []
        self.saved_to: str | None = None

    def get_segments(self) -> list[Segment]:
        return self._segments

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        self.applied = translated

    def save(self, output_path: str) -> None:
        self.saved_to = output_path


def test_build_parser_accepts_model_and_probe_related_flags() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "book.epub",
            "--output",
            "translated.epub",
            "--model",
            "gemini-2.5-pro",
            "--provider",
            "api",
        ]
    )
    assert args.model == "gemini-2.5-pro"
    assert args.provider == "api"


def test_resolve_model_alias_with_probe_fallback_prefers_available_candidate() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }

    with pytest.MonkeyPatch.context() as mp:
        from ai import model_probe as probe_module

        mp.setattr(probe_module, "ModelProbe", lambda **kwargs: _Probe({"gemini-2.5-flash": True}))
        resolved_model, is_pro = cli.resolve_model("pro", config)

    assert resolved_model == "gemini-2.5-flash"
    assert is_pro is False


def test_resolve_model_explicit_mode_uses_alias_without_probe_fallback() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }

    with pytest.MonkeyPatch.context() as mp:
        from ai import model_probe as probe_module

        mp.setattr(probe_module, "ModelProbe", lambda **kwargs: _Probe({"gemini-2.5-flash": True}))
        resolved_model, is_pro = cli.resolve_model("pro", config, explicit=True)

    assert resolved_model == "gemini-2.5-pro"
    assert is_pro is True


def test_resolve_model_without_probe_falls_back_to_name_heuristics() -> None:
    with pytest.MonkeyPatch.context() as mp:
        from ai import model_resolver as resolver_module

        class _ExplodingResolver:
            def __init__(self, config: dict[str, object]) -> None:
                raise RuntimeError("resolver unavailable")

        mp.setattr(resolver_module, "ModelResolver", _ExplodingResolver)
        resolved_model, is_pro = cli.resolve_model("gemini-3-pro-preview", {})

    assert resolved_model == "gemini-3-pro-preview"
    assert is_pro is True


def test_resolve_model_warns_and_returns_primary_when_probe_rejects_all() -> None:
    config = {
        "model_aliases": {"pro": "gemini-2.5-pro", "flash": "gemini-2.5-flash"},
        "fallback_chain": ["flash"],
        "enable_fallback": True,
        "model_probe": {"enabled": True},
    }

    with pytest.MonkeyPatch.context() as mp:
        from ai import model_probe as probe_module

        mp.setattr(probe_module, "ModelProbe", lambda **kwargs: _Probe({}))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            resolved_model, is_pro = cli.resolve_model("pro", config)

    assert resolved_model == "gemini-2.5-pro"
    assert is_pro is True
    assert any("All model candidates unavailable" in str(w.message) for w in caught)


def test_text_batcher_accounts_for_separator_overhead() -> None:
    batcher = TextBatcher(max_batch_chars=12, separator_overhead=6)
    assert batcher.plan_batches(["abc", "def"]) == [["abc", "def"]]
    assert batcher.plan_batches(["abc", "def", "ghi"]) == [["abc", "def"], ["ghi"]]


def test_translation_engine_respects_batches_and_prompts(tmp_path: Path) -> None:
    provider = _RecordingProvider()
    source = _MemorySource(["alpha", "beta", "gamma"])
    engine = TranslationEngine(
        provider,
        EngineConfig(system_prompt="SYSTEM", max_batch_chars=6, separator_overhead=0),
    )

    result = engine.translate(source, str(tmp_path / "out.md"))

    assert result.total_segments == 3
    assert result.total_batches == 3
    assert [call for call in provider.calls] == [["alpha"], ["beta"], ["gamma"]]
    assert provider.prompts == ["SYSTEM", "SYSTEM", "SYSTEM"]
    assert [segment.translated for segment in source.applied] == ["T:alpha", "T:beta", "T:gamma"]


def test_translation_engine_split_retry_preserves_order(tmp_path: Path) -> None:
    provider = _RecordingProvider(fail_on_batch_size_above=1)
    source = _MemorySource(["A", "B"])
    engine = TranslationEngine(
        provider,
        EngineConfig(
            system_prompt="SYSTEM", max_batch_chars=100, separator_overhead=0, max_split_depth=5
        ),
    )

    result = engine.translate(source, str(tmp_path / "out.md"))

    assert result.translated_segments == 2
    assert provider.calls[0] == ["A", "B"]
    assert [segment.translated for segment in source.applied] == ["T:A", "T:B"]
