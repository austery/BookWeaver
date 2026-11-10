from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.core.glossary import (
    GlossaryManager,
    measure_term_usage,
    terms_with_a_slash,
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


def test_terms_with_a_slash_names_terms_and_changes_nothing() -> None:
    data: dict[str, object] = {
        "critical_terminology": [
            {"term": "Estrangement", "suggested_translation": "疏离 / 隔阂"},
            {"term": "client–server architecture", "suggested_translation": "客户端/服务器架构"},
            {"term": "Humane", "suggested_translation": "人道／仁慈"},
            {"term": "General will", "suggested_translation": "公意"},
            "bad",
            {"term": "No translation"},
        ]
    }
    before = json.dumps(data, ensure_ascii=False)

    assert terms_with_a_slash(data) == [
        "Estrangement",
        "client–server architecture",
        "Humane",
    ]
    assert json.dumps(data, ensure_ascii=False) == before


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


def test_measure_term_usage_treats_a_whole_compound_translation_as_one_choice() -> None:
    terms: list[dict[str, object]] = [
        {"term": "client-server", "suggested_translation": "客户端/服务器架构"}
    ]

    usage = measure_term_usage(terms, [("a client-server design", "一种客户端/服务器架构设计")])

    assert usage[0].missing == 0
    assert usage[0].consistent


def test_measure_term_usage_counts_alternatives_as_other_choices() -> None:
    terms: list[dict[str, object]] = [
        {"term": "Estrangement", "suggested_translation": "疏离", "alternatives": ["隔阂"]}
    ]

    usage = measure_term_usage(terms, [("estrangement", "疏离"), ("estrangement again", "隔阂")])

    assert usage[0].option_counts == {"疏离": 1, "隔阂": 1}
    assert usage[0].missing == 0
    assert not usage[0].consistent


def test_measure_term_usage_skips_a_term_with_no_translation() -> None:
    terms: list[dict[str, object]] = [{"term": "Estrangement", "suggested_translation": " "}]

    assert measure_term_usage(terms, [("estrangement", "任何译文")]) == []


_TIERLESS = {
    "critical_terminology": [
        {
            "term": "Estrangement",
            "suggested_translation": "疏离",
            "alternatives": ["隔阂"],
            "negative_constraint": "NOT 异化",
            "priority": "critical",
        },
        {
            "term": "Uniformity",
            "suggested_translation": "整齐划一",
            "alternatives": ["一律化"],
            "priority": "medium",
        },
        {"term": "Thrasymachus", "suggested_translation": "色拉叙马霍斯", "priority": "high"},
    ]
}


def test_a_glossary_without_tiers_renders_the_same_bytes_as_before_tiers() -> None:
    """Saved books resume only if their glossary block is byte-identical (SPEC-028 §3.5)."""
    block = GlossaryManager.from_dict(_TIERLESS).format_block()

    assert block == (
        "【关键术语约束】以下术语必须严格遵守标准译法：\n"
        "  • Estrangement → 疏离（NOT 异化）\n"
        "  • Thrasymachus → 色拉叙马霍斯\n"
        "  • Uniformity → 整齐划一"
    )


def _tiered() -> dict[str, object]:
    terms = [dict(entry) for entry in _TIERLESS["critical_terminology"]]
    terms[1]["tier"] = "preferred"
    terms[2]["tier"] = "fixed"
    terms.append(
        {
            "term": "Cosmic morale",
            "suggested_translation": "宇宙士气",
            "alternatives": ["面对宇宙的精神底气", "宇宙信念"],
            "negative_constraint": "NOT 宇宙道德",
            "tier": "preferred",
            "priority": "high",
        }
    )
    return {"critical_terminology": terms}


def test_preferred_terms_get_their_own_block_with_alternatives() -> None:
    block = GlossaryManager.from_dict(_tiered()).format_block()

    strict, suggested = block.split("\n\n")
    assert strict == (
        "【关键术语约束】以下术语必须严格遵守标准译法：\n"
        "  • Estrangement → 疏离（NOT 异化）\n"
        "  • Thrasymachus → 色拉叙马霍斯"
    )
    assert suggested == (
        "【建议术语】以下译法一般情况下采用；如果某句的语境需要，"
        "可以改用更贴切、更通顺的译法，但不得改变原意：\n"
        "  • Cosmic morale → 宇宙士气（也可：面对宇宙的精神底气、宇宙信念）（NOT 宇宙道德）\n"
        "  • Uniformity → 整齐划一（也可：一律化）"
    )


def test_only_preferred_terms_render_only_the_suggestion_block() -> None:
    data = {
        "critical_terminology": [
            {"term": "Uniformity", "suggested_translation": "整齐划一", "tier": "preferred"}
        ]
    }

    block = GlossaryManager.from_dict(data).format_block()

    assert block.startswith("【建议术语】")
    assert "必须严格遵守" not in block
    assert block.endswith("  • Uniformity → 整齐划一")


def test_min_priority_filters_both_tiers() -> None:
    block = GlossaryManager.from_dict(_tiered()).format_block(min_priority="critical")

    assert "Estrangement" in block
    assert "Uniformity" not in block and "Cosmic morale" not in block
    assert "【建议术语】" not in block


def test_an_unknown_tier_fails_loudly_with_its_index() -> None:
    data = {
        "critical_terminology": [
            {"term": "A", "suggested_translation": "甲"},
            {"term": "B", "suggested_translation": "乙", "tier": "soft"},
        ]
    }

    with pytest.raises(ValueError, match=r"critical_terminology\[1\].*tier"):
        GlossaryManager.from_dict(data)


def test_term_usage_carries_the_tier() -> None:
    terms: list[dict[str, object]] = [
        {"term": "Uniformity", "suggested_translation": "整齐划一", "tier": "preferred"},
        {"term": "Unity", "suggested_translation": "统一"},
    ]

    usage = {item.term: item for item in measure_term_usage(terms, [("unity", "统一")])}

    assert usage["Uniformity"].tier == "preferred"
    assert usage["Unity"].tier is None


def test_a_fixed_term_using_only_its_alternative_is_drift() -> None:
    terms: list[dict[str, object]] = [
        {
            "term": "garden",
            "suggested_translation": "花园",
            "alternatives": ["园子"],
            "tier": "fixed",
        }
    ]

    usage = measure_term_usage(terms, [("garden", "园子"), ("a garden", "园子")])

    assert usage[0].missing == 2
    assert not usage[0].consistent
