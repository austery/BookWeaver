"""Unified CLI entry point for BookWeaver translation.

This is the **composition root** — it wires ports, core, and adapters
together.  It lives outside the hexagonal boundary modules and is
allowed to import from all layers.

Usage:
    python -m ai.cli input.epub --output translated.epub [options]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ai.adapters.providers._delimiter import SEPARATOR_OVERHEAD
from ai.adapters.providers.gemini_api_adapter import GeminiAPIAdapter
from ai.adapters.providers.gemini_cli_adapter import GeminiCLIAdapter
from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.core.engine import EngineConfig, TranslationEngine
from ai.ports.provider import ITranslationProvider

# ── Language mapping ──────────────────────────────────────────

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
# NOTE: This prompt does NOT mention %% delimiters — that's the
# adapter's job (see augment_prompt_for_batch).

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


# ── Argument parsing ──────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser (compatible with legacy 09_*.py flags)."""
    p = argparse.ArgumentParser(
        prog="bookweaver",
        description="Translate books using the hexagonal translation engine.",
    )
    p.add_argument("input_epub", help="Source EPUB file path")
    p.add_argument("--output", required=True, help="Output EPUB path")
    p.add_argument(
        "--output-lang", default="zh", help="Target language code (default: zh)"
    )
    p.add_argument(
        "--model", default="gemini-2.5-flash", help="Gemini model name or alias"
    )
    p.add_argument(
        "--provider",
        choices=["cli", "api"],
        default="cli",
        help="Translation backend (default: cli)",
    )
    p.add_argument(
        "-p", "--prompt", default=None, help="Additional translation instructions"
    )
    p.add_argument(
        "--glossary", default=None, help="Path to extracted glossary JSON"
    )
    p.add_argument(
        "--glossary-min-priority",
        default=None,
        choices=["critical", "high", "medium"],
        help="Minimum glossary term priority",
    )
    p.add_argument(
        "--cli-api-fallback",
        action="store_true",
        help="Enable API fallback when CLI provider fails",
    )
    p.add_argument(
        "--max-batch-chars",
        type=int,
        default=None,
        help="Max chars per batch (default: 60000 for pro, 10000 otherwise)",
    )
    return p


# ── Wiring helpers ────────────────────────────────────────────


def _get_language_name(lang_code: str) -> str:
    """Resolve language code to full name."""
    return _LANG_NAMES.get(lang_code, lang_code)


def build_system_prompt(
    target_language: str,
    *,
    glossary_block: str | None = None,
    custom_prompt: str | None = None,
) -> str:
    """Assemble the system prompt from components."""
    prompt = _SYSTEM_PROMPT_TEMPLATE.format(target_language=target_language)
    if glossary_block:
        prompt = f"{prompt}\n\n{glossary_block}"
    if custom_prompt:
        prompt = f"{prompt}\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"
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

    return (
        GlossaryInjector(Path(glossary_path)).format_block(
            min_priority=min_priority
        )
        or None
    )


def resolve_model(
    model_name: str,
    config: dict[str, object] | None = None,
) -> tuple[str, bool]:
    """Resolve model alias and detect pro tier.

    Returns:
        (resolved_model_name, is_pro)
    """
    try:
        from ai.model_resolver import ModelResolver

        resolver = ModelResolver(config or {})
        resolved = resolver.resolve(model_name)
        return resolved.name, getattr(resolved, "role", None) is not None and str(
            getattr(resolved, "role", "")
        ).endswith("PRO")
    except Exception:
        is_pro = "pro" in model_name.lower()
        return model_name, is_pro


