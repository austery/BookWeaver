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
        default="gemini-2.5-pro",
        help="Gemini model for extraction (default: gemini-2.5-pro)",
    )
    parser.add_argument(
        "--max-terms",
        type=int,
        default=20,
        help="Maximum number of terms to extract (default: 20)",
    )
    parser.add_argument(
        "--provider",
        default="cli",
        choices=["cli", "api"],
        help="Provider to use for extraction (default: cli)",
    )
    return parser.parse_args()


def _make_translate_fn(provider: str, model: str) -> Callable[[str], str]:
    """Create a translate_fn callable for the given provider.

    Returns a function that takes a prompt string and returns the model's response.
    """
    if provider == "api":
        from ai.gemini_api_provider import GeminiAPIProvider
        import os

        api_key = os.environ.get("GEMINI_API_KEY", "")
        p = GeminiAPIProvider(model=model, api_key=api_key)
        return lambda prompt: p.translate_chunk(text=prompt, chunk_size=0, system_prompt="")
    else:
        from ai.gemini_provider import GeminiCLIProvider

        p = GeminiCLIProvider(model=model)
        return lambda prompt: p.translate_chunk(text=prompt, chunk_size=0, system_prompt="")


def main() -> None:
    args = parse_arguments()
    epub_path = Path(args.input_epub).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not epub_path.exists():
        print(f"ERROR: Input EPUB not found: {epub_path}", file=sys.stderr)
        sys.exit(1)

    from ai.glossary_extractor import extract_glossary_from_epub

    translate_fn = _make_translate_fn(args.provider, args.model)
    extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=output_path,
        translate_fn=translate_fn,
        max_terms=args.max_terms,
    )


if __name__ == "__main__":
    main()
