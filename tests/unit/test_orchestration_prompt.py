from __future__ import annotations

from ai.orchestration_context import OrchestrationContext
from ai.orchestration_prompt import build_orchestration_prompt


def test_prompt_includes_audience_style_background_glossary_and_challenges() -> None:
    analysis = (
        "## Quick Summary\n"
        "- Page Count: 2\n\n"
        "## Core Content\n"
        "- Intro to stoic practice.\n\n"
        "## Background Context\n"
        "- Practical philosophy for daily use.\n\n"
        "## Comprehension Challenges\n"
        "- Dense sentence chains.\n\n"
        "## Structural & Creative Challenges\n"
        "- Preserve heading hierarchy.\n"
    )
    context = OrchestrationContext(
        audience="General readers interested in philosophy.",
        style="Natural and precise modern Chinese.",
        glossary={"Stoicism": "斯多葛主义", "Apatheia": "不动心"},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown=analysis,
    )

    assert "## Target Audience" in prompt
    assert "## Translation Style" in prompt
    assert "## Content Background" in prompt
    assert "## Glossary" in prompt
    assert "## Comprehension Challenges" in prompt
    assert "### Quick Summary" in prompt
    assert "### Comprehension Challenges" in prompt
    assert "- Stoicism -> 斯多葛主义" in prompt


def test_prompt_glossary_order_is_deterministic() -> None:
    analysis = "## Quick Summary\n- Stable baseline.\n"
    context_a = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={"gamma": "伽马", "Alpha": "阿尔法", "beta": "贝塔"},
    )
    context_b = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={"beta": "贝塔", "gamma": "伽马", "Alpha": "阿尔法"},
    )

    prompt_a = build_orchestration_prompt(
        output_lang="zh",
        context=context_a,
        analysis_markdown=analysis,
    )
    prompt_b = build_orchestration_prompt(
        output_lang="zh",
        context=context_b,
        analysis_markdown=analysis,
    )

    assert prompt_a == prompt_b
    assert "- Alpha -> 阿尔法" in prompt_a
    assert "- beta -> 贝塔" in prompt_a
    assert "- gamma -> 伽马" in prompt_a


def test_prompt_translation_principles_present() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown="## Quick Summary\n- Summary.\n",
    )

    assert "## Translation Principles" in prompt
    assert "- Preserve original meaning and factual accuracy." in prompt
    assert "- Apply glossary terms consistently across all pages." in prompt
    assert "- Keep markdown structure, links, and image references unchanged." in prompt


def test_prompt_uses_fallback_when_analysis_sections_are_missing() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown="",
    )

    assert "- No structured background was extracted from analysis." in prompt
    assert "- No explicit challenge analysis was found. Preserve clarity and fidelity." in prompt


def test_prompt_uses_fallback_when_headings_have_blank_content() -> None:
    analysis = (
        "## Quick Summary\n\n"
        "## Core Content\n   \n"
        "## Background Context\n\n"
        "## Comprehension Challenges\n\n"
        "## Structural & Creative Challenges\n   \n"
    )
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown=analysis,
    )

    assert "### Quick Summary" not in prompt
    assert "### Comprehension Challenges" not in prompt
    assert "- No structured background was extracted from analysis." in prompt
    assert "- No explicit challenge analysis was found. Preserve clarity and fidelity." in prompt


def test_prompt_ignores_whitespace_only_additional_instructions() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown="## Quick Summary\n- Summary.\n",
        additional_instructions=" \n\t ",
    )

    assert "## Additional Instructions" not in prompt


def test_prompt_includes_empty_glossary_fallback_text() -> None:
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={},
    )

    prompt = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown="## Quick Summary\n- Summary.\n",
    )

    assert "## Glossary" in prompt
    assert "- (No glossary terms provided.)" in prompt


def test_prompt_formatting_is_stable_without_extra_blank_blocks() -> None:
    analysis = (
        "## Quick Summary\n"
        "- One line.\n\n"
        "## Core Content\n"
        "- Two line.\n\n"
        "## Comprehension Challenges\n"
        "- Challenge one.\n\n"
        "## Structural & Creative Challenges\n"
        "- Challenge two.\n"
    )
    context = OrchestrationContext(
        audience="General readers",
        style="Natural Chinese.",
        glossary={"Alpha": "阿尔法"},
    )

    prompt_without_extra = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown=analysis,
    )
    prompt_with_extra = build_orchestration_prompt(
        output_lang="zh",
        context=context,
        analysis_markdown=analysis,
        additional_instructions="Use concise wording.",
    )

    assert "\n\n\n" not in prompt_without_extra
    assert "\n\n\n" not in prompt_with_extra
    assert prompt_without_extra.endswith("\n")
    assert prompt_with_extra.endswith("\n")
    assert not prompt_without_extra.endswith("\n\n")
    assert not prompt_with_extra.endswith("\n\n")
