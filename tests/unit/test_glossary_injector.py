from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.glossary_injector import GlossaryInjector


MINIMAL_GLOSSARY = {
    "critical_terminology": [
        {
            "term": "Connascence",
            "suggested_translation": "共生性",
            "negative_constraint": "NOT 并发性 (Concurrency)",
            "reason": "Easily confused with Concurrency",
            "priority": "critical",
        }
    ]
}

MEDIUM_GLOSSARY = {
    "critical_terminology": [
        {
            "term": "Connascence",
            "suggested_translation": "共生性",
            "negative_constraint": "NOT 并发性 (Concurrency)",
            "reason": "Author-invented concept",
            "priority": "critical",
        },
        {
            "term": "Shift Left",
            "suggested_translation": "向左移动",
            "reason": "Architectural practice",
            "priority": "high",
        },
        {
            "term": "Evolutionary Architecture",
            "suggested_translation": "演进式架构",
            "reason": "Core book concept",
            "priority": "medium",
        },
    ]
}


def write_glossary(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "glossary.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_load_valid_glossary(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    assert len(injector.terms) == 1
    assert injector.terms[0]["term"] == "Connascence"


def test_format_block_contains_term(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    assert "Connascence" in block
    assert "共生性" in block


def test_format_block_contains_negative_constraint(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, MINIMAL_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    assert "NOT" in block or "≠" in block


def test_format_block_empty_when_no_terms(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, {"critical_terminology": []})
    injector = GlossaryInjector(path)
    assert injector.format_block() == ""


def test_format_block_under_token_budget(tmp_path: Path) -> None:
    """Block must stay lean — rough budget check via character count."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    # 300 tokens ≈ 1200 characters; 20-term glossary should be well under this
    assert len(block) < 2000


def test_load_from_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        GlossaryInjector(Path("/nonexistent/glossary.json"))


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid glossary JSON"):
        GlossaryInjector(p)


def test_load_wrong_schema_raises(tmp_path: Path) -> None:
    p = tmp_path / "wrong.json"
    p.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'critical_terminology'"):
        GlossaryInjector(p)


def test_format_block_prioritizes_critical_terms(tmp_path: Path) -> None:
    """Critical terms appear before medium-priority terms."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block()
    idx_critical = block.index("Connascence")
    idx_medium = block.index("Evolutionary Architecture")
    assert idx_critical < idx_medium


def test_format_block_min_priority_critical_only(tmp_path: Path) -> None:
    """min_priority='critical' includes only critical terms."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block(min_priority="critical")
    assert "Connascence" in block
    assert "Shift Left" not in block
    assert "Evolutionary Architecture" not in block


def test_format_block_min_priority_high_includes_critical_and_high(tmp_path: Path) -> None:
    """min_priority='high' includes critical + high, excludes medium."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block(min_priority="high")
    assert "Connascence" in block
    assert "Shift Left" in block
    assert "Evolutionary Architecture" not in block


def test_format_block_min_priority_medium_includes_all(tmp_path: Path) -> None:
    """min_priority='medium' includes all terms (same as None)."""
    path = write_glossary(tmp_path, MEDIUM_GLOSSARY)
    injector = GlossaryInjector(path)
    block = injector.format_block(min_priority="medium")
    assert "Connascence" in block
    assert "Shift Left" in block
    assert "Evolutionary Architecture" in block


def test_format_block_min_priority_high_all_medium_returns_empty(tmp_path: Path) -> None:
    """min_priority='high' when all terms are medium returns empty string."""
    glossary_all_medium = {
        "critical_terminology": [
            {
                "term": "Technical Debt",
                "suggested_translation": "技术债务",
                "reason": "Common concept",
                "priority": "medium",
            }
        ]
    }
    path = write_glossary(tmp_path, glossary_all_medium)
    injector = GlossaryInjector(path)
    assert injector.format_block(min_priority="high") == ""
