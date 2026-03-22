from __future__ import annotations


def test_resolve_presets_technical_content_prefers_technical() -> None:
    from ai.epub_preset_resolver import resolve_presets

    resolved = resolve_presets(
        sampled_text=["API schema", "distributed system", "latency budget"],
        audience_override=None,
        style_override=None,
    )
    assert resolved.audience == "technical"
    assert resolved.style == "technical"
    assert "technical signal" in resolved.audience_reason.lower()


def test_resolve_presets_philosophy_content_prefers_general_storytelling() -> None:
    from ai.epub_preset_resolver import resolve_presets

    resolved = resolve_presets(
        sampled_text=["Stoic", "virtue", "meaning of life"],
        audience_override=None,
        style_override=None,
    )
    assert resolved.audience == "general"
    assert resolved.style == "storytelling"


def test_resolve_presets_override_wins_and_is_marked() -> None:
    from ai.epub_preset_resolver import resolve_presets

    resolved = resolve_presets(
        sampled_text=["API schema"],
        audience_override="business",
        style_override="formal",
    )
    assert resolved.audience == "business"
    assert resolved.style == "formal"
    assert resolved.audience_source == "cli_override"
    assert resolved.style_source == "cli_override"
