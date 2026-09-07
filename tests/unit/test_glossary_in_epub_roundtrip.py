from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.orchestration import build_system_prompt, load_glossary_block
from ai.glossary_injector import GlossaryInjector


def _write_glossary(tmp_path: Path) -> Path:
    glossary = {
        "critical_terminology": [
            {
                "term": "Connascence",
                "suggested_translation": "共生性",
                "negative_constraint": "NOT 并发性",
                "priority": "critical",
            },
            {
                "term": "Shift Left",
                "suggested_translation": "左移",
                "negative_constraint": "NOT 左边",
                "priority": "high",
            },
            {
                "term": "Tech Debt",
                "suggested_translation": "技术债务",
                "negative_constraint": "",
                "priority": "medium",
            },
        ]
    }
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps(glossary), encoding="utf-8")
    return path


def test_load_glossary_block_filters_priority_for_prompt_budget(tmp_path: Path) -> None:
    gpath = _write_glossary(tmp_path)

    filtered = load_glossary_block(str(gpath), min_priority="high")

    assert filtered is not None
    assert "Connascence" in filtered
    assert "Shift Left" in filtered
    assert "Tech Debt" not in filtered


def test_build_system_prompt_places_glossary_before_custom_instructions(tmp_path: Path) -> None:
    gpath = _write_glossary(tmp_path)
    glossary_block = load_glossary_block(str(gpath))
    prompt = build_system_prompt(
        "Chinese",
        glossary_block=glossary_block,
        custom_prompt="Preserve code blocks and URLs exactly.",
    )

    glossary_idx = prompt.find("【关键术语约束】")
    custom_idx = prompt.find("ADDITIONAL INSTRUCTIONS")

    assert glossary_idx != -1
    assert custom_idx != -1
    assert glossary_idx < custom_idx
    assert "Connascence" in prompt
    assert "共生性" in prompt


def test_build_system_prompt_without_glossary_omits_terminology_block() -> None:
    prompt = build_system_prompt("Chinese", custom_prompt="No glossary for this run.")

    assert "【关键术语约束】" not in prompt
    assert "ADDITIONAL INSTRUCTIONS" in prompt


def test_glossary_injector_and_cli_loader_produce_consistent_glossary_block(
    tmp_path: Path,
) -> None:
    gpath = _write_glossary(tmp_path)

    via_injector = GlossaryInjector(gpath).format_block(min_priority="critical")
    via_cli = load_glossary_block(str(gpath), min_priority="critical")

    assert via_cli == via_injector
    assert via_cli is not None
    assert "Connascence" in via_cli
    assert "Shift Left" not in via_cli


def test_load_glossary_block_with_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Glossary file not found"):
        load_glossary_block(str(missing))
