"""Unit tests for ai.cli — the composition root.

Tests prompt assembly, argument parsing, and model resolution.
Does NOT test actual translation (that's covered by engine + adapter tests).
"""

from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ai.cli as cli_module
from ai.ports.provider import TranslationError
from ai.ports.source import Segment, TranslatedSegment
from ai.cli import (
    build_parser,
    build_system_prompt,
    create_provider,
    detect_input_format,
    load_config,
    load_glossary_block,
    run,
    _get_language_name,
    _SanityProbeConfig,
)


# ── Prompt assembly ───────────────────────────────────────────


class TestBuildSystemPrompt:
    def test_basic_prompt(self) -> None:
        prompt = build_system_prompt("Chinese")
        assert "Chinese" in prompt
        assert "translator" in prompt

    def test_with_glossary(self) -> None:
        prompt = build_system_prompt("Chinese", glossary_block="## Glossary\n- API → 接口")
        assert "Glossary" in prompt
        assert "接口" in prompt

    def test_with_custom_instructions(self) -> None:
        prompt = build_system_prompt("Chinese", custom_prompt="Use formal tone.")
        assert "ADDITIONAL INSTRUCTIONS" in prompt
        assert "formal tone" in prompt

    def test_with_both_glossary_and_custom(self) -> None:
        prompt = build_system_prompt(
            "Japanese",
            glossary_block="## Terms\n- AI → 人工知能",
            custom_prompt="Use keigo.",
        )
        assert "Japanese" in prompt
        assert "人工知能" in prompt
        assert "keigo" in prompt

    def test_no_percent_delimiter_in_prompt(self) -> None:
        """System prompt must NOT mention %% — that's the adapter's job."""
        prompt = build_system_prompt("Chinese")
        assert "%%" not in prompt

    def test_epub_immersive_prompt_includes_delimiter_and_output_format_rules(self) -> None:
        prompt = build_system_prompt("Chinese", immersive=True)
        assert "If input contains %%" in prompt
        assert "OUTPUT FORMAT" in prompt
        assert "Translate to Chinese:" in prompt

    def test_non_epub_prompt_does_not_include_immersive_footer(self) -> None:
        prompt = build_system_prompt("Chinese", immersive=False)
        assert "OUTPUT FORMAT" not in prompt
        assert "Translate to Chinese:" not in prompt


