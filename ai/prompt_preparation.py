"""Freeze local prompt intent before external work and identify the exact rendered request."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_LANG_NAMES: dict[str, str] = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "it": "Italian",
}

# ── System prompt template ────────────────────────────────────
# NOTE: This prompt states no batch output format (no %% delimiters,
# no <segment> tags). The transport protocol owns that contract and
# appends it per request (see augment_prompt_for_batch), so every
# rendered request carries exactly one output contract.

_SYSTEM_PROMPT_TEMPLATE = """\
You are a professional {target_language} native translator \
who needs to fluently translate text into {target_language}.

## Translation Rules
1. Output only the translated content, without explanations \
or additional content (such as "Here's the translation:")
2. The returned translation must maintain exactly the same \
number of paragraphs and format as the original text
3. If the text contains HTML tags, consider where the tags \
should be placed in the translation while maintaining fluency
4. For content that should not be translated (such as proper \
nouns, code, URLs), keep the original text"""


def _get_language_name(lang_code: str) -> str:
    """Resolve language code to full name."""
    return _LANG_NAMES.get(lang_code, lang_code)


def build_system_prompt(
    target_language: str,
    *,
    glossary_block: str | None = None,
    custom_prompt: str | None = None,
    immersive: bool = False,
) -> str:
    """Assemble the protocol-neutral system prompt from components.

    ``immersive`` (EPUB) only adds the closing target-language cue. The
    batch output contract is added by the provider's transport protocol.
    """
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(target_language=target_language)
    if glossary_block:
        prompt = f"{prompt}\n\n{glossary_block}"
    if custom_prompt:
        prompt = f"{prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
    if immersive:
        prompt = f"{prompt}\n\nTranslate to {target_language}:"
    return prompt


def load_glossary_block(
    glossary_path: str | None,
    *,
    min_priority: str | None = None,
) -> str | None:
    """Load and format glossary block if path is provided."""
    if glossary_path is None:
        return None
    from ai.glossary_injector import GlossaryInjector

    return GlossaryInjector(Path(glossary_path)).format_block(min_priority=min_priority) or None


@dataclass(frozen=True)
class EffectivePrompt:
    text: str
    sha256: str


@dataclass(frozen=True)
class PromptPreparation:
    language: str
    custom_prompt: str | None
    immersive: bool
    template_text: str | None

    @classmethod
    def from_config(
        cls,
        config: dict[str, object],
        *,
        output_lang: str,
        custom_prompt: str | None,
        immersive: bool,
    ) -> PromptPreparation:
        template_text = None
        if "prompt_profile" in config or "prompt_templates" in config:
            profile = config.get("prompt_profile", "default")
            templates = config.get("prompt_templates", {})
            template = (
                templates.get(profile)
                if isinstance(templates, dict) and isinstance(profile, str)
                else None
            )
            if not isinstance(template, str):
                raise ValueError(
                    "Selected prompt_profile requires a matching prompt_templates entry"
                )
            template_text = Path(template).expanduser().read_text(encoding="utf-8")
            if immersive and any(
                marker in template_text for marker in ("<!-- START -->", "<!-- END -->")
            ):
                raise ValueError(
                    "Legacy START/END prompt wrappers conflict with EPUB segment output; use an EPUB-compatible template or omit prompt_profile/templates"
                )
        return cls(_get_language_name(output_lang), custom_prompt, immersive, template_text)

    def render(
        self, glossary_path: Path | None, *, min_priority: str | None = None
    ) -> EffectivePrompt:
        glossary_block = load_glossary_block(
            str(glossary_path) if glossary_path else None, min_priority=min_priority
        )
        if self.template_text is None:
            text = build_system_prompt(
                self.language,
                glossary_block=glossary_block,
                custom_prompt=self.custom_prompt,
                immersive=self.immersive,
            )
        else:
            text = (
                self.template_text.replace("{TARGET_LANGUAGE}", self.language)
                .replace("{GLOSSARY_BLOCK}", glossary_block or "")
                .replace("{CUSTOM_INSTRUCTIONS_BLOCK}", self.custom_prompt or "")
            )
        return EffectivePrompt(text, hashlib.sha256(text.encode()).hexdigest())
