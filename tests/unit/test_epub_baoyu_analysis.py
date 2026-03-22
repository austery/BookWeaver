from __future__ import annotations


def _example_analysis():
    from ai.epub_baoyu_analysis import BaoyuAnalysis, PresetResolution

    return BaoyuAnalysis(
        quick_summary=["Summary line 1", "Summary line 2"],
        core_argument="Core argument sentence.",
        key_concepts=["Concept A", "Concept B"],
        structure=["Section 1 -> Section 2"],
        background_context=["Author background", "Writing context"],
        terminology=[("API", "接口"), ("latency", "延迟")],
        tone_style_assessment=["Conversational but rigorous"],
        comprehension_challenges=[("Stoic", "May be unfamiliar", "Ancient philosophy school")],
        figurative_mapping=[
            ("itch at the back of my brain", "persistent anxiety", "interpret", "持续焦虑")
        ],
        structural_challenges=["Long nested clauses need restructuring"],
        preset_resolution=PresetResolution(
            audience="general",
            style="storytelling",
            audience_reason="Auto fallback",
            style_reason="Auto fallback",
            audience_source="auto",
            style_source="auto",
        ),
    )


def test_render_analysis_contains_required_baoyu_sections() -> None:
    from ai.epub_baoyu_analysis import render_analysis_markdown

    text = render_analysis_markdown(_example_analysis())
    for heading in [
        "## Quick Summary",
        "## Core Content",
        "## Background Context",
        "## Terminology",
        "## Tone & Style",
        "## Comprehension Challenges",
        "## Figurative Language & Metaphor Mapping",
        "## Structural & Creative Challenges",
        "## Preset Resolution",
    ]:
        assert heading in text


def test_preset_resolution_section_contains_reason_and_source() -> None:
    from ai.epub_baoyu_analysis import render_analysis_markdown

    text = render_analysis_markdown(_example_analysis())
    assert "Audience:" in text
    assert "Style:" in text
    assert "Reason:" in text
    assert "Source:" in text