class TestSanityProbeConfig:
    def test_load_probe_config_defaults(self) -> None:
        from ai.cli import _load_probe_config

        cfg = _load_probe_config({})
        assert cfg.enabled is True
        assert cfg.max_length_ratio == 2.0
        assert cfg.min_length_ratio == 0.15
        assert cfg.min_source_length == 10
        assert cfg.min_cjk_density == 0.30
        assert cfg.min_cjk_source_length == 40
        assert cfg.heartbeat_chars == 60

    def test_load_probe_config_from_dict(self) -> None:
        from ai.cli import _load_probe_config

        cfg = _load_probe_config(
            {
                "sanity_probe": {
                    "enabled": False,
                    "max_length_ratio": 3.0,
                    "min_length_ratio": 0.1,
                    "min_source_length": 5,
                    "min_cjk_density": 0.5,
                    "min_cjk_source_length": 25,
                    "heartbeat_chars": 80,
                }
            }
        )
        assert cfg.enabled is False
        assert cfg.max_length_ratio == 3.0
        assert cfg.min_length_ratio == 0.1
        assert cfg.min_source_length == 5
        assert cfg.min_cjk_density == 0.5
        assert cfg.min_cjk_source_length == 25
        assert cfg.heartbeat_chars == 80

    def test_load_probe_config_partial_dict_merges_with_defaults(self) -> None:
        from ai.cli import _load_probe_config

        cfg = _load_probe_config({"sanity_probe": {"enabled": False}})
        assert cfg.enabled is False
        assert cfg.max_length_ratio == 2.0  # default preserved
        assert cfg.min_cjk_density == 0.30  # default preserved

    def test_load_probe_config_ignores_bad_type(self) -> None:
        from ai.cli import _load_probe_config

        cfg = _load_probe_config({"sanity_probe": "not-a-dict"})
        assert cfg.enabled is True  # falls back to defaults

    def test_load_probe_config_falls_back_on_bad_field_value(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from ai.cli import _load_probe_config

        cfg = _load_probe_config({"sanity_probe": {"max_length_ratio": "not-a-number"}})
        assert cfg.enabled is True  # falls back to defaults
        assert "Warning" in capsys.readouterr().err


class TestSanityCheckBatch:
    def _make_seg(self, seg_id: str, original: str, translated: str) -> TranslatedSegment:
        return TranslatedSegment(id=seg_id, original=original, translated=translated)

    def _default_probe(self) -> _SanityProbeConfig:
        from ai.cli import _SanityProbeConfig

        return _SanityProbeConfig()

    def test_passes_normal_en_to_zh(self) -> None:
        from ai.cli import _sanity_check_batch

        segs = [
            self._make_seg(
                "ch1.xhtml::0", "The key principle is that space curves.", "核心原则是空间弯曲。"
            )
        ]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=5)

    def test_raises_on_empty_output(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        segs = [self._make_seg("ch1.xhtml::0", "Hello world", "")]
        with pytest.raises(TranslationError, match="empty output"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=2, total_batches=10)

    def test_raises_on_length_ratio_too_high(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        segs = [self._make_seg("ch1.xhtml::0", "Hello world example.", "你" * 200)]
        with pytest.raises(TranslationError, match="length_ratio"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_raises_on_length_ratio_too_low(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        # Source 100 chars, translated 5 chars (ratio=0.05 < min=0.15)
        segs = [self._make_seg("ch1.xhtml::0", "A" * 100, "你好。")]
        with pytest.raises(TranslationError, match="length_ratio"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_raises_on_cjk_density_too_low(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        # Source >= min_cjk_source_length (40) so CJK check fires.
        segs = [
            self._make_seg(
                "ch1.xhtml::0",
                "Hello world example, this is a longer test.",
                "Hello world example, this is a longer test.",
            )
        ]
        with pytest.raises(TranslationError, match="cjk_density"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=1, total_batches=5)

    def test_skips_length_ratio_for_short_source(self) -> None:
        from ai.cli import _sanity_check_batch

        segs = [self._make_seg("ch1.xhtml::0", "A", "翻译一下这个字母A的中文意思是什么")]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_skips_cjk_check_for_non_zh_lang(self) -> None:
        from ai.cli import _sanity_check_batch

        segs = [self._make_seg("ch1.xhtml::0", "Hello world example.", "Hallo Welt Beispiel.")]
        _sanity_check_batch(segs, "de", self._default_probe(), batch_index=0, total_batches=1)

    def test_error_message_includes_batch_position(self) -> None:
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        segs = [self._make_seg("ch1.xhtml::5", "Hello world.", "")]
        with pytest.raises(TranslationError, match=r"batch 3/10"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=2, total_batches=10)

    def test_cjk_density_uses_stripped_length(self) -> None:
        from ai.cli import _sanity_check_batch

        # Source >= min_cjk_source_length (40) to actually trigger the CJK density check.
        # After stripping: 2 CJK / 2 effective chars = 1.0 > threshold — should pass.
        segs = [self._make_seg("ch1.xhtml::0", "A" * 40, "你好\n\n\n\n\n\n\n\n\n\n")]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)

    def test_cjk_density_subtracts_ascii_letters_for_proper_nouns(self) -> None:
        from ai.cli import _sanity_check_batch

        # Stock ticker "Sheet & Tube" is preserved in Latin in the translation.
        # Naïve formula: 5 CJK / 24 total = 0.21 < 0.30 → false positive.
        # Corrected formula: 5 CJK / (24 - 9 ASCII letters) = 5/15 = 0.33 → passes.
        segs = [
            self._make_seg(
                "split_084.html::0",
                "1. Sheet & Tube, preferred, sells at 40.",  # 40 chars — CJK check fires
                "1. Sheet & Tube优先股，售价40。",
            )
        ]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=26, total_batches=98)

    def test_cjk_check_skips_equation_length_source(self) -> None:
        from ai.cli import _sanity_check_batch

        # Standalone math equation (19 chars, below min_cjk_source_length=40).
        # Model correctly preserves it as-is (0 CJK) — must not raise.
        segs = [self._make_seg("ch1.xhtml::19", "Rab − ½ R gab = Tab", "Rab − ½ R gab = Tab")]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=3, total_batches=12)

    def test_cjk_check_skips_source_with_url(self) -> None:
        from ai.cli import _sanity_check_batch

        # Source contains a URL — CJK density check is bypassed entirely.
        # Density of translation would be ≈ 0.125, well below the 0.30 threshold,
        # but that is correct: the URL keeps Latin chars in the output.
        segs = [
            self._make_seg(
                "endpage.xhtml::1",
                "Follow the Penguin Twitter.com@penguinukbooks",
                "关注企鹅 Twitter.com@penguinukbooks",
            )
        ]
        _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=7, total_batches=9)

    def test_cjk_check_skips_copyright_markers_in_source(self) -> None:
        from ai.cli import _sanity_check_batch

        # © and "First published" are universal copyright-page markers.
        # Translations keep publisher names / foreign titles in Latin — low CJK density —
        # but must NOT raise because the bypass fires first.
        # Translations are long enough to pass the length-ratio check (ratio ≥ 0.15).
        cases = [
            (
                "copyright.xhtml::3",
                "Copyright © Carlo Rovelli, 2014Translation copyright © Simon Carnell, 2015",
                # density ≈ 0.11 < 0.30 — would fail without bypass
                "版权所有 © Carlo Rovelli, 2014. 翻译版权 © Simon Carnell and Erica Segre, 2015.",
            ),
            (
                "copyright.xhtml::2",
                "First published in Italian under the title Sette brevi lezioni di fisica 2014",
                # density ≈ 0.15 < 0.30 — would fail without bypass
                "首次以意大利文发行 by Adelphi Edizioni 2014 and Allen Lane 2015",
            ),
        ]
        for seg_id, src, tgt in cases:
            segs = [self._make_seg(seg_id, src, tgt)]
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=1, total_batches=2)
        from ai.cli import _sanity_check_batch
        from ai.ports.provider import TranslationError

        # Pure prose (>= 40 chars, no URL, no copyright marker) — check fires.
        segs = [
            self._make_seg(
                "ch1.xhtml::0",
                "Hello world example, this is a longer test.",
                "Hello world example, this is a longer test.",
            )
        ]
        with pytest.raises(TranslationError, match="cjk_density"):
            _sanity_check_batch(segs, "zh", self._default_probe(), batch_index=0, total_batches=1)


class TestEmitBatchSample:
    def test_emits_batch_sample_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig

        segs = [
            TranslatedSegment(
                id="EPUB/ch04.xhtml::0",
                original="The key principle is encapsulation of state.",
                translated="核心原则是状态封装。",
            )
        ]
        _emit_batch_sample(segs, _SanityProbeConfig(), batch_index=2, total_batches=10)
        out = capsys.readouterr().out
        assert "[progress:batch_sample]" in out
        assert "batch=3/10" in out
        assert "doc=EPUB/ch04.xhtml" in out
        assert "核心原则" in out

    def test_truncates_long_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig

        long_src = "A" * 200
        long_tgt = "中" * 200
        segs = [TranslatedSegment(id="ch::0", original=long_src, translated=long_tgt)]
        _emit_batch_sample(
            segs, _SanityProbeConfig(heartbeat_chars=60), batch_index=0, total_batches=1
        )
        out = capsys.readouterr().out
        assert "..." in out

    def test_no_output_for_empty_batch(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig

        _emit_batch_sample([], _SanityProbeConfig(), batch_index=0, total_batches=1)
        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out

    def test_omits_doc_for_non_epub_segment(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ai.cli import _emit_batch_sample, _SanityProbeConfig

        segs = [TranslatedSegment(id="plain-segment-id", original="Hello.", translated="你好。")]
        _emit_batch_sample(segs, _SanityProbeConfig(), batch_index=0, total_batches=1)
        out = capsys.readouterr().out
        assert "[progress:batch_sample]" in out
        assert "doc=" not in out


class TestGlossaryPromptInjection:
    def test_load_glossary_block_with_min_priority_filter(self, tmp_path: Path) -> None:
        glossary = tmp_path / "glossary.json"
        glossary.write_text(
            '{"critical_terminology": ['
            '{"term":"Connascence","suggested_translation":"共生性","priority":"critical"},'
            '{"term":"Shift Left","suggested_translation":"向左移动","priority":"high"},'
            '{"term":"Tech Debt","suggested_translation":"技术债务","priority":"medium"}'
            "]}",
            encoding="utf-8",
        )

        block = load_glossary_block(str(glossary), min_priority="high")
        assert block is not None
        assert "Connascence" in block
        assert "Shift Left" in block
        assert "Tech Debt" not in block

    def test_build_system_prompt_includes_filtered_glossary_block(self) -> None:
        glossary_block = "【关键术语约束】\n• Connascence → 共生性"
        prompt = build_system_prompt(
            "Chinese",
            glossary_block=glossary_block,
            custom_prompt="Preserve code blocks",
        )
        assert "Connascence" in prompt
        assert "ADDITIONAL INSTRUCTIONS" in prompt
        assert "Preserve code blocks" in prompt


class TestGlossaryProgressLog:
    def test_glossary_resolved_log_includes_mode_and_metrics(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Regression: glossary resolution progress log should include mode + metrics.

        When glossary extraction resolves, the progress log should emit:
        - action=resolved
        - mode (auto|deep-scan)
        - tier (index | local-refinement | deep-scan)
        - docs, chars, candidate_count, term_count (useful metrics)

        This is a unit test of _log_progress; integration test would mock run() call.
        """
        from ai.cli import _log_progress

        # Simulate glossary resolution log (as emitted by ai/cli.py line 979-987)
        _log_progress(
            "glossary",
            action="resolved",
            mode="auto",
            tier="local-refinement",
            docs=3,
            chars=8450,
            candidate_count=24,
            term_count=18,
        )

        out = capsys.readouterr().out
        assert "[progress:glossary]" in out
        assert "action=resolved" in out
        assert "mode=auto" in out
        assert "tier=local-refinement" in out
        assert "docs=3" in out
        assert "chars=8450" in out
        assert "candidate_count=24" in out
        assert "term_count=18" in out


# ── Language resolution ───────────────────────────────────────


class TestLanguageResolution:
    def test_known_codes(self) -> None:
        assert _get_language_name("zh") == "Chinese"
        assert _get_language_name("en") == "English"
        assert _get_language_name("ja") == "Japanese"

    def test_unknown_code_returns_itself(self) -> None:
        assert _get_language_name("xx") == "xx"


# ── Runtime config loading ─────────────────────────────────────


class TestLoadConfig:
    def test_load_config_merges_standard_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project_root = tmp_path / "project"
        (project_root / "ai").mkdir(parents=True)
        (project_root / "config").mkdir(parents=True)

        (project_root / "config" / "config.json.example").write_text(
            (
                '{"default_model":"gemini-2.5-flash",'
                '"gemini_api":{"enabled":true,"api_key":null},'
                '"prompt_profile":"default"}'
            ),
            encoding="utf-8",
        )
        (project_root / "config" / "config.json").write_text(
            '{"default_model":"gemini-2.5-pro","prompt_profile":"ebook"}',
            encoding="utf-8",
        )

        fake_home = tmp_path / "home"
        user_cfg = fake_home / ".config" / "translatebook"
        user_cfg.mkdir(parents=True)
        (user_cfg / "config.json").write_text(
            '{"gemini_api":{"api_key":"user-key"}}',
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "__file__", str(project_root / "ai" / "cli.py"))
        monkeypatch.setattr(cli_module.Path, "home", staticmethod(lambda: fake_home))

        config = load_config()

        assert config["default_model"] == "gemini-2.5-pro"
        assert config["prompt_profile"] == "ebook"
        assert isinstance(config["gemini_api"], dict)
        assert config["gemini_api"]["enabled"] is True
        assert config["gemini_api"]["api_key"] == "user-key"

    def test_load_config_returns_empty_dict_when_registry_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _RaisingRegistry:
            @classmethod
            def from_json_files(cls, paths: list[Path]) -> "_RaisingRegistry":
                raise ValueError("bad config")

        monkeypatch.setattr(cli_module, "ConfigRegistry", _RaisingRegistry)
        assert load_config() == {}


# ── Provider wiring ─────────────────────────────────────────────


class TestCreateProviderResilience:
    def test_create_provider_uses_transient_retry_sequence_from_resilience_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class _FakeGeminiProvider:
            def __init__(self, model: str) -> None:
                captured["model"] = model

        class _FakeGeminiCLIAdapter:
            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                rate_limit_backoff: tuple[int, ...],
                transient_backoff: tuple[int, ...],
                use_segment_tags: bool = False,
            ) -> None:
                captured["raw_provider_type"] = type(raw_provider).__name__
                captured["timeout_seconds"] = timeout_seconds
                captured["rate_limit_backoff"] = rate_limit_backoff
                captured["transient_backoff"] = transient_backoff
                captured["use_segment_tags"] = use_segment_tags

        class _FakeProviderFactory:
            def __init__(self, config: dict[str, object]) -> None:
                self._config = config

            def create(
                self,
                model: str,
                provider_name: str = "cli",
                api_key: str | None = None,
                cli_api_fallback_enabled: bool = False,
            ) -> SimpleNamespace:
                return SimpleNamespace(primary=_FakeGeminiProvider(model), fallback=None)

        monkeypatch.setattr("ai.provider_factory.ProviderFactory", _FakeProviderFactory)
        monkeypatch.setattr(cli_module, "GeminiCLIAdapter", _FakeGeminiCLIAdapter)

        provider = create_provider(
            "cli",
            "gemini-2.5-flash",
            is_pro=False,
            config={
                "epub_resilience": {
                    "rate_limit_backoff_seconds": [9],
                    "transient_backoff_seconds": [3, 5, 8],
                }
            },
        )

        assert isinstance(provider, _FakeGeminiCLIAdapter)
        assert captured["model"] == "gemini-2.5-flash"
        assert captured["raw_provider_type"] == "_FakeGeminiProvider"
        assert captured["timeout_seconds"] == 180
        assert captured["rate_limit_backoff"] == (9,)
        assert captured["transient_backoff"] == (3, 5, 8)
        assert captured["use_segment_tags"] is False

    def test_create_provider_rejects_non_positive_transient_backoff_values(self) -> None:
        with pytest.raises(ValueError, match="transient_backoff_seconds"):
            create_provider(
                "cli",
                "gemini-2.5-flash",
                config={"epub_resilience": {"transient_backoff_seconds": [4, 0]}},
            )


class TestCreateProviderCliApiFallback:
    def test_cli_api_fallback_attempts_api_on_cli_translation_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class _RawCLIProvider:
            pass

        class _RawAPIProvider:
            pass

        class _FakeProviderFactory:
            def __init__(self, config: dict[str, object]) -> None:
                self._config = config

            def create(
                self,
                model: str,
                provider_name: str = "cli",
                api_key: str | None = None,
                cli_api_fallback_enabled: bool = False,
            ) -> SimpleNamespace:
                fallback = _RawAPIProvider() if cli_api_fallback_enabled else None
                return SimpleNamespace(primary=_RawCLIProvider(), fallback=fallback)

        class _FailingCLIAdapter:
            calls = 0

            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                rate_limit_backoff: tuple[int, ...],
                transient_backoff: tuple[int, ...],
                use_segment_tags: bool = False,
            ) -> None:
                self._raw_provider = raw_provider

            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                _FailingCLIAdapter.calls += 1
                raise TranslationError("simulated transient transport failure")

        class _APIAdapter:
            calls = 0

            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                use_segment_tags: bool = False,
            ) -> None:
                self._raw_provider = raw_provider

            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                _APIAdapter.calls += 1
                return [f"api:{segment}" for segment in segments]

        monkeypatch.setattr("ai.provider_factory.ProviderFactory", _FakeProviderFactory)
        monkeypatch.setattr(cli_module, "GeminiCLIAdapter", _FailingCLIAdapter)
        monkeypatch.setattr(cli_module, "GeminiAPIAdapter", _APIAdapter)

        provider = create_provider(
            "cli",
            "gemini-2.5-flash",
            config={"gemini_api": {"api_key": "test-key"}},
            cli_api_fallback=True,
        )

        translated = provider.translate_batch(["hello"], system_prompt="PROMPT")
        assert translated == ["api:hello"]
        assert _FailingCLIAdapter.calls == 1
        assert _APIAdapter.calls == 1

        stdout = capsys.readouterr().out
        assert "[progress:provider-fallback]" in stdout
        assert "from_provider=cli" in stdout
        assert "to_provider=api" in stdout

    def test_without_cli_api_fallback_flag_remains_fail_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _RawCLIProvider:
            pass

        class _FakeProviderFactory:
            def __init__(self, config: dict[str, object]) -> None:
                self._config = config

            def create(
                self,
                model: str,
                provider_name: str = "cli",
                api_key: str | None = None,
                cli_api_fallback_enabled: bool = False,
            ) -> SimpleNamespace:
                return SimpleNamespace(primary=_RawCLIProvider(), fallback=None)

        class _FailingCLIAdapter:
            calls = 0

            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                rate_limit_backoff: tuple[int, ...],
                transient_backoff: tuple[int, ...],
                use_segment_tags: bool = False,
            ) -> None:
                self._raw_provider = raw_provider

            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                _FailingCLIAdapter.calls += 1
                raise TranslationError("simulated transient transport failure")

        monkeypatch.setattr("ai.provider_factory.ProviderFactory", _FakeProviderFactory)
        monkeypatch.setattr(cli_module, "GeminiCLIAdapter", _FailingCLIAdapter)

        provider = create_provider(
            "cli",
            "gemini-2.5-flash",
            config={},
            cli_api_fallback=False,
        )

        with pytest.raises(TranslationError, match="simulated transient transport failure"):
            provider.translate_batch(["hello"], system_prompt="PROMPT")

        assert _FailingCLIAdapter.calls == 1

    def test_cli_api_fallback_does_not_trigger_on_generic_cli_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _RawCLIProvider:
            pass

        class _RawAPIProvider:
            pass

        class _FakeProviderFactory:
            def __init__(self, config: dict[str, object]) -> None:
                self._config = config

            def create(
                self,
                model: str,
                provider_name: str = "cli",
                api_key: str | None = None,
                cli_api_fallback_enabled: bool = False,
            ) -> SimpleNamespace:
                fallback = _RawAPIProvider() if cli_api_fallback_enabled else None
                return SimpleNamespace(primary=_RawCLIProvider(), fallback=fallback)

        class _FailingCLIAdapter:
            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                rate_limit_backoff: tuple[int, ...],
                transient_backoff: tuple[int, ...],
                use_segment_tags: bool = False,
            ) -> None:
                self._raw_provider = raw_provider

            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                raise TranslationError("Gemini CLI failed: model not found")

        class _APIAdapter:
            calls = 0

            def __init__(
                self,
                raw_provider: object,
                *,
                timeout_seconds: int,
                use_segment_tags: bool = False,
            ) -> None:
                self._raw_provider = raw_provider

            def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
                _APIAdapter.calls += 1
                return [f"api:{segment}" for segment in segments]

        monkeypatch.setattr("ai.provider_factory.ProviderFactory", _FakeProviderFactory)
        monkeypatch.setattr(cli_module, "GeminiCLIAdapter", _FailingCLIAdapter)
        monkeypatch.setattr(cli_module, "GeminiAPIAdapter", _APIAdapter)

        provider = create_provider(
            "cli",
            "gemini-2.5-flash",
            config={"gemini_api": {"api_key": "test-key"}},
            cli_api_fallback=True,
        )

        with pytest.raises(TranslationError, match="Gemini CLI failed: model not found"):
            provider.translate_batch(["hello"], system_prompt="PROMPT")
        assert _APIAdapter.calls == 0


# ── Argument parsing ──────────────────────────────────────────


class TestBuildParser:
    def test_minimal_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.input_path == "input.epub"
        assert args.output == "out.epub"
        assert args.output_lang == "zh"
        assert args.model == "gemini-2.5-flash"
        assert args.provider == "cli"
        assert args.prompt is None
        assert args.glossary is None
        assert args.resume is True
        assert args.force_resume is False
        assert args.checkpoint_dir is None

    def test_all_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "book.epub",
                "--output",
                "translated.epub",
                "--output-lang",
                "ja",
                "--model",
                "gemini-2.5-pro",
                "--provider",
                "api",
                "-p",
                "Use formal tone",
                "--glossary",
                "/path/to/glossary.json",
                "--glossary-min-priority",
                "high",
                "--glossary-max-terms",
                "30",
                "--cli-api-fallback",
                "--max-batch-chars",
                "30000",
                "--resume",
                "--force-resume",
                "--checkpoint-dir",
                "checkpoint-dir",
            ]
        )
        assert args.output_lang == "ja"
        assert args.model == "gemini-2.5-pro"
        assert args.provider == "api"
        assert args.prompt == "Use formal tone"
        assert args.glossary == "/path/to/glossary.json"
        assert args.glossary_min_priority == "high"
        assert args.glossary_max_terms == 30
        assert args.cli_api_fallback is True
        assert args.max_batch_chars == 30000
        assert args.resume is True
        assert args.force_resume is True
        assert args.checkpoint_dir == "checkpoint-dir"

    def test_short_prompt_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "-p", "Keep it short"])
        assert args.prompt == "Keep it short"

    def test_extract_glossary_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "--extract-glossary"])
        assert args.extract_glossary is True

    def test_no_resume_flag_disables_default_resume(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "--no-resume"])
        assert args.resume is False


class TestNoSanityProbeFlag:
    def test_no_sanity_probe_flag_present_in_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub", "--no-sanity-probe"])
        assert args.no_sanity_probe is True

    def test_no_sanity_probe_defaults_to_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.no_sanity_probe is False


class TestMainModelExplicitness:
    def test_main_marks_model_as_explicit_when_flag_is_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}
        monkeypatch.setattr(cli_module, "run", lambda **kwargs: captured.update(kwargs))

        cli_module.main(["book.epub", "--output", "translated.epub", "--model", "pro"])

        assert captured["model"] == "pro"
        assert captured["model_explicit"] is True

    def test_main_marks_model_as_implicit_when_flag_is_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}
        monkeypatch.setattr(cli_module, "run", lambda **kwargs: captured.update(kwargs))

        cli_module.main(["book.epub", "--output", "translated.epub"])

        assert captured["model"] == "gemini-2.5-flash"
        assert captured["model_explicit"] is False


class TestGlossaryModeParser:
    """Test --glossary-mode argument parsing."""

    def test_glossary_mode_deep_scan_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["input.epub", "--output", "out.epub", "--glossary-mode", "deep-scan"]
        )
        assert args.glossary_mode == "deep-scan"

    def test_glossary_mode_auto_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub", "--glossary-mode", "auto"])
        assert args.glossary_mode == "auto"

    def test_glossary_mode_defaults_to_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.glossary_mode is None

    def test_extract_glossary_leaves_glossary_mode_none(self) -> None:
        """--extract-glossary doesn't set glossary_mode (backward compat)."""
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub", "--extract-glossary"])
        assert args.extract_glossary is True
        assert args.glossary_mode is None


class TestGlossaryModeMainForwarding:
    """Test that glossary_mode flows through main() to run()."""

    def test_main_forwards_glossary_mode_deep_scan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}
        monkeypatch.setattr(cli_module, "run", lambda **kwargs: captured.update(kwargs))

        cli_module.main(
            ["book.epub", "--output", "translated.epub", "--glossary-mode", "deep-scan"]
        )

        assert captured["glossary_mode"] == "deep-scan"

    def test_main_forwards_glossary_mode_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}
        monkeypatch.setattr(cli_module, "run", lambda **kwargs: captured.update(kwargs))

        cli_module.main(["book.epub", "--output", "translated.epub", "--glossary-mode", "auto"])

        assert captured["glossary_mode"] == "auto"

    def test_main_forwards_glossary_mode_none_when_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}
        monkeypatch.setattr(cli_module, "run", lambda **kwargs: captured.update(kwargs))

        cli_module.main(["book.epub", "--output", "translated.epub"])

        assert captured["glossary_mode"] is None


# ── Format routing (parser) ──────────────────────────────────


class TestBuildParserFormatRouting:
    def test_input_format_default_is_auto(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.input_format == "auto"

    def test_input_format_markdown_with_directory(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "./pages_dir",
                "--output",
                "out.md",
                "--input-format",
                "markdown",
            ]
        )
        assert args.input_format == "markdown"
        assert args.input_path == "./pages_dir"

    def test_input_format_epub(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "book.epub",
                "--output",
                "out.epub",
                "--input-format",
                "epub",
            ]
        )
        assert args.input_format == "epub"


