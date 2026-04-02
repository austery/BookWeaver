"""Unit tests for ai.cli — the composition root.

Tests prompt assembly, argument parsing, and model resolution.
Does NOT test actual translation (that's covered by engine + adapter tests).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ai.cli as cli_module
from ai.cli import (
    build_parser,
    build_system_prompt,
    create_provider,
    detect_input_format,
    load_config,
    load_glossary_block,
    run,
    _get_language_name,
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
            ) -> None:
                captured["raw_provider_type"] = type(raw_provider).__name__
                captured["timeout_seconds"] = timeout_seconds
                captured["rate_limit_backoff"] = rate_limit_backoff
                captured["transient_backoff"] = transient_backoff

        import ai.gemini_provider as gemini_provider_module

        monkeypatch.setattr(gemini_provider_module, "GeminiProvider", _FakeGeminiProvider)
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

    def test_create_provider_rejects_non_positive_transient_backoff_values(self) -> None:
        with pytest.raises(ValueError, match="transient_backoff_seconds"):
            create_provider(
                "cli",
                "gemini-2.5-flash",
                config={"epub_resilience": {"transient_backoff_seconds": [4, 0]}},
            )


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

    def test_short_prompt_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "-p", "Keep it short"])
        assert args.prompt == "Keep it short"

    def test_extract_glossary_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "--extract-glossary"])
        assert args.extract_glossary is True


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
        ) -> None:
            assert epub_path == in_epub
            extracted_path_calls.append(output_path)
            assert max_terms == 20
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '{"critical_terminology":[{"term":"API","suggested_translation":"接口","priority":"high"}]}',
                encoding="utf-8",
            )

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
        ) -> None:
            received_max_terms.append(max_terms)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")

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
        assert "Glossary extraction is only supported for EPUBs" in stdout

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
        ) -> None:
            assert isinstance(provider_adapter, dict)
            assert provider_adapter["model"] == "gemini-2.5-pro"
            assert max_terms == 20
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"critical_terminology":[]}', encoding="utf-8")

        monkeypatch.setattr(cli_module, "_extract_glossary_to_path", fake_extract)

        run(
            input_path=str(in_epub),
            output=str(out_file),
            model="gemini-2.5-flash",
            input_format="epub",
            extract_glossary=True,
        )

        assert create_calls == ["gemini-2.5-flash", "gemini-2.5-pro"]
        assert isinstance(_NoopEngine.last_provider, dict)
        assert _NoopEngine.last_provider["model"] == "gemini-2.5-flash"
