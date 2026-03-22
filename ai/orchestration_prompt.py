from __future__ import annotations

from typing import Iterable

from ai.orchestration_context import OrchestrationContext


_BACKGROUND_SECTION_HEADINGS: tuple[str, ...] = (
    "Quick Summary",
    "Core Content",
    "Background Context",
)
_CHALLENGE_SECTION_HEADINGS: tuple[str, ...] = (
    "Comprehension Challenges",
    "Figurative Language & Metaphor Mapping",
    "Structural & Creative Challenges",
)


def _extract_analysis_section_lines(analysis_markdown: str, heading: str) -> list[str]:
    section_heading = f"## {heading}"
    lines = analysis_markdown.splitlines()
    section_lines: list[str] = []
    capture = False

    for line in lines:
        if line.startswith("## "):
            if capture:
                break
            if line == section_heading:
                capture = True
                continue
        if not capture:
            continue
        stripped = line.strip()
        if stripped:
            section_lines.append(stripped)

    return section_lines


def _render_section(title: str, lines: Iterable[str]) -> str:
    rendered_lines = list(lines)
    body = "\n".join(rendered_lines) if rendered_lines else "- (No items.)"
    return f"## {title}\n{body}"


def _render_analysis_guidance(
    *,
    analysis_markdown: str,
    headings: tuple[str, ...],
    empty_fallback: str,
) -> list[str]:
    rendered_lines: list[str] = []
    for heading in headings:
        section_lines = _extract_analysis_section_lines(analysis_markdown, heading)
        if not section_lines:
            continue
        if rendered_lines:
            rendered_lines.append("")
        rendered_lines.append(f"### {heading}")
        rendered_lines.extend(section_lines)
    if rendered_lines:
        return rendered_lines
    return [empty_fallback]


def _render_glossary(glossary: dict[str, str]) -> list[str]:
    if not glossary:
        return ["- (No glossary terms provided.)"]
    ordered_terms = sorted(glossary.items(), key=lambda item: (item[0].casefold(), item[0]))
    return [f"- {source} -> {target}" for source, target in ordered_terms]


def build_orchestration_prompt(
    *,
    output_lang: str,
    context: OrchestrationContext,
    analysis_markdown: str,
    additional_instructions: str | None = None,
) -> str:
    background_lines = _render_analysis_guidance(
        analysis_markdown=analysis_markdown,
        headings=_BACKGROUND_SECTION_HEADINGS,
        empty_fallback="- No structured background was extracted from analysis.",
    )
    challenge_lines = _render_analysis_guidance(
        analysis_markdown=analysis_markdown,
        headings=_CHALLENGE_SECTION_HEADINGS,
        empty_fallback="- No explicit challenge analysis was found. Preserve clarity and fidelity.",
    )
    translation_principles = [
        "- Preserve original meaning and factual accuracy.",
        "- Apply glossary terms consistently across all pages.",
        "- Keep markdown structure, links, and image references unchanged.",
        "- Resolve ambiguity using Content Background and Comprehension Challenges.",
        f"- Output only the translated content in target language ({output_lang}).",
    ]

    sections = [
        f"You are a professional translator for {output_lang} readers.",
        _render_section("Target Audience", [context.audience]),
        _render_section("Translation Style", [context.style]),
        _render_section("Content Background", background_lines),
        _render_section("Glossary", _render_glossary(context.glossary)),
        _render_section("Comprehension Challenges", challenge_lines),
        _render_section("Translation Principles", translation_principles),
    ]

    additional_text = additional_instructions.strip() if additional_instructions is not None else ""
    if additional_text:
        sections.append(_render_section("Additional Instructions", [additional_text]))

    return "\n\n".join(sections) + "\n"