# ── Format detection ─────────────────────────────────────────


class TestDetectInputFormat:
    def test_epub_extension(self) -> None:
        assert detect_input_format("book.epub") == "epub"

    def test_md_extension(self) -> None:
        assert detect_input_format("page.md") == "markdown"

    def test_directory_detected_as_markdown(self, tmp_path: Path) -> None:
        assert detect_input_format(str(tmp_path)) == "markdown"

    def test_unknown_defaults_to_epub(self) -> None:
        assert detect_input_format("book.unknownext") == "epub"

    def test_pdf_extension(self) -> None:
        assert detect_input_format("report.pdf") == "pdf"


# ── Input validation ─────────────────────────────────────────


class TestRunInputValidation:
    def test_missing_input_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            run(
                input_path=str(tmp_path / "nonexistent.epub"),
                output=str(tmp_path / "out.epub"),
            )

    def test_empty_markdown_dir_raises(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="No page\\*.md files"):
            run(
                input_path=str(empty_dir),
                output=str(tmp_path / "out.md"),
                input_format="markdown",
            )

    def test_md_file_with_no_pages_in_parent_raises(self, tmp_path: Path) -> None:
        fake_input = tmp_path / "notes.md"
        fake_input.write_text("x")
        with pytest.raises(FileNotFoundError, match="No page\\*.md files"):
            run(
                input_path=str(fake_input),
                output=str(tmp_path / "out.md"),
                input_format="markdown",
            )


