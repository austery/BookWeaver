"""Unified CLI entry point for BookWeaver translation.

This is the **composition root** — it wires ports, core, and adapters
together.  It lives outside the hexagonal boundary modules and is
allowed to import from all layers.

Usage:
    python -m ai.cli input.epub --output translated.epub [options]
    python -m ai.cli ./pages_dir/ --output translated.md [options]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ai.adapters.providers._delimiter import SEPARATOR_OVERHEAD
from ai.adapters.providers.gemini_api_adapter import GeminiAPIAdapter
from ai.adapters.providers.gemini_cli_adapter import GeminiCLIAdapter
from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.adapters.sources.markdown_adapter import MarkdownSourceAdapter
from ai.adapters.sources.pdf_adapter import PdfSourceAdapter
from ai.core.config import ConfigRegistry
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


# ── Format detection ──────────────────────────────────────────


_FORMAT_MAP: dict[str, str] = {
    ".epub": "epub",
    ".md": "markdown",
    ".pdf": "pdf",
}


def detect_input_format(input_path: str) -> str:
    """Detect input format from path.

    Returns ``"markdown"`` for directories or ``.md`` files,
    ``"pdf"`` for ``.pdf`` files, ``"epub"`` for ``.epub``,
    and ``"epub"`` as default.
    """
    p = Path(input_path)
    if p.is_dir():
        return "markdown"
    suffix = p.suffix.lower()
    return _FORMAT_MAP.get(suffix, "epub")


# ── Argument parsing ──────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser (compatible with legacy 09_*.py flags)."""
    p = argparse.ArgumentParser(
        prog="bookweaver",
        description="Translate books using the hexagonal translation engine.",
    )
    p.add_argument(
        "input_path",
        help="Source file (.epub/.pdf) or directory of page*.md files",
    )
    p.add_argument("--output", required=True, help="Output path")
    p.add_argument("--output-lang", default="zh", help="Target language code (default: zh)")
    p.add_argument("--model", default="gemini-2.5-flash", help="Gemini model name or alias")
    p.add_argument(
        "--provider",
        choices=["cli", "api"],
        default="cli",
        help="Translation backend (default: cli)",
    )
    p.add_argument("-p", "--prompt", default=None, help="Additional translation instructions")
    p.add_argument(
        "--extract-glossary",
        action="store_true",
        help="Auto-extract glossary before translation (EPUB input only)",
    )
    p.add_argument("--glossary", default=None, help="Path to extracted glossary JSON")
    p.add_argument(
        "--glossary-min-priority",
        default=None,
        choices=["critical", "high", "medium"],
        help="Minimum glossary term priority",
    )
    p.add_argument(
        "--glossary-max-terms",
        type=int,
        default=None,
        help="Max terms when auto-extracting glossary (EPUB input only)",
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
    p.add_argument(
        "--input-format",
        choices=["auto", "epub", "markdown", "pdf"],
        default="auto",
        help="Input format (default: auto-detect from path)",
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

    return GlossaryInjector(Path(glossary_path)).format_block(min_priority=min_priority) or None


def _resolve_extraction_temp_dir(input_path: str) -> Path:
    """Resolve glossary extraction workspace path."""
    input_name = Path(input_path).name
    return Path(f"{Path(input_name).stem}_temp")


def _extract_glossary_to_path(
    *,
    epub_path: Path,
    output_path: Path,
    provider_adapter: ITranslationProvider,
    max_terms: int = 20,
) -> None:
    """Extract glossary JSON from EPUB and write to output_path."""
    from ai.glossary_extractor import extract_glossary_from_epub

    def translate_fn(prompt: str) -> str:
        translated = provider_adapter.translate_batch([prompt], system_prompt="")
        if not translated:
            msg = "Glossary extraction returned empty response"
            raise RuntimeError(msg)
        return translated[0]

    extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=output_path,
        translate_fn=translate_fn,
        max_terms=max_terms,
        full_index=False,
    )


def resolve_model(
    model_name: str,
    config: dict[str, object] | None = None,
    *,
    explicit: bool = False,
) -> tuple[str, bool]:
    """Resolve model alias and detect pro tier.

    Returns:
        (resolved_model_name, is_pro)
    """
    try:
        from ai.model_resolver import ModelResolver

        resolver = ModelResolver(config or {})
        resolved = resolver.resolve_alias(model_name) if explicit else resolver.resolve(model_name)
        return resolved.name, getattr(resolved, "role", None) is not None and str(
            getattr(resolved, "role", "")
        ).endswith("PRO")
    except Exception as exc:
        import sys

        print(f"Warning: model resolution failed ({exc}), using fallback", file=sys.stderr)
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
        project_root = Path(__file__).resolve().parent.parent
        config_paths = [
            project_root / "config" / "config.json.example",
            project_root / "config" / "config.json",
            Path.home() / ".config" / "translatebook" / "config.json",
        ]
        return ConfigRegistry.from_json_files(config_paths).to_dict()
    except Exception as exc:
        import sys

        print(f"Warning: config load failed ({exc}), using defaults", file=sys.stderr)
        return {}


# ── Main ──────────────────────────────────────────────────────


def run(
    *,
    input_path: str,
    output: str,
    output_lang: str = "zh",
    model: str = "gemini-2.5-flash",
    provider: str = "cli",
    prompt: str | None = None,
    extract_glossary: bool = False,
    glossary: str | None = None,
    glossary_min_priority: str | None = None,
    glossary_max_terms: int | None = None,
    cli_api_fallback: bool = False,
    max_batch_chars: int | None = None,
    input_format: str = "auto",
    model_explicit: bool = False,
    config: dict[str, object] | None = None,
) -> None:
    """Execute the translation pipeline.

    This is the programmatic entry point — ``main()`` parses CLI args
    and delegates here.
    """
    runtime_config = config if config is not None else load_config()

    # 1. Resolve model
    resolved_model, is_pro = resolve_model(model, runtime_config, explicit=model_explicit)
    if not model_explicit:
        primary_model, _ = resolve_model(model, runtime_config, explicit=True)
        is_genuine_fallback = primary_model != resolved_model and resolved_model != model
        if is_genuine_fallback:
            print(
                f"Auto model fallback: primary {primary_model} unavailable, using {resolved_model}."
            )
    print(f"Model: {resolved_model} (pro={is_pro})")

    # 2. Create provider adapter
    provider_adapter = create_provider(
        provider,
        resolved_model,
        is_pro=is_pro,
        config=runtime_config,
        cli_api_fallback=cli_api_fallback,
    )

    # 3. Validate input and detect/resolve format
    input_file = Path(input_path)
    if not input_file.exists():
        msg = f"Input path does not exist: {input_path}"
        raise FileNotFoundError(msg)

    fmt = input_format if input_format != "auto" else detect_input_format(input_path)

    if glossary_max_terms is not None and glossary_max_terms <= 0:
        msg = f"glossary_max_terms must be > 0, got {glossary_max_terms}"
        raise ValueError(msg)

    effective_glossary = glossary
    if extract_glossary:
        if fmt != "epub":
            print(
                "Warning: Glossary extraction is only supported for EPUBs; ignoring --extract-glossary."
            )
        else:
            temp_dir = _resolve_extraction_temp_dir(input_path)
            temp_dir.mkdir(parents=True, exist_ok=True)
            extracted_glossary = temp_dir / "extracted_glossary.json"
            print(f"[glossary] Extracting glossary to: {extracted_glossary}")
            extract_model, extract_is_pro = resolve_model("pro", runtime_config)
            extract_provider_adapter = create_provider(
                provider,
                extract_model,
                is_pro=extract_is_pro,
                config=runtime_config,
                cli_api_fallback=cli_api_fallback,
            )
            _extract_glossary_to_path(
                epub_path=input_file,
                output_path=extracted_glossary,
                provider_adapter=extract_provider_adapter,
                max_terms=glossary_max_terms or 20,
            )
            effective_glossary = str(extracted_glossary)

    # 4. Build system prompt
    language_name = _get_language_name(output_lang)
    glossary_block = load_glossary_block(effective_glossary, min_priority=glossary_min_priority)
    system_prompt = build_system_prompt(
        language_name, glossary_block=glossary_block, custom_prompt=prompt
    )

    # 5. Configure engine
    batch_chars = max_batch_chars or (60_000 if is_pro else 10_000)
    engine_config = EngineConfig(
        system_prompt=system_prompt,
        max_batch_chars=batch_chars,
        separator_overhead=SEPARATOR_OVERHEAD,
    )
    engine = TranslationEngine(provider_adapter, engine_config)

    # 6. Create source adapter (format routing)
    if fmt == "markdown":
        md_dir = str(input_file) if input_file.is_dir() else str(input_file.parent)
        md_dir_path = Path(md_dir)
        if not md_dir_path.is_dir():
            msg = f"Markdown directory does not exist: {md_dir}"
            raise FileNotFoundError(msg)
        if not list(md_dir_path.glob("page*.md")):
            msg = f"No page*.md files found in: {md_dir}"
            raise FileNotFoundError(msg)
        source = MarkdownSourceAdapter(md_dir)
    elif fmt == "pdf":
        source = PdfSourceAdapter(input_path)
    else:
        source = EpubSourceAdapter(input_path)

    # 7. Execute
    print(f"Translating {input_path} → {output} ({output_lang})")
    result = engine.translate(
        source,
        output,
        on_batch_translated=lambda i, total: print(f"  Batch {i + 1}/{total} done"),
    )
    print(f"Done: {result.translated_segments} segments in {result.total_batches} batches")


def _is_model_flag_explicit(argv: list[str] | None) -> bool:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    return any(token == "--model" or token.startswith("--model=") for token in args)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    model_explicit = _is_model_flag_explicit(argv)

    run(
        input_path=args.input_path,
        output=args.output,
        output_lang=args.output_lang,
        model=args.model,
        model_explicit=model_explicit,
        provider=args.provider,
        prompt=args.prompt,
        extract_glossary=args.extract_glossary,
        glossary=args.glossary,
        glossary_min_priority=args.glossary_min_priority,
        glossary_max_terms=args.glossary_max_terms,
        cli_api_fallback=args.cli_api_fallback,
        max_batch_chars=args.max_batch_chars,
        input_format=args.input_format,
    )


if __name__ == "__main__":
    main()
