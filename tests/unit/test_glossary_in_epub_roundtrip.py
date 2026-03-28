from __future__ import annotations

import json
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
