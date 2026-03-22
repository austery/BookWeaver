from __future__ import annotations

from dataclasses import dataclass


_AUDIENCE_PRESETS = {"general", "technical", "academic", "business"}
_STYLE_PRESETS = {
    "storytelling",
    "formal",
    "technical",
    "literal",
    "academic",
    "business",
    "humorous",
    "conversational",
    "elegant",
}

_TECHNICAL_KEYWORDS = (
    "api",
    "schema",
    "distributed",
    "latency",
    "throughput",
    "database",
    "protocol",
    "architecture",
)
_ACADEMIC_KEYWORDS = (
    "hypothesis",
    "methodology",
    "empirical",
    "citation",
    "theorem",
    "literature",
)
_BUSINESS_KEYWORDS = (
    "roi",
    "stakeholder",
    "roadmap",
    "revenue",
    "market",
    "strategy",
    "kpi",
)


@dataclass(frozen=True, slots=True)
class ResolvedPresets:
    audience: str
    style: str
    audience_reason: str
    style_reason: str
    audience_source: str
    style_source: str


def _count_matches(*, text: str, keywords: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword in lowered)


def _resolve_auto_presets(sampled_text: list[str]) -> tuple[str, str, str, str]:
    joined = "\n".join(sampled_text)
    technical_score = _count_matches(text=joined, keywords=_TECHNICAL_KEYWORDS)
    academic_score = _count_matches(text=joined, keywords=_ACADEMIC_KEYWORDS)
    business_score = _count_matches(text=joined, keywords=_BUSINESS_KEYWORDS)

    if (
        technical_score >= academic_score
        and technical_score >= business_score
        and technical_score > 0
    ):
        return (
            "technical",
            "technical",
            f"Detected technical signal score={technical_score}",
            f"Detected technical style signal score={technical_score}",
        )
    if (
        academic_score >= technical_score
        and academic_score >= business_score
        and academic_score > 0
    ):
        return (
            "academic",
            "academic",
            f"Detected academic signal score={academic_score}",
            f"Detected academic style signal score={academic_score}",
        )
    if (
        business_score >= technical_score
        and business_score >= academic_score
        and business_score > 0
    ):
        return (
            "business",
            "business",
            f"Detected business signal score={business_score}",
            f"Detected business style signal score={business_score}",
        )

    return (
        "general",
        "storytelling",
        "No strong domain signal; fallback to general audience",
        "No strong style signal; fallback to storytelling style",
    )


def resolve_presets(
    *,
    sampled_text: list[str],
    audience_override: str | None,
    style_override: str | None,
) -> ResolvedPresets:
    auto_audience, auto_style, auto_audience_reason, auto_style_reason = _resolve_auto_presets(
        sampled_text
    )

    if audience_override is not None and audience_override not in _AUDIENCE_PRESETS:
        raise ValueError(f"Unsupported audience preset: {audience_override}")
    if style_override is not None and style_override not in _STYLE_PRESETS:
        raise ValueError(f"Unsupported style preset: {style_override}")

    resolved_audience = audience_override or auto_audience
    resolved_style = style_override or auto_style
    audience_source = "cli_override" if audience_override else "auto"
    style_source = "cli_override" if style_override else "auto"

    audience_reason = (
        f"CLI override: {audience_override}"
        if audience_override is not None
        else auto_audience_reason
    )
    style_reason = (
        f"CLI override: {style_override}" if style_override is not None else auto_style_reason
    )

    return ResolvedPresets(
        audience=resolved_audience,
        style=resolved_style,
        audience_reason=audience_reason,
        style_reason=style_reason,
        audience_source=audience_source,
        style_source=style_source,
    )
