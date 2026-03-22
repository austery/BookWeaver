from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from ai.orchestration_context import OrchestrationContext


_FIGURATIVE_KEYWORD_PATTERN = re.compile(r"\b(?:like|as|metaphor|image)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class AnalysisStats:
    page_count: int
    character_count: int


def _sorted_pages(pages: Mapping[str, str]) -> list[tuple[str, str]]:
    normalized_pages: list[tuple[str, str]] = []
    for page_name, content in pages.items():
        if not isinstance(page_name, str):
            raise TypeError(f"Page name must be str, got {type(page_name).__name__}.")
        if not isinstance(content, str):
            raise TypeError(
                f"Page content for {page_name!r} must be str, got {type(content).__name__}.",
            )
        normalized_pages.append((page_name, content))

    return sorted(normalized_pages, key=lambda item: item[0])


def _build_stats(pages: list[tuple[str, str]]) -> AnalysisStats:
    return AnalysisStats(
        page_count=len(pages),
        character_count=sum(len(content) for _, content in pages),
    )


def _build_summary_lines(stats: AnalysisStats) -> list[str]:
    return [
        f"- Page Count: {stats.page_count}",
        f"- Character Count: {stats.character_count}",
        "- Workflow: Deterministic local analysis draft (no external calls).",
    ]


def _build_core_content_lines(pages: list[tuple[str, str]]) -> list[str]:
    if not pages:
        return ["- No source pages provided."]

    sample_pages = pages[:2]
    lines = ["- The source appears to be explanatory prose intended for careful reading."]
    for page_name, content in sample_pages:
        preview = content.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = f"{preview[:117]}..."
        lines.append(f"- {page_name}: {preview or '(empty page content)'}")
    return lines


def _build_background_context_lines(context: OrchestrationContext) -> list[str]:
    return [
        f"- Audience baseline: {context.audience}",
        "- Reader expectation: preserve meaning while reducing ambiguity in translated output.",
    ]


def _build_terminology_lines(glossary: Mapping[str, str]) -> list[str]:
    if not glossary:
        return ["- (No glossary entries provided.)"]

    ordered_terms = sorted(glossary.items(), key=lambda item: (item[0].casefold(), item[0]))
    return [f"- {source} -> {target}" for source, target in ordered_terms]


def _build_tone_style_lines(context: OrchestrationContext) -> list[str]:
    return [
        f"- Desired style: {context.style}",
        "- Maintain conceptual precision and natural flow for target-language readers.",
    ]


def _build_comprehension_challenges_lines(pages: list[tuple[str, str]]) -> list[str]:
    combined_text = " ".join(content for _, content in pages)
    lines = ["- Philosophical abstractions may require explicit logical connectors in translation."]
    if any(marker in combined_text for marker in (";", ":", "—")):
        lines.append("- Long compound clauses may need controlled segmentation for readability.")
    if any(marker in combined_text for marker in ('"', "“", "”", "'")):
        lines.append("- Quoted speech or emphasized terms need stable rendering choices.")
    if len(combined_text) > 500:
        lines.append(
            "- Dense passages should be translated with consistency over adjacent paragraphs."
        )
    return lines


def _build_figurative_lines(pages: list[tuple[str, str]]) -> list[str]:
    combined_text = " ".join(content for _, content in pages)
    if _FIGURATIVE_KEYWORD_PATTERN.search(combined_text):
        return [
            "- Preserve figurative intent first, then adjust literal wording for target-language clarity.",
            "- Keep metaphor source/target mapping explicit when literal carry-over is unnatural.",
        ]
    return [
        "- No explicit metaphor markers detected; still watch for implicit figurative phrasing.",
        "- Prefer faithful conceptual mapping over decorative rewriting.",
    ]


def _build_structural_challenge_lines(pages: list[tuple[str, str]]) -> list[str]:
    if not pages:
        return ["- No structure to analyze."]

    page_names = [page_name for page_name, _ in pages]
    return [
        f"- Maintain page-level continuity across {len(page_names)} input files.",
        "- Keep markdown structure stable (headings, lists, and emphasis markers).",
        "- Avoid introducing new rhetorical structure not present in source text.",
    ]


def _render_section(title: str, lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "- (No items.)"
    return f"## {title}\n{body}"


def build_analysis_markdown(*, pages: Mapping[str, str], context: OrchestrationContext) -> str:
    ordered_pages = _sorted_pages(pages)
    stats = _build_stats(ordered_pages)

    sections = [
        _render_section("Quick Summary", _build_summary_lines(stats)),
        _render_section("Core Content", _build_core_content_lines(ordered_pages)),
        _render_section("Background Context", _build_background_context_lines(context)),
        _render_section("Terminology", _build_terminology_lines(context.glossary)),
        _render_section("Tone & Style", _build_tone_style_lines(context)),
        _render_section(
            "Comprehension Challenges", _build_comprehension_challenges_lines(ordered_pages)
        ),
        _render_section(
            "Figurative Language & Metaphor Mapping",
            _build_figurative_lines(ordered_pages),
        ),
        _render_section(
            "Structural & Creative Challenges",
            _build_structural_challenge_lines(ordered_pages),
        ),
    ]
    return "\n\n".join(sections) + "\n"
