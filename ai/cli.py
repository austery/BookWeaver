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
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
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
from ai.ports.source import TranslatedSegment

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
_CHECKPOINT_SCHEMA_VERSION = 1
_CHECKPOINT_ROOT = ".bookweaver_checkpoints"
_CHECKPOINT_STATE_FILE = "state.json"
_CHECKPOINT_TRANSLATIONS_FILE = "translations.json"


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


@dataclass(frozen=True)
class CheckpointMetadata:
    input_signature: str
    input_format: str
    output_lang: str
    model: str
    provider: str
    max_batch_chars: int
    separator_overhead: int
    system_prompt_hash: str


def _compute_input_signature(input_file: Path) -> str:
    stat = input_file.stat()
    payload = f"{input_file.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _checkpoint_state_file(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / _CHECKPOINT_STATE_FILE


def _checkpoint_translations_file(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / _CHECKPOINT_TRANSLATIONS_FILE


def _resolve_checkpoint_dir(
    *,
    checkpoint_dir: str | None,
    input_file: Path,
    output_file: Path,
    input_format: str,
) -> Path:
    if checkpoint_dir is not None:
        return Path(checkpoint_dir)
    return output_file.parent / _CHECKPOINT_ROOT / input_format / input_file.stem


def _build_checkpoint_metadata(
    *,
    input_file: Path,
    input_format: str,
    output_lang: str,
    model: str,
    provider: str,
    max_batch_chars: int,
    separator_overhead: int,
    system_prompt: str,
) -> CheckpointMetadata:
    return CheckpointMetadata(
        input_signature=_compute_input_signature(input_file),
        input_format=input_format,
        output_lang=output_lang,
        model=model,
        provider=provider,
        max_batch_chars=max_batch_chars,
        separator_overhead=separator_overhead,
        system_prompt_hash=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _persist_checkpoint(
    *,
    checkpoint_dir: Path,
    metadata: CheckpointMetadata,
    translations: dict[str, str],
) -> None:
    state_payload: dict[str, object] = {
        "schema_version": _CHECKPOINT_SCHEMA_VERSION,
        "input_signature": metadata.input_signature,
        "input_format": metadata.input_format,
        "output_lang": metadata.output_lang,
        "model": metadata.model,
        "provider": metadata.provider,
        "max_batch_chars": metadata.max_batch_chars,
        "separator_overhead": metadata.separator_overhead,
        "system_prompt_hash": metadata.system_prompt_hash,
        "translated_segment_count": len(translations),
    }
    translations_payload: dict[str, object] = {
        "schema_version": _CHECKPOINT_SCHEMA_VERSION,
        "segments": translations,
    }
    _write_json(_checkpoint_state_file(checkpoint_dir), state_payload)
    _write_json(_checkpoint_translations_file(checkpoint_dir), translations_payload)


def _load_checkpoint_translations(
    *,
    checkpoint_dir: Path,
    metadata: CheckpointMetadata,
    force_resume: bool,
) -> dict[str, str]:
    state_file = _checkpoint_state_file(checkpoint_dir)
    translations_file = _checkpoint_translations_file(checkpoint_dir)
    if not state_file.exists() or not translations_file.exists():
        return {}

    try:
        raw_state = json.loads(state_file.read_text(encoding="utf-8"))
        raw_translations = json.loads(translations_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[resume] Warning: failed to parse checkpoint files ({exc}), starting fresh.")
        return {}

    if not isinstance(raw_state, dict) or not isinstance(raw_translations, dict):
        print("[resume] Warning: invalid checkpoint schema, starting fresh.")
        return {}

    schema_errors = (
        ("state", raw_state.get("schema_version")),
        ("translation", raw_translations.get("schema_version")),
    )
    for schema_label, version in schema_errors:
        if version != _CHECKPOINT_SCHEMA_VERSION:
            print(f"[resume] Warning: checkpoint {schema_label} schema mismatch, starting fresh.")
            return {}

    hard_mismatches: list[str] = []
    if raw_state.get("input_signature") != metadata.input_signature:
        hard_mismatches.append("input signature")
    if raw_state.get("input_format") != metadata.input_format:
        hard_mismatches.append("input format")
    if hard_mismatches:
        print(
            f"[resume] Warning: checkpoint invalidated ({', '.join(hard_mismatches)} changed), starting fresh."
        )
        return {}

    soft_mismatches: list[str] = []
    expected_pairs: tuple[tuple[str, str | int], ...] = (
        ("output_lang", metadata.output_lang),
        ("model", metadata.model),
        ("provider", metadata.provider),
        ("max_batch_chars", metadata.max_batch_chars),
        ("separator_overhead", metadata.separator_overhead),
        ("system_prompt_hash", metadata.system_prompt_hash),
    )
    for key, expected in expected_pairs:
        if raw_state.get(key) != expected:
            soft_mismatches.append(key)

    if soft_mismatches and not force_resume:
        print(
            f"[resume] Warning: checkpoint invalidated ({', '.join(soft_mismatches)} mismatch). "
            "Use --force-resume to override."
        )
        return {}
    if soft_mismatches:
        print(
            f"[resume] Warning: forcing resume despite mismatched {', '.join(soft_mismatches)}."
        )

    segments_raw = raw_translations.get("segments")
    if not isinstance(segments_raw, dict):
        print("[resume] Warning: invalid translations payload, starting fresh.")
        return {}

    translations: dict[str, str] = {}
    for segment_id, translated_text in segments_raw.items():
        if not isinstance(segment_id, str) or not isinstance(translated_text, str):
            print("[resume] Warning: malformed checkpoint segment entry, starting fresh.")
            return {}
        translations[segment_id] = translated_text

    return translations


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
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint artifacts when available (EPUB workflow)",
    )
    p.add_argument(
        "--force-resume",
        action="store_true",
        help="Resume even when model/config changed (EPUB workflow)",
    )
    p.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Checkpoint directory path (default: <output-dir>/.bookweaver_checkpoints/<format>/<input-stem>)",
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

    rate_limit_backoff = _resolve_resilience_backoff(
        resilience,
        key="rate_limit_backoff_seconds",
        default=(60, 120),
    )
    transient_backoff = _resolve_resilience_backoff(
        resilience,
        key="transient_backoff_seconds",
        default=(45,),
    )

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


def _resolve_resilience_backoff(
    resilience: dict[str, object],
    *,
    key: str,
    default: tuple[int, ...],
) -> tuple[int, ...]:
    """Resolve and validate resilience backoff sequences from config."""
    raw = resilience.get(key, list(default))
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"{key} must be a list of positive integers")

    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"{key} values must be positive integers")
        values.append(item)
    return tuple(values)


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
    resume: bool = False,
    force_resume: bool = False,
    checkpoint_dir: str | None = None,
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
    resume_translations: dict[str, str] | None = None
    checkpoint_callback: Callable[[int, list[TranslatedSegment]], None] | None = None
    resume_enabled = resume or force_resume
    if resume_enabled:
        if fmt != "epub":
            print("Warning: Resume is only supported for EPUB input; ignoring resume flags.")
        else:
            checkpoint_path = _resolve_checkpoint_dir(
                checkpoint_dir=checkpoint_dir,
                input_file=input_file,
                output_file=Path(output),
                input_format=fmt,
            )
            checkpoint_metadata = _build_checkpoint_metadata(
                input_file=input_file,
                input_format=fmt,
                output_lang=output_lang,
                model=resolved_model,
                provider=provider,
                max_batch_chars=batch_chars,
                separator_overhead=SEPARATOR_OVERHEAD,
                system_prompt=system_prompt,
            )
            resume_translations = _load_checkpoint_translations(
                checkpoint_dir=checkpoint_path,
                metadata=checkpoint_metadata,
                force_resume=force_resume,
            )
            if resume_translations:
                print(
                    f"[resume] Loaded {len(resume_translations)} translated segments from {checkpoint_path}"
                )
            else:
                print(f"[resume] No compatible checkpoint found in {checkpoint_path}; starting fresh.")

            persisted_translations = dict(resume_translations)

            def _persist_batch(_batch_index: int, translated: list[TranslatedSegment]) -> None:
                for item in translated:
                    persisted_translations[item.id] = item.translated
                _persist_checkpoint(
                    checkpoint_dir=checkpoint_path,
                    metadata=checkpoint_metadata,
                    translations=persisted_translations,
                )

            checkpoint_callback = _persist_batch

    engine_config = EngineConfig(
        system_prompt=system_prompt,
        max_batch_chars=batch_chars,
        separator_overhead=SEPARATOR_OVERHEAD,
        resume_translations=resume_translations,
        on_checkpoint_batch=checkpoint_callback,
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
        resume=args.resume,
        force_resume=args.force_resume,
        checkpoint_dir=args.checkpoint_dir,
    )


if __name__ == "__main__":
    main()
