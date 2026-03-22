from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresetResolution:
    audience: str
    style: str
    audience_reason: str
    style_reason: str
    audience_source: str
    style_source: str


@dataclass(frozen=True, slots=True)
class BaoyuAnalysis:
    quick_summary: list[str]
    core_argument: str
    key_concepts: list[str]
    structure: list[str]
    background_context: list[str]
    terminology: list[tuple[str, str]]
    tone_style_assessment: list[str]
    comprehension_challenges: list[tuple[str, str, str]]
    figurative_mapping: list[tuple[str, str, str, str]]
    structural_challenges: list[str]
    preset_resolution: PresetResolution


def render_analysis_markdown(analysis: BaoyuAnalysis) -> str:
    lines: list[str] = [
        "# Analysis",
        "",
        "## Quick Summary",
    ]
    lines.extend([f"- {item}" for item in analysis.quick_summary])

    lines.extend(
        ["", "## Core Content", f"- Core argument: {analysis.core_argument}", "- Key concepts:"]
    )
    lines.extend([f"  - {item}" for item in analysis.key_concepts])
    lines.append("- Structure:")
    lines.extend([f"  - {item}" for item in analysis.structure])

    lines.extend(["", "## Background Context"])
    lines.extend([f"- {item}" for item in analysis.background_context])

    lines.extend(["", "## Terminology"])
    lines.extend([f"- {source} -> {target}" for source, target in analysis.terminology])

    lines.extend(["", "## Tone & Style"])
    lines.extend([f"- {item}" for item in analysis.tone_style_assessment])

    lines.extend(["", "## Comprehension Challenges"])
    lines.extend(
        [
            f"- {term} -> why: {reason} -> note: {suggested_note}"
            for term, reason, suggested_note in analysis.comprehension_challenges
        ]
    )

    lines.extend(["", "## Figurative Language & Metaphor Mapping"])
    lines.extend(
        [
            f"- {source} -> {meaning} -> {approach} -> {rendering}"
            for source, meaning, approach, rendering in analysis.figurative_mapping
        ]
    )

    lines.extend(["", "## Structural & Creative Challenges"])
    lines.extend([f"- {item}" for item in analysis.structural_challenges])

    lines.extend(
        [
            "",
            "## Preset Resolution",
            f"- Audience: {analysis.preset_resolution.audience}",
            f"  - Reason: {analysis.preset_resolution.audience_reason}",
            f"  - Source: {analysis.preset_resolution.audience_source}",
            f"- Style: {analysis.preset_resolution.style}",
            f"  - Reason: {analysis.preset_resolution.style_reason}",
            f"  - Source: {analysis.preset_resolution.style_source}",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"
