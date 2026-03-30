from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.core.glossary import GlossaryManager, validate_model_output


def _write_glossary(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_from_json_requires_critical_terminology_key(tmp_path: Path) -> None:
    wrong = _write_glossary(tmp_path, {"wrong": []})

    with pytest.raises(ValueError, match="missing 'critical_terminology'"):
        GlossaryManager.from_json_file(wrong)


def test_load_from_json_formats_block_sorted_by_priority(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        {
            "critical_terminology": [
                {"term": "B", "suggested_translation": "乙", "priority": "medium"},
                {"term": "A", "suggested_translation": "甲", "priority": "critical"},
            ]
        },
    )

    block = GlossaryManager.from_json_file(path).format_block()

    assert "A → 甲" in block
    assert "B → 乙" in block
    assert block.index("A → 甲") < block.index("B → 乙")


def test_format_block_respects_min_priority_filter(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        {
            "critical_terminology": [
                {"term": "C", "suggested_translation": "丙", "priority": "critical"},
                {"term": "H", "suggested_translation": "高", "priority": "high"},
                {"term": "M", "suggested_translation": "中", "priority": "medium"},
            ]
        },
    )

    block = GlossaryManager.from_json_file(path).format_block(min_priority="high")

    assert "C → 丙" in block
    assert "H → 高" in block
    assert "M → 中" not in block


def test_validate_model_output_strips_markdown_fence_and_parses() -> None:
    parsed = validate_model_output('```json\n{"critical_terminology":[]}\n```')
    assert parsed == {"critical_terminology": []}


def test_validate_model_output_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        validate_model_output("not json")


def test_load_from_json_rejects_non_dict_term_entry_with_index(tmp_path: Path) -> None:
    path = _write_glossary(
        tmp_path,
        {
            "critical_terminology": [
                {"term": "A", "suggested_translation": "甲", "priority": "critical"},
                "invalid",
            ]
        },
    )

    with pytest.raises(ValueError, match=r"critical_terminology\[1\]"):
        GlossaryManager.from_json_file(path)
