#!/usr/bin/env python3
"""Pipeline step 0: Extract terminology glossary from EPUB.

Usage:
    python 00_extract_glossary.py <input.epub> --output <glossary.json> [options]

This step is optional and runs before 01_prepare_env.py. It extracts critical
technical terms from the EPUB's Index and TOC documents and writes a structured
JSON glossary that subsequent translation steps can inject into prompts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract terminology glossary from EPUB (SPEC-010 Strategy A)"
    )
    parser.add_argument("input_epub", help="Source EPUB path")
    parser.add_argument(
        "--output",
        required=True,
        help="Output glossary JSON path (e.g. {temp_dir}/extracted_glossary.json)",
    )
    parser.add_argument(
        "--model",
        default="pro",
        help="Gemini model for extraction (default: pro). Accepts aliases: pro, flash, lite.",
    )
    parser.add_argument(
        "--max-terms",
        type=int,
        default=20,
        help="Maximum number of terms to extract (default: 20)",
    )
    parser.add_argument(
        "--full-index",
        action="store_true",
        help="Translate ALL top-level index entries (no filtering). Overrides --max-terms.",
    )
    parser.add_argument(
        "--provider",
        default="cli",
        choices=["cli", "api"],
        help="Provider to use for extraction (default: cli). Use 'api' to skip CLI.",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable automatic CLI→API fallback on CLI failure.",
    )
    return parser.parse_args()


def _load_config() -> dict:
    """Load runtime config to resolve model aliases and API key."""
    script_dir = Path(__file__).resolve().parent
    for path in [
        script_dir / "config" / "config.json",
        Path.home() / ".config" / "translatebook" / "config.json",
        script_dir / "config" / "config.json.example",
    ]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def _resolve_model(alias: str, config: dict) -> str:
    """Resolve model alias (pro/flash/lite) using config, fallback to built-in defaults."""
    _BUILTIN_ALIASES = {
        "pro": "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
        "lite": "gemini-2.5-flash-lite",
    }
    model_aliases = config.get("model_aliases", {})
    if isinstance(model_aliases, dict) and alias in model_aliases:
        return str(model_aliases[alias])
    return _BUILTIN_ALIASES.get(alias, alias)


def _get_api_key(config: dict) -> str:
    """Read API key from config or environment."""
    import os

    gemini_api = config.get("gemini_api", {})
    if isinstance(gemini_api, dict):
        key = gemini_api.get("api_key", "")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return os.environ.get("GEMINI_API_KEY", "")


def _make_cli_translate_fn(model: str) -> Callable[[str], str]:
    from ai.gemini_provider import GeminiProvider

    p = GeminiProvider(model=model)
    return lambda prompt: p.translate_chunk(prompt, 0, "", timeout_seconds=600)


def _make_api_translate_fn(model: str, api_key: str) -> Callable[[str], str]:
    from ai.gemini_api_provider import GeminiAPIProvider

    p = GeminiAPIProvider(model=model, api_key=api_key)
    return lambda prompt: p.translate_chunk(text=prompt, chunk_size=0, system_prompt="")


def _make_translate_fn_with_fallback(
    provider: str, model: str, config: dict, no_fallback: bool
) -> Callable[[str], str]:
    """Build a translate_fn that falls back CLI→API automatically on failure."""
    api_key = _get_api_key(config)

    if provider == "api":
        print(f"[glossary] Provider: API (model={model})", flush=True)
        return _make_api_translate_fn(model, api_key)

    cli_fn = _make_cli_translate_fn(model)

    if no_fallback or not api_key:
        if not api_key and not no_fallback:
            print("[glossary] Warning: no API key found, CLI→API fallback disabled", flush=True)
        print(f"[glossary] Provider: CLI (model={model}, no fallback)", flush=True)
        return cli_fn

    api_fn = _make_api_translate_fn(model, api_key)

    def cli_with_fallback(prompt: str) -> str:
        try:
            return cli_fn(prompt)
        except Exception as e:
            print(f"[glossary] CLI failed ({e}), retrying with API...", flush=True)
            return api_fn(prompt)

    print(f"[glossary] Provider: CLI with API fallback (model={model})", flush=True)
    return cli_with_fallback


def main() -> None:
    args = parse_arguments()
    epub_path = Path(args.input_epub).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not epub_path.exists():
        print(f"ERROR: Input EPUB not found: {epub_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config()
    model = _resolve_model(args.model, config)

    from ai.glossary_extractor import extract_glossary_from_epub

    translate_fn = _make_translate_fn_with_fallback(
        provider=args.provider,
        model=model,
        config=config,
        no_fallback=args.no_fallback,
    )
    extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=output_path,
        translate_fn=translate_fn,
        max_terms=args.max_terms,
        full_index=args.full_index,
    )


if __name__ == "__main__":
    main()

