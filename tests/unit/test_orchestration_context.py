from __future__ import annotations

import json
from pathlib import Path

from ai.orchestration_context import load_orchestration_context


DEFAULT_AUDIENCE = "General readers interested in practical philosophy."
DEFAULT_STYLE = "Accurate, concise, and natural modern Chinese prose."


def _write_builtin_glossary(script_dir: Path, entries: dict[str, str]) -> None:
    glossary_path = script_dir / "config" / "glossaries" / "en_zh_glossary.json"
    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_context_merges_glossaries_in_deterministic_order(tmp_path: Path) -> None:
    _write_builtin_glossary(
        tmp_path,
        {
            " Stoicism ": " 斯多葛主义 ",
            "Marcus Aurelius": " 马可·奥勒留 ",
        },
    )

    runtime_config = {
        "orchestrated": {
            "audience": "Philosophy readers",
            "style": "Elegant and clear",
            "glossary": {
                " Stoicism ": "斯多葛学派",
                " Apatheia ": " 不动心 ",
            },
        }
    }

    context = load_orchestration_context(
        runtime_config=runtime_config,
        output_lang="zh",
        script_dir=tmp_path,
    )

    assert context.audience == "Philosophy readers"
    assert context.style == "Elegant and clear"
    assert list(context.glossary.items()) == [
        ("Stoicism", "斯多葛学派"),
        ("Marcus Aurelius", "马可·奥勒留"),
        ("Apatheia", "不动心"),
    ]


def test_load_context_ignores_empty_glossary_entries(tmp_path: Path) -> None:
    _write_builtin_glossary(
        tmp_path,
        {
            "": "ignored",
            "Valid": " 有效 ",
            "BlankValue": " ",
            "   ": "ignored",
        },
    )

    runtime_config = {
        "orchestrated": {
            "glossary": {
                "   ": "ignored",
                "Runtime": " 运行时 ",
                "Keep": "   ",
            }
        }
    }

    context = load_orchestration_context(
        runtime_config=runtime_config,
        output_lang="zh",
        script_dir=tmp_path,
    )

    assert context.glossary == {
        "Valid": "有效",
        "Runtime": "运行时",
    }


def test_load_context_non_zh_skips_builtin_glossary(tmp_path: Path) -> None:
    _write_builtin_glossary(tmp_path, {"Stoicism": "斯多葛主义"})

    runtime_config = {
        "orchestrated": {
            "glossary": {
                "Stoicism": "Stoïcisme",
                "Apatheia": "Apathie",
            }
        }
    }

    context = load_orchestration_context(
        runtime_config=runtime_config,
        output_lang="fr",
        script_dir=tmp_path,
    )

    assert context.glossary == {
        "Stoicism": "Stoïcisme",
        "Apatheia": "Apathie",
    }


def test_load_context_defaults_audience_and_style(tmp_path: Path) -> None:
    context = load_orchestration_context(runtime_config={}, output_lang="zh", script_dir=tmp_path)

    assert context.audience == DEFAULT_AUDIENCE
    assert context.style == DEFAULT_STYLE


def test_load_context_invalid_builtin_glossary_does_not_block_runtime_glossary(
    tmp_path: Path,
) -> None:
    glossary_path = tmp_path / "config" / "glossaries" / "en_zh_glossary.json"
    glossary_path.parent.mkdir(parents=True, exist_ok=True)
    glossary_path.write_text("{invalid-json", encoding="utf-8")

    runtime_config = {
        "orchestrated": {
            "glossary": {
                "Apatheia": " 不动心 ",
            }
        }
    }

    context = load_orchestration_context(
        runtime_config=runtime_config,
        output_lang="zh",
        script_dir=tmp_path,
    )

    assert context.glossary == {
        "Apatheia": "不动心",
    }
