"""Unit tests for ai.cli — the composition root.

Tests prompt assembly, argument parsing, and model resolution.
Does NOT test actual translation (that's covered by engine + adapter tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.cli import build_parser, build_system_prompt, detect_input_format, run, _get_language_name


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


# ── Language resolution ───────────────────────────────────────


class TestLanguageResolution:
    def test_known_codes(self) -> None:
        assert _get_language_name("zh") == "Chinese"
        assert _get_language_name("en") == "English"
        assert _get_language_name("ja") == "Japanese"

    def test_unknown_code_returns_itself(self) -> None:
        assert _get_language_name("xx") == "xx"


# ── Argument parsing ──────────────────────────────────────────


class TestBuildParser:
    def test_minimal_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.input_epub == "input.epub"
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
        assert args.cli_api_fallback is True
        assert args.max_batch_chars == 30000

    def test_short_prompt_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["in.epub", "--output", "out.epub", "-p", "Keep it short"])
        assert args.prompt == "Keep it short"


# ── Format routing (parser) ──────────────────────────────────


class TestBuildParserFormatRouting:
    def test_input_format_default_is_auto(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["input.epub", "--output", "out.epub"])
        assert args.input_format == "auto"

    def test_input_format_markdown(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "input.md",
                "--output",
                "out.epub",
                "--input-format",
                "markdown",
                "--markdown-dir",
                "/pages",
            ]
        )
        assert args.input_format == "markdown"
        assert args.markdown_dir == "/pages"

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

    def test_unknown_defaults_to_epub(self) -> None:
        assert detect_input_format("book.pdf") == "epub"


# ── Input validation ─────────────────────────────────────────


class TestRunInputValidation:
    def test_missing_input_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            run(
                input_path=str(tmp_path / "nonexistent.epub"),
                output=str(tmp_path / "out.epub"),
            )

    def test_missing_markdown_dir_raises(self, tmp_path: Path) -> None:
        fake_input = tmp_path / "input.md"
        fake_input.write_text("x")
        with pytest.raises(FileNotFoundError, match="directory does not exist"):
            run(
                input_path=str(fake_input),
                output=str(tmp_path / "out.md"),
                input_format="markdown",
                markdown_dir=str(tmp_path / "no_such_dir"),
            )

    def test_empty_markdown_dir_raises(self, tmp_path: Path) -> None:
        fake_input = tmp_path / "input.md"
        fake_input.write_text("x")
        with pytest.raises(FileNotFoundError, match="No page\\*.md files"):
            run(
                input_path=str(fake_input),
                output=str(tmp_path / "out.md"),
                input_format="markdown",
                markdown_dir=str(tmp_path),
            )
