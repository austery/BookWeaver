from __future__ import annotations

import pytest

from ai.orchestration_context import OrchestrationContext
from ai.orchestration_analysis import build_analysis_markdown


_REQUIRED_HEADINGS = [
    "## Quick Summary",
    "## Core Content",
    "## Background Context",
    "## Terminology",
    "## Tone & Style",
    "## Comprehension Challenges",
    "## Figurative Language & Metaphor Mapping",
    "## Structural & Creative Challenges",
]


def _extract_section(markdown: str, heading: str) -> str:
    section_heading = f"## {heading}"
    lines = markdown.splitlines()
    section_lines: list[str] = []
    capture = False

    for line in lines:
        if line.startswith("## "):
            if capture:
                break
            if line == section_heading:
                capture = True
                section_lines.append(line)
                continue
        if capture:
            section_lines.append(line)

    return "\n".join(section_lines).strip()


def test_analysis_contains_required_baoyu_sections() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={"Stoicism": "斯多葛主义"},
    )
    markdown = build_analysis_markdown(
        pages={"page0001.md": "A short philosophical paragraph."},
        context=context,
    )

    for heading in _REQUIRED_HEADINGS:
        assert heading in markdown


def test_analysis_includes_page_count_and_character_count() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    markdown = build_analysis_markdown(
        pages={"page0002.md": "cd", "page0001.md": "ab"},
        context=context,
    )

    assert "- Page Count: 2" in markdown
    assert "- Character Count: 4" in markdown


def test_analysis_terminology_section_is_deterministic() -> None:
    pages = {"page0002.md": "second", "page0001.md": "first"}
    context_a = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={
            "gamma": "伽马",
            "Alpha": "阿尔法",
            "beta": "贝塔",
        },
    )
    context_b = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={
            "beta": "贝塔",
            "gamma": "伽马",
            "Alpha": "阿尔法",
        },
    )

    markdown_a = build_analysis_markdown(pages=pages, context=context_a)
    markdown_b = build_analysis_markdown(pages=pages, context=context_b)

    terminology_a = _extract_section(markdown_a, "Terminology")
    terminology_b = _extract_section(markdown_b, "Terminology")

    assert terminology_a == terminology_b
    assert "- Alpha -> 阿尔法" in terminology_a
    assert "- beta -> 贝塔" in terminology_a
    assert "- gamma -> 伽马" in terminology_a


def test_analysis_comprehension_detects_punctuation_and_quotes() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    markdown = build_analysis_markdown(
        pages={"page0001.md": 'He said: "Truth is layered"; the claim endures.'},
        context=context,
    )
    section = _extract_section(markdown, "Comprehension Challenges")

    assert "- Long compound clauses may need controlled segmentation for readability." in section
    assert "- Quoted speech or emphasized terms need stable rendering choices." in section


def test_analysis_comprehension_detects_long_text_challenge() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    long_text = "A" * 501
    markdown = build_analysis_markdown(
        pages={"page0001.md": long_text},
        context=context,
    )
    section = _extract_section(markdown, "Comprehension Challenges")

    assert (
        "- Dense passages should be translated with consistency over adjacent paragraphs."
        in section
    )


def test_analysis_comprehension_handles_empty_input() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    markdown = build_analysis_markdown(pages={}, context=context)
    section = _extract_section(markdown, "Comprehension Challenges")

    assert (
        "- Philosophical abstractions may require explicit logical connectors in translation."
        in section
    )
    assert (
        "- Long compound clauses may need controlled segmentation for readability." not in section
    )
    assert "- Quoted speech or emphasized terms need stable rendering choices." not in section
    assert (
        "- Dense passages should be translated with consistency over adjacent paragraphs."
        not in section
    )


def test_analysis_figurative_branch_detects_word_boundary_keywords() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    markdown = build_analysis_markdown(
        pages={"page0001.md": "The argument blooms like, spring rain."},
        context=context,
    )
    section = _extract_section(markdown, "Figurative Language & Metaphor Mapping")

    assert (
        "- Preserve figurative intent first, then adjust literal wording for target-language clarity."
        in section
    )
    assert (
        "- Keep metaphor source/target mapping explicit when literal carry-over is unnatural."
        in section
    )


def test_analysis_figurative_branch_handles_absent_keywords() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    markdown = build_analysis_markdown(
        pages={"page0001.md": "The chapter states a direct claim without symbolic imagery."},
        context=context,
    )
    section = _extract_section(markdown, "Figurative Language & Metaphor Mapping")

    assert (
        "- No explicit metaphor markers detected; still watch for implicit figurative phrasing."
        in section
    )
    assert "- Prefer faithful conceptual mapping over decorative rewriting." in section


def test_analysis_rejects_non_string_page_content() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={},
    )
    with pytest.raises(TypeError, match=r"page0001\.md.*str"):
        build_analysis_markdown(
            pages={"page0001.md": 123},  # type: ignore[arg-type]
            context=context,
        )


def test_analysis_markdown_is_fully_deterministic_across_input_ordering() -> None:
    context_a = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={"gamma": "伽马", "Alpha": "阿尔法", "beta": "贝塔"},
    )
    context_b = OrchestrationContext(
        audience="General readers",
        style="Natural and precise Chinese.",
        glossary={"beta": "贝塔", "gamma": "伽马", "Alpha": "阿尔法"},
    )
    pages_a = {
        "page0002.md": "Second page includes metaphor image and punctuation: yes.",
        "page0001.md": 'First page says "steady effort" and ends with a long clause; still coherent.',
    }
    pages_b = {
        "page0001.md": 'First page says "steady effort" and ends with a long clause; still coherent.',
        "page0002.md": "Second page includes metaphor image and punctuation: yes.",
    }

    markdown_a = build_analysis_markdown(pages=pages_a, context=context_a)
    markdown_b = build_analysis_markdown(pages=pages_b, context=context_b)

    assert markdown_a == markdown_b