def create_provider(
    provider_name: str,
    model: str,
    *,
    is_pro: bool = False,
    config: dict[str, object] | None = None,
    cli_api_fallback: bool = False,
) -> ITranslationProvider:
    """Create the appropriate provider adapter."""
    timeout = 300 if is_pro else 180

    resilience = (config or {}).get("epub_resilience", {})
    if not isinstance(resilience, dict):
        resilience = {}

    rate_limit_backoff = tuple(resilience.get("rate_limit_backoff_seconds", [60, 120]))
    transient_backoff = tuple(resilience.get("transient_backoff_seconds", [45]))

    if provider_name == "api":
        from ai.gemini_api_provider import GeminiAPIProvider

        api_key = _resolve_api_key(config)
        raw = GeminiAPIProvider(api_key=api_key, model=model, config=config)
        return GeminiAPIAdapter(raw, timeout_seconds=timeout)

    # CLI provider
    from ai.gemini_provider import GeminiProvider

    raw = GeminiProvider(model=model)
    return GeminiCLIAdapter(
        raw,
        timeout_seconds=timeout,
        rate_limit_backoff=rate_limit_backoff,
        transient_backoff=transient_backoff,
    )


def _resolve_api_key(config: dict[str, object] | None) -> str | None:
    """Resolve API key from config or environment."""
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    if config:
        api_cfg = config.get("gemini_api", {})
        if isinstance(api_cfg, dict):
            return api_cfg.get("api_key")  # type: ignore[return-value]
    return None


def load_config() -> dict[str, object]:
    """Load runtime configuration from standard paths."""
    try:
        from pipeline_utils import load_runtime_config

        return load_runtime_config()
    except Exception:
        return {}


# ── Main ──────────────────────────────────────────────────────


def run(
    *,
    input_epub: str,
    output: str,
    output_lang: str = "zh",
    model: str = "gemini-2.5-flash",
    provider: str = "cli",
    prompt: str | None = None,
    glossary: str | None = None,
    glossary_min_priority: str | None = None,
    cli_api_fallback: bool = False,
    max_batch_chars: int | None = None,
    config: dict[str, object] | None = None,
) -> None:
    """Execute the EPUB translation pipeline.

    This is the programmatic entry point — ``main()`` parses CLI args
    and delegates here.
    """
    runtime_config = config if config is not None else load_config()

    # 1. Resolve model
    resolved_model, is_pro = resolve_model(model, runtime_config)
    print(f"Model: {resolved_model} (pro={is_pro})")

    # 2. Create provider adapter
    provider_adapter = create_provider(
        provider,
        resolved_model,
        is_pro=is_pro,
        config=runtime_config,
        cli_api_fallback=cli_api_fallback,
    )

    # 3. Build system prompt
    language_name = _get_language_name(output_lang)
    glossary_block = load_glossary_block(
        glossary, min_priority=glossary_min_priority
    )
    system_prompt = build_system_prompt(
        language_name, glossary_block=glossary_block, custom_prompt=prompt
    )

    # 4. Configure engine
    batch_chars = max_batch_chars or (60_000 if is_pro else 10_000)
    engine_config = EngineConfig(
        system_prompt=system_prompt,
        max_batch_chars=batch_chars,
        separator_overhead=SEPARATOR_OVERHEAD,
    )
    engine = TranslationEngine(provider_adapter, engine_config)

    # 5. Create source adapter
    source = EpubSourceAdapter(input_epub)

    # 6. Execute
    print(f"Translating {input_epub} → {output} ({output_lang})")
    result = engine.translate(
        source,
        output,
        on_batch_translated=lambda i, total: print(
            f"  Batch {i + 1}/{total} done"
        ),
    )
    print(
        f"Done: {result.translated_segments} segments"
        f" in {result.total_batches} batches"
    )


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    run(
        input_epub=args.input_epub,
        output=args.output,
        output_lang=args.output_lang,
        model=args.model,
        provider=args.provider,
        prompt=args.prompt,
        glossary=args.glossary,
        glossary_min_priority=args.glossary_min_priority,
        cli_api_fallback=args.cli_api_fallback,
        max_batch_chars=args.max_batch_chars,
    )


if __name__ == "__main__":
    main()
