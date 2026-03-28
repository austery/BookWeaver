from __future__ import annotations

import json
import re
from pathlib import Path

from ai.epub_translate_roundtrip import _create_translation_prompt
from ai.glossary_injector import GlossaryInjector


def _write_glossary(tmp_path: Path) -> Path:
    data = {
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "negative_constraint": "NOT 并发性",
                "reason": "author concept",
                "priority": "critical",
            }
        ]
    }
    p = tmp_path / "glossary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_create_translation_prompt_with_glossary(tmp_path: Path) -> None:
    """_create_translation_prompt includes glossary content when glossary provided."""
    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt("zh", None, segment_count=1, glossary=glossary_block)
    assert "Connascence" in prompt
    assert "共生性" in prompt


def test_create_translation_prompt_no_glossary() -> None:
    """_create_translation_prompt works unchanged when no glossary given."""
    prompt = _create_translation_prompt("zh", None, segment_count=1, glossary=None)
    assert "Connascence" not in prompt
    assert isinstance(prompt, str)
    assert len(prompt) > 0


# ── TDD: Prompt pollution prevention ────────────────────────────────


def test_glossary_block_before_translate_marker(tmp_path: Path) -> None:
    """Glossary block MUST appear BEFORE 'Translate to' marker in prompt.

    Root cause of prompt pollution: when glossary sits after 'Translate to X:',
    the CLI provider concatenates prompt + source text, making Gemini see the
    glossary as content to translate rather than instructions.
    """
    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt("zh", None, segment_count=5, glossary=glossary_block)

    # Find positions
    translate_marker = re.search(r"Translate to .+:", prompt)
    glossary_pos = prompt.find("关键术语约束")

    assert translate_marker is not None, "Prompt must contain 'Translate to X:' marker"
    assert glossary_pos != -1, "Prompt must contain glossary block"
    assert glossary_pos < translate_marker.start(), (
        f"Glossary (pos={glossary_pos}) must appear BEFORE 'Translate to' marker "
        f"(pos={translate_marker.start()}) to prevent prompt pollution. "
        f"When glossary is after the marker, CLI provider sends it as content to translate."
    )


def test_glossary_block_before_translate_marker_single_segment(tmp_path: Path) -> None:
    """Same rule applies for single-segment prompts."""
    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt("zh", None, segment_count=1, glossary=glossary_block)

    translate_marker = re.search(r"Translate to .+:", prompt)
    glossary_pos = prompt.find("关键术语约束")

    assert translate_marker is not None
    assert glossary_pos != -1
    assert glossary_pos < translate_marker.start(), (
        "Glossary must appear before 'Translate to' marker for single-segment too"
    )


def test_custom_prompt_before_translate_marker() -> None:
    """Custom prompt (ADDITIONAL INSTRUCTIONS) must also come before 'Translate to' marker."""
    prompt = _create_translation_prompt(
        "zh", "Keep all code blocks intact.", segment_count=3, glossary=None
    )

    translate_marker = re.search(r"Translate to .+:", prompt)
    custom_pos = prompt.find("ADDITIONAL INSTRUCTIONS")

    assert translate_marker is not None
    assert custom_pos != -1
    assert custom_pos < translate_marker.start(), (
        "Custom prompt must appear before 'Translate to' marker to prevent pollution"
    )


def test_glossary_and_custom_prompt_both_before_translate_marker(tmp_path: Path) -> None:
    """When both glossary and custom prompt exist, both must precede the translate marker."""
    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt(
        "zh", "Preserve formatting.", segment_count=10, glossary=glossary_block
    )

    translate_marker = re.search(r"Translate to .+:", prompt)
    glossary_pos = prompt.find("关键术语约束")
    custom_pos = prompt.find("ADDITIONAL INSTRUCTIONS")

    assert translate_marker is not None
    assert glossary_pos != -1
    assert custom_pos != -1
    assert glossary_pos < translate_marker.start()
    assert custom_pos < translate_marker.start()


def test_translate_marker_is_last_instruction_in_prompt(tmp_path: Path) -> None:
    """'Translate to X:' must be the very last line of the prompt.

    This ensures the CLI provider places it right before the source text,
    creating a clean boundary between instructions and content.
    """
    gpath = _write_glossary(tmp_path)
    injector = GlossaryInjector(gpath)
    glossary_block = injector.format_block()

    prompt = _create_translation_prompt(
        "zh", "Extra instructions.", segment_count=5, glossary=glossary_block
    )

    # The prompt should end with the "Translate to X:" line (possibly trailing whitespace)
    lines = [line for line in prompt.strip().split("\n") if line.strip()]
    last_line = lines[-1].strip()
    assert re.match(r"Translate to .+:", last_line), (
        f"Last line of prompt should be 'Translate to X:' but got: '{last_line}'"
    )