class _NoopSource:
    def get_segments(self) -> list[object]:
        return []

    def apply_translations(self, translated: list[object]) -> None:
        return None

    def save(self, output_path: str) -> None:
        Path(output_path).write_text("", encoding="utf-8")


class _NoopEngine:
    last_config: object | None = None
    last_provider: object | None = None

    def __init__(self, provider: object, config: object) -> None:
        self.provider = provider
        self.config = config
        _NoopEngine.last_provider = provider
        _NoopEngine.last_config = config

    def translate(
        self,
        source: object,
        output_path: str,
        *,
        on_batch_translated: object | None = None,
        on_source_loaded: object | None = None,
        on_batch_progress: object | None = None,
        on_before_save: object | None = None,
    ) -> object:
        Path(output_path).write_text("", encoding="utf-8")
        return SimpleNamespace(translated_segments=0, total_batches=0)


class TestRunModelResolutionSemantics:
    def test_run_uses_strict_resolution_for_explicit_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})

        resolve_calls: list[tuple[str, bool]] = []

        def fake_resolve_model(
            model_name: str,
            config: dict[str, object],
            *,
            explicit: bool = False,
        ) -> tuple[str, bool]:
            resolve_calls.append((model_name, explicit))
            if explicit and model_name == "pro":
                return ("gemini-2.5-pro", True)
            return ("gemini-2.5-flash", False)

        monkeypatch.setattr(cli_module, "resolve_model", fake_resolve_model)

        create_calls: list[str] = []

        def fake_create_provider(
            provider_name: str,
            model: str,
            *,
            is_pro: bool = False,
            use_segment_tags: bool = False,
            config: dict[str, object] | None = None,
            cli_api_fallback: bool = False,
        ) -> object:
            create_calls.append(model)
            return {"provider": provider_name, "model": model, "is_pro": is_pro}

        monkeypatch.setattr(cli_module, "create_provider", fake_create_provider)
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="pro",
            model_explicit=True,
            input_format="epub",
        )

        assert resolve_calls[0] == ("pro", True)
        assert create_calls[0] == "gemini-2.5-pro"

    def test_run_uses_60k_default_batch_size_for_epub_pro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model_name, config, *, explicit=False: ("gemini-2.5-pro", True),
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {
                "provider": args[0],
                "model": args[1],
                "is_pro": kwargs.get("is_pro", False),
            },
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="pro",
            model_explicit=True,
            input_format="epub",
        )

        assert _NoopEngine.last_config is not None
        assert getattr(_NoopEngine.last_config, "max_batch_chars") == 60_000

    def test_run_uses_60k_default_batch_size_for_epub_flash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model_name, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {
                "provider": args[0],
                "model": args[1],
                "is_pro": kwargs.get("is_pro", False),
            },
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="flash",
            model_explicit=True,
            input_format="epub",
        )

        assert _NoopEngine.last_config is not None
        assert getattr(_NoopEngine.last_config, "max_batch_chars") == 60_000

    def test_run_uses_configured_epub_batch_defaults_for_pro_and_flash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            cli_module,
            "load_config",
            lambda: {
                "epub_resilience": {
                    "pro_epub_max_batch_chars": 42000,
                    "standard_epub_max_batch_chars": 28000,
                }
            },
        )
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model_name, config, *, explicit=False: (
                ("gemini-2.5-pro", True) if model_name == "pro" else ("gemini-2.5-flash", False)
            ),
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {
                "provider": args[0],
                "model": args[1],
                "is_pro": kwargs.get("is_pro", False),
            },
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out-pro.epub"),
            model="pro",
            model_explicit=True,
            input_format="epub",
        )
        assert _NoopEngine.last_config is not None
        assert getattr(_NoopEngine.last_config, "max_batch_chars") == 42000

        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out-flash.epub"),
            model="flash",
            model_explicit=True,
            input_format="epub",
        )
        assert _NoopEngine.last_config is not None
        assert getattr(_NoopEngine.last_config, "max_batch_chars") == 28000

    def test_run_prints_auto_fallback_message_when_resolved_model_changes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})

        def fake_resolve_model(
            model_name: str,
            config: dict[str, object],
            *,
            explicit: bool = False,
        ) -> tuple[str, bool]:
            if explicit:
                return ("gemini-2.5-pro", True)
            return ("gemini-2.5-flash", False)

        monkeypatch.setattr(cli_module, "resolve_model", fake_resolve_model)
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {
                "provider": args[0],
                "model": args[1],
                "is_pro": kwargs.get("is_pro", False),
            },
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="pro",
            model_explicit=False,
            input_format="epub",
        )

        stdout = capsys.readouterr().out
        assert (
            "Auto model fallback: primary gemini-2.5-pro unavailable, using gemini-2.5-flash."
            in stdout
        )

    def test_run_does_not_print_auto_fallback_message_on_resolver_exception_fallback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})

        def fake_resolve_model(
            model_name: str,
            config: dict[str, object],
            *,
            explicit: bool = False,
        ) -> tuple[str, bool]:
            if explicit:
                return ("gemini-2.5-pro", True)
            # Simulate resolve_model exception fallback path: returns raw user input.
            return ("pro", True)

        monkeypatch.setattr(cli_module, "resolve_model", fake_resolve_model)
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {
                "provider": args[0],
                "model": args[1],
                "is_pro": kwargs.get("is_pro", False),
            },
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="pro",
            model_explicit=False,
            input_format="epub",
        )

        stdout = capsys.readouterr().out
        assert "Auto model fallback:" not in stdout


