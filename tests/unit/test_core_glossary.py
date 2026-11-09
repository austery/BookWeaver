from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.core.glossary import (
    GlossaryManager,
    keep_first_translation,
    measure_term_usage,
    validate_model_output,
)


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


def test_keep_first_translation_leaves_one_option_and_names_the_changed_terms() -> None:
    data: dict[str, object] = {
        "critical_terminology": [
            {"term": "Estrangement", "suggested_translation": "疏离 / 隔阂", "priority": "high"},
            {"term": "Humane", "suggested_translation": "人道／仁慈", "priority": "high"},
            {"term": "General will", "suggested_translation": "公意", "priority": "high"},
        ]
    }

    result, changed = keep_first_translation(data)

    terms = result["critical_terminology"]
    assert isinstance(terms, list)
    assert [term["suggested_translation"] for term in terms] == ["疏离", "人道", "公意"]
    assert changed == ["Estrangement", "Humane"]


@pytest.mark.parametrize(
    "term,translation",
    [
        ("I/O", "输入/输出"),
        ("I/O", "输入 / 输出"),
        ("read-write", "读/写"),
        ("Supply and demand", "供给/需求"),
        ("CRUD", "增/删/改/查"),
        ("Network stack", "TCP/IP 协议栈"),
    ],
)
def test_keep_first_translation_keeps_a_slash_that_belongs_to_the_translation(
    term: str, translation: str
) -> None:
    data: dict[str, object] = {
        "critical_terminology": [{"term": term, "suggested_translation": translation}]
    }

    result, changed = keep_first_translation(data)

    assert result == data
    assert changed == []


@pytest.mark.parametrize("translation", ["疏离/隔阂", "疏离 / 隔阂", "疏离／隔阂", "疏离 ／ 隔阂"])
def test_keep_first_translation_splits_every_form_of_alternatives(translation: str) -> None:
    data: dict[str, object] = {
        "critical_terminology": [{"term": "Estrangement", "suggested_translation": translation}]
    }

    result, changed = keep_first_translation(data)

    terms = result["critical_terminology"]
    assert isinstance(terms, list)
    assert terms[0]["suggested_translation"] == "疏离"
    assert changed == ["Estrangement"]


def test_keep_first_translation_ignores_malformed_entries() -> None:
    data: dict[str, object] = {"critical_terminology": ["bad", {"term": "x"}]}

    assert keep_first_translation(data) == (data, [])


def test_measure_term_usage_counts_each_option_and_each_missing_segment() -> None:
    terms: list[dict[str, object]] = [
        {"term": "Leap of faith", "suggested_translation": "信仰的跃进 / 信仰之跃"},
        {"term": "art", "suggested_translation": "艺术"},
        {"term": "Absent", "suggested_translation": "缺席"},
    ]
    pairs = [
        ("a LEAP OF  faith here", "信仰的跃进"),
        ("the leap of faith", "信仰之跃"),
        ("another leap of faith", "别的说法"),
        ("the party met", "聚会"),
        ("art and party", "艺术"),
    ]

    usage = {item.term: item for item in measure_term_usage(terms, pairs)}

    leap = usage["Leap of faith"]
    assert (leap.segments, leap.option_counts, leap.missing) == (
        3,
        {"信仰的跃进": 1, "信仰之跃": 1},
        1,
    )
    assert not leap.consistent
    assert (usage["art"].segments, usage["art"].missing) == (1, 0)
    assert usage["art"].consistent
    assert usage["Absent"].segments == 0
    assert usage["Absent"].consistent


def test_measure_term_usage_does_not_count_a_shorter_option_inside_a_longer_one() -> None:
    terms: list[dict[str, object]] = [
        {"term": "Philosophy of mind", "suggested_translation": "心灵 / 心灵哲学"}
    ]

    usage = measure_term_usage(terms, [("philosophy of mind", "讨论心灵哲学")])

    assert usage[0].option_counts == {"心灵": 0, "心灵哲学": 1}
    assert usage[0].consistent


def test_keep_first_translation_splits_spaced_alternatives_for_a_hyphenated_term() -> None:
    data: dict[str, object] = {
        "critical_terminology": [
            {
                "term": "Trade-union consciousness",
                "suggested_translation": "工联主义意识 / 工联意识",
            }
        ]
    }

    result, changed = keep_first_translation(data)

    terms = result["critical_terminology"]
    assert isinstance(terms, list)
    assert terms[0]["suggested_translation"] == "工联主义意识"
    assert changed == ["Trade-union consciousness"]