class TestRunGlossaryExtractionOrchestration:
    def _patch_base_runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: object())
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "PdfSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "MarkdownSourceAdapter", lambda path: _NoopSource())

    def test_epub_extract_glossary_generates_temp_glossary_and_injects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_base_runtime(monkeypatch)
        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        temp_dir = tmp_path / "book_temp"
        monkeypatch.setattr(cli_module, "_resolve_extraction_temp_dir", lambda input_path: temp_dir)

        extracted_path_calls: list[Path] = []

        def fake_extract(
            *,
            epub_path: Path,
            output_path: Path,
            provider_adapter: object,
            max_terms: int = 20,
            mode: str = "auto",
        ) -> dict:
            assert epub_path == in_epub
            extracted_path_calls.append(output_path)
            assert max_terms == 20
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '{"critical_terminology":[{"term":"API","suggested_translation":"接口","priority":"high"}]}',
                encoding="utf-8",
            )
            return {"tier": "index", "term_count": 1, "docs": 0, "chars": 100, "candidate_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        injected_glossary_paths: list[str | None] = []

        def fake_load_glossary(path: str | None, *, min_priority: str | None = None) -> str | None:
            injected_glossary_paths.append(path)
            return None

        monkeypatch.setattr(cli_module, "load_glossary_block", fake_load_glossary)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            extract_glossary=True,
        )

        expected = temp_dir / "extracted_glossary.json"
        assert extracted_path_calls == [expected]
        assert injected_glossary_paths == [str(expected)]

    def test_epub_extract_glossary_passes_glossary_max_terms(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_base_runtime(monkeypatch)
        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        temp_dir = tmp_path / "book_temp"
        monkeypatch.setattr(cli_module, "_resolve_extraction_temp_dir", lambda input_path: temp_dir)

        received_max_terms: list[int] = []

        def fake_extract(
            *,
            epub_path: Path,
            output_path: Path,
            provider_adapter: object,
            max_terms: int = 20,
            mode: str = "auto",
        ) -> dict:
            received_max_terms.append(max_terms)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")
            return {"tier": "index", "term_count": 0, "docs": 0, "chars": 0, "candidate_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            extract_glossary=True,
            glossary_max_terms=33,
        )

        assert received_max_terms == [33]

    def test_run_rejects_non_positive_glossary_max_terms(self, tmp_path: Path) -> None:
        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        with pytest.raises(ValueError, match="glossary_max_terms must be > 0"):
            run(
                input_path=str(in_epub),
                output=str(tmp_path / "out.epub"),
                input_format="epub",
                glossary_max_terms=0,
            )

    @pytest.mark.parametrize("fmt", ["pdf", "markdown"])
    def test_non_epub_extract_glossary_warns_and_ignores(
        self,
        fmt: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._patch_base_runtime(monkeypatch)

        if fmt == "pdf":
            input_path = tmp_path / "report.pdf"
            input_path.write_bytes(b"%PDF-1.4")
            output_path = tmp_path / "out.md"
        else:
            input_path = tmp_path / "md_dir"
            input_path.mkdir()
            (input_path / "page0001.md").write_text("hello", encoding="utf-8")
            output_path = tmp_path / "out.md"

        def fail_extract(**kwargs: object) -> None:
            raise AssertionError("extractor should not run for non-epub formats")

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fail_extract)

        run(
            input_path=str(input_path),
            output=str(output_path),
            input_format=fmt,
            extract_glossary=True,
        )

        stdout = capsys.readouterr().out
        # New code path uses mode-based warning
        assert (
            "Glossary extraction is only supported for EPUBs" in stdout
            or "only supported for EPUBs; skipping extraction" in stdout
        )

    def test_epub_extract_glossary_uses_pro_model_but_translation_stays_flash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})

        def fake_resolve_model(
            model_name: str, config: dict[str, object], *, explicit: bool = False
        ) -> tuple[str, bool]:
            if model_name == "pro":
                return ("gemini-2.5-pro", True)
            return ("gemini-2.5-flash", False)

        monkeypatch.setattr(cli_module, "resolve_model", fake_resolve_model)

        create_calls: list[str] = []

        def fake_create_provider(
            provider_name: str,
            model: str,
            *,
            is_pro: bool = False,
            use_segment_tags: bool = False,
            config: dict[str, object] | None = None,
            cli_api_fallback: bool = False,
        ) -> object:
            create_calls.append(model)
            return {"provider": provider_name, "model": model, "is_pro": is_pro}

        monkeypatch.setattr(cli_module, "create_provider", fake_create_provider)
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        temp_dir = tmp_path / "book_temp"
        monkeypatch.setattr(cli_module, "_resolve_extraction_temp_dir", lambda input_path: temp_dir)

        def fake_extract(
            *,
            epub_path: Path,
            output_path: Path,
            provider_adapter: object,
            max_terms: int = 20,
            mode: str = "auto",
        ) -> dict:
            assert isinstance(provider_adapter, dict)
            assert provider_adapter["model"] == "gemini-2.5-pro"
            assert max_terms == 20
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")
            return {"tier": "index", "term_count": 0, "docs": 0, "chars": 0, "candidate_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="gemini-2.5-flash",
            input_format="epub",
            extract_glossary=True,
        )

        assert create_calls == ["gemini-2.5-pro", "gemini-2.5-flash"]
        assert isinstance(_NoopEngine.last_provider, dict)
        assert _NoopEngine.last_provider["model"] == "gemini-2.5-flash"

    def test_legacy_extract_glossary_routes_through_mode_based_branch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression test: legacy --extract-glossary uses mode-based routing.

        resolve_glossary_request(extract_glossary=True) yields mode="auto",
        so the first mode-based branch handles it. The legacy elif branch
        with `extract_glossary and glossary_request.mode != "manual"` is
        unreachable dead code.

        This test verifies that extract_glossary=True routes through the
        correct mode="auto" path and extraction still happens.
        """
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module, "resolve_model", lambda name, config, *, explicit=False: (name, False)
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {"provider": "test"},
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        temp_dir = tmp_path / "book_temp"
        monkeypatch.setattr(cli_module, "_resolve_extraction_temp_dir", lambda input_path: temp_dir)

        extraction_happened = False
        received_mode = None

        def fake_extract(
            *,
            epub_path: Path,
            output_path: Path,
            provider_adapter: object,
            max_terms: int = 20,
            mode: str = "auto",
        ) -> dict:
            nonlocal extraction_happened, received_mode
            extraction_happened = True
            received_mode = mode
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")
            return {"tier": "index", "term_count": 0, "docs": 0, "chars": 0, "candidate_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        # Call with legacy extract_glossary=True (no explicit glossary_mode)
        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            extract_glossary=True,  # Legacy flag
        )

        # Verify extraction happened through mode-based branch
        assert extraction_happened, "Extraction should have been triggered"
        assert received_mode == "auto", "Legacy extract_glossary should map to mode='auto'"

    def test_run_passes_glossary_mode_to_extractor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() should pass glossary_mode from resolve_glossary_request to extractor."""
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module, "resolve_model", lambda name, config, *, explicit=False: (name, False)
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {"provider": "test"},
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        temp_dir = tmp_path / "book_temp"
        monkeypatch.setattr(cli_module, "_resolve_extraction_temp_dir", lambda input_path: temp_dir)

        extract_mode_received = None

        def fake_extract(
            *,
            epub_path: Path,
            output_path: Path,
            provider_adapter: object,
            max_terms: int = 20,
            mode: str = "auto",
        ) -> dict:
            nonlocal extract_mode_received
            extract_mode_received = mode
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")
            return {"tier": "index", "term_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="flash",
            input_format="epub",
            glossary_mode="deep-scan",
        )

        assert extract_mode_received == "deep-scan"

    def test_manual_glossary_skips_auto_extraction_even_when_mode_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When --glossary <path> is set, extraction should be skipped even if mode is auto/deep-scan."""
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module, "resolve_model", lambda name, config, *, explicit=False: (name, False)
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {"provider": "test"},
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        manual_glossary = tmp_path / "manual.json"
        manual_glossary.write_text('{"critical_terminology":[]}', encoding="utf-8")

        extract_called = False

        def fake_extract(*args: object, **kwargs: object) -> dict:
            nonlocal extract_called
            extract_called = True
            return {"tier": "none", "term_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="flash",
            input_format="epub",
            glossary=str(manual_glossary),
            glossary_mode="auto",  # Should be ignored because manual glossary provided
        )

        assert not extract_called, "Extraction should not run when manual glossary is provided"

    def test_manual_glossary_warns_when_overriding_extraction_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """When --glossary <path> overrides --extract-glossary or --glossary-mode, warn the user."""
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module, "resolve_model", lambda name, config, *, explicit=False: (name, False)
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {"provider": "test"},
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        manual_glossary = tmp_path / "manual.json"
        manual_glossary.write_text('{"critical_terminology":[]}', encoding="utf-8")

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="flash",
            input_format="epub",
            glossary=str(manual_glossary),
            extract_glossary=True,  # Should trigger warning
        )

        captured = capsys.readouterr()
        assert "manual glossary" in captured.out.lower() or "override" in captured.out.lower()

    def test_non_epub_deep_scan_warns_and_skips_extraction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """When glossary_mode is auto/deep-scan but input is not EPUB, warn and skip extraction."""
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module, "resolve_model", lambda name, config, *, explicit=False: (name, False)
        )
        monkeypatch.setattr(
            cli_module,
            "create_provider",
            lambda *args, **kwargs: {"provider": "test"},
        )
        monkeypatch.setattr(cli_module, "TranslationEngine", _NoopEngine)
        monkeypatch.setattr(cli_module, "build_system_prompt", lambda *args, **kwargs: "PROMPT")
        monkeypatch.setattr(cli_module, "MarkdownSourceAdapter", lambda path: _NoopSource())
        monkeypatch.setattr(cli_module, "load_glossary_block", lambda *args, **kwargs: None)

        # Create markdown directory with page files
        in_md_dir = tmp_path / "md_dir"
        in_md_dir.mkdir()
        (in_md_dir / "page0001.md").write_text("# Title\nContent", encoding="utf-8")
        out_file = tmp_path / "out.md"

        extract_called = False

        def fake_extract(*args: object, **kwargs: object) -> dict:
            nonlocal extract_called
            extract_called = True
            return {"tier": "none", "term_count": 0}

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_md_dir),
            output=str(out_file),
            model="flash",
            input_format="markdown",
            glossary_mode="deep-scan",
        )

        assert not extract_called, "Extraction should not run for non-EPUB input"
        captured = capsys.readouterr()
        assert "epub" in captured.out.lower() and (
            "skip" in captured.out.lower() or "warn" in captured.out.lower()
        )


class _ResumeProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
        batch = list(segments)
        self.calls.append(batch)
        return [f"翻译:{item}" for item in batch]


class _ResumeSource:
    def __init__(self) -> None:
        self.applied: list[TranslatedSegment] | None = None
        self.saved_to: str | None = None
        self._segments = [
            Segment(id="chapter1.xhtml::0", text="A", metadata={"doc_path": "chapter1.xhtml"}),
            Segment(id="chapter1.xhtml::1", text="B", metadata={"doc_path": "chapter1.xhtml"}),
            Segment(id="chapter2.xhtml::0", text="C", metadata={"doc_path": "chapter2.xhtml"}),
        ]

    def get_segments(self) -> list[Segment]:
        return list(self._segments)

    def apply_translations(self, translated: list[TranslatedSegment]) -> None:
        self.applied = translated

    def save(self, output_path: str) -> None:
        self.saved_to = output_path
        Path(output_path).write_text("", encoding="utf-8")


class _EmptyTranslationProvider:
    """Provider that always returns empty translations — used to trigger probe guards."""

    def translate_batch(self, segments: list[str], *, system_prompt: str) -> list[str]:
        return [""] * len(segments)


class TestRunSanityProbe:
    """Verifies that run() wires the sanity probe into the on_checkpoint_batch callback."""

    def _patch_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
        source: _ResumeSource,
        provider: object,
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: provider)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: source)

    def test_run_emits_batch_sample_lines(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_base(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        run(input_path=str(in_epub), output=str(tmp_path / "out.epub"), input_format="epub")

        out = capsys.readouterr().out
        # _ResumeSource has 3 segments planned into 2 batches
        assert out.count("[progress:batch_sample]") == 2

    def test_run_halts_on_empty_translation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        self._patch_base(monkeypatch, source, _EmptyTranslationProvider())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        with pytest.raises(TranslationError, match="empty output"):
            run(input_path=str(in_epub), output=str(tmp_path / "out.epub"), input_format="epub")

    def test_no_sanity_probe_flag_suppresses_probe_and_sample(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        self._patch_base(monkeypatch, source, _EmptyTranslationProvider())

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        # With probe disabled, empty output should NOT raise
        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out.epub"),
            input_format="epub",
            no_sanity_probe=True,
        )

        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out

    def test_probe_disabled_via_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        self._patch_base(monkeypatch, source, _EmptyTranslationProvider())
        monkeypatch.setattr(
            cli_module,
            "load_config",
            lambda: {"sanity_probe": {"enabled": False}},
        )

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        run(
            input_path=str(in_epub),
            output=str(tmp_path / "out.epub"),
            input_format="epub",
        )

        out = capsys.readouterr().out
        assert "[progress:batch_sample]" not in out


class TestRunResumeCheckpoint:
    def _patch_runtime_for_resume(
        self,
        monkeypatch: pytest.MonkeyPatch,
        source: _ResumeSource,
        provider: _ResumeProvider,
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: provider)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: source)

    def _write_partial_checkpoint(
        self,
        *,
        checkpoint_dir: Path,
        input_epub: Path,
        output_lang: str = "zh",
        model: str = "gemini-2.5-flash",
        segmenter_signature: str | None = "epub-leaf-block-v2",
    ) -> None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        system_prompt = build_system_prompt("Chinese", immersive=True)
        state = {
            "schema_version": 1,
            "input_signature": cli_module._compute_input_signature(input_epub),
            "input_format": "epub",
            "output_lang": output_lang,
            "model": model,
            "provider": "cli",
            "max_batch_chars": 60000,
            "separator_overhead": cli_module.SEPARATOR_OVERHEAD,
            "system_prompt_hash": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "translated_segment_count": 1,
        }
        if segmenter_signature is not None:
            state["segmenter_signature"] = segmenter_signature
        (checkpoint_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (checkpoint_dir / "translations.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "segments": {"chapter1.xhtml::0": "缓存:A"},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def test_run_resume_skips_translated_segments_from_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp"
        self._write_partial_checkpoint(checkpoint_dir=checkpoint_dir, input_epub=in_epub)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        assert provider.calls == [["B"], ["C"]]
        assert source.applied is not None
        assert [item.translated for item in source.applied] == ["缓存:A", "翻译:B", "翻译:C"]

    def test_run_force_resume_allows_model_mismatch_checkpoint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp_force"
        self._write_partial_checkpoint(
            checkpoint_dir=checkpoint_dir,
            input_epub=in_epub,
            model="gemini-2.5-pro",
        )

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            force_resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        assert provider.calls == [["B"], ["C"]]

    def test_run_resume_rejects_incompatible_checkpoint_without_force(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp_strict"
        self._write_partial_checkpoint(
            checkpoint_dir=checkpoint_dir,
            input_epub=in_epub,
            model="gemini-2.5-pro",
        )

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        assert provider.calls == [["A", "B"], ["C"]]

    def test_run_resume_rejects_checkpoint_when_segmenter_signature_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp_missing_segmenter_signature"
        self._write_partial_checkpoint(
            checkpoint_dir=checkpoint_dir,
            input_epub=in_epub,
            segmenter_signature=None,
        )

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        assert provider.calls == [["A", "B"], ["C"]]

    def test_run_resume_rejects_checkpoint_when_segmenter_signature_mismatches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp_mismatched_segmenter_signature"
        self._write_partial_checkpoint(
            checkpoint_dir=checkpoint_dir,
            input_epub=in_epub,
            segmenter_signature="epub-div-block-v1",
        )

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        assert provider.calls == [["A", "B"], ["C"]]

    def test_run_resume_uses_stable_default_checkpoint_layout(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_resume(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_dir = tmp_path / "book_temp"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "translated_roundtrip.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
        )

        checkpoint_dir = out_dir / ".bookweaver_checkpoints" / "epub" / "book"
        state_file = checkpoint_dir / "state.json"
        translations_file = checkpoint_dir / "translations.json"
        assert state_file.exists()
        assert translations_file.exists()

        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["schema_version"] == 1
        assert state["input_format"] == "epub"
        assert state["segmenter_signature"] == cli_module._EPUB_SEGMENTER_SIGNATURE
        assert state["translated_segment_count"] == 3

        translations = json.loads(translations_file.read_text(encoding="utf-8"))
        assert set(translations["segments"]) == {
            "chapter1.xhtml::0",
            "chapter1.xhtml::1",
            "chapter2.xhtml::0",
        }


class TestRunProgressLogging:
    def _patch_runtime_for_epub_progress(
        self,
        monkeypatch: pytest.MonkeyPatch,
        source: _ResumeSource,
        provider: _ResumeProvider,
    ) -> None:
        monkeypatch.setattr(cli_module, "load_config", lambda: {})
        monkeypatch.setattr(
            cli_module,
            "resolve_model",
            lambda model, config, *, explicit=False: ("gemini-2.5-flash", False),
        )
        monkeypatch.setattr(cli_module, "create_provider", lambda *args, **kwargs: provider)
        monkeypatch.setattr(cli_module, "EpubSourceAdapter", lambda path: source)

    def test_run_logs_progress_contract_for_epub(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_epub_progress(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
        )

        stdout = capsys.readouterr().out
        assert re.search(
            r"\[progress:model\].*requested=.*resolved=.*tier=.*explicit=",
            stdout,
        )
        assert re.search(r"\[progress:source\].*segments=3", stdout)
        assert re.search(r"\[progress:batch\].*index=1/2", stdout)
        assert re.search(r"\[progress:batch\].*translated=0/3", stdout)
        assert re.search(r"\[progress:batch\].*batch_segments=2", stdout)
        assert re.search(r"\[progress:batch\].*docs=chapter1.xhtml", stdout)
        assert re.search(r"\[progress:batch\].*index=2/2", stdout)
        assert re.search(r"\[progress:batch\].*translated=2/3", stdout)
        assert re.search(r"\[progress:batch\].*batch_segments=1", stdout)
        assert re.search(r"\[progress:batch\].*docs=chapter2.xhtml", stdout)
        assert re.search(r"\[progress:save\].*segments=3", stdout)
        assert re.search(r"\[progress:done\].*segments=3.*batches=2.*resumed=0", stdout)

    def test_run_logs_resumed_context_when_checkpoint_loaded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_epub_progress(monkeypatch, source, provider)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")
        out_file = tmp_path / "out.epub"
        checkpoint_dir = tmp_path / "resume_cp_logs"
        TestRunResumeCheckpoint()._write_partial_checkpoint(
            checkpoint_dir=checkpoint_dir,
            input_epub=in_epub,
        )

        run(
            input_path=str(in_epub),
            output=str(out_file),
            input_format="epub",
            resume=True,
            checkpoint_dir=str(checkpoint_dir),
        )

        stdout = capsys.readouterr().out
        assert re.search(r"\[progress:resume\].*restored_segments=1", stdout)
        assert re.search(r"\[progress:source\].*resumed=1", stdout)

    def test_run_logs_failure_stage_before_exception(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class _FailingEngine:
            def __init__(self, provider: object, config: object) -> None:
                self.provider = provider
                self.config = config

            def translate(
                self,
                source: object,
                output_path: str,
                *,
                on_batch_translated: object | None = None,
                on_source_loaded: object | None = None,
                on_batch_progress: object | None = None,
                on_before_save: object | None = None,
            ) -> object:
                if callable(on_source_loaded):
                    on_source_loaded(3, 0, 1)
                raise RuntimeError("simulated engine failure")

        source = _ResumeSource()
        provider = _ResumeProvider()
        self._patch_runtime_for_epub_progress(monkeypatch, source, provider)
        monkeypatch.setattr(cli_module, "TranslationEngine", _FailingEngine)

        in_epub = tmp_path / "book.epub"
        in_epub.write_bytes(b"epub")

        with pytest.raises(RuntimeError, match="simulated engine failure"):
            run(
                input_path=str(in_epub),
                output=str(tmp_path / "out.epub"),
                input_format="epub",
            )

        captured = capsys.readouterr()
        assert "[progress:translate]" in captured.out
        assert "[progress:error] stage=translate" in captured.err
