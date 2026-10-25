#!/usr/bin/env python3
"""Extract EPUB terminology through the shared authorized provider boundary."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.glossary_extractor import extract_glossary_from_epub
from ai.model_profiles import resolve_profile
from ai.runtime_config import load_runtime_config
from ai.runtime_factory import DefaultProviderFactory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract EPUB terminology with Antigravity or an explicitly authorized API"
    )
    parser.add_argument("input_epub")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", choices=["flash", "pro"], default="pro")
    parser.add_argument("--effort", choices=["low", "medium", "high"])
    parser.add_argument("--provider", choices=["cli", "api"], default="cli")
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--max-terms", type=int, default=50)
    parser.add_argument("--full-index", action="store_true")
    parser.add_argument("--glossary-mode", choices=["auto", "deep-scan"], default="auto")
    parser.add_argument("--no-fallback", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.no_fallback:
        parser.error("Automatic fallback was removed; omit --no-fallback")
    if args.max_terms <= 0:
        parser.error("--max-terms must be positive")
    source = Path(args.input_epub).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".epub":
        parser.error("Input must be an existing EPUB file")
    if source == output:
        parser.error("Output must not overwrite the input")
    model = resolve_profile(args.model, effort=args.effort, provider=args.provider)
    config = load_runtime_config()
    characters = sum(len(segment.text) for segment in EpubSourceAdapter(source).get_segments())
    factory = DefaultProviderFactory(audit_directory=output.parent / ".bookweaver_runs")
    provider = factory.create(
        model,
        protocol="delimiter",
        config=config,
        allow_paid_api=args.allow_paid_api,
        remaining_chars=characters,
    )

    def translate(prompt: str) -> str:
        return provider.translate_batch([prompt], system_prompt="")[0]

    try:
        extract_glossary_from_epub(
            epub_path=source,
            output_path=output,
            translate_fn=translate,
            max_terms=args.max_terms,
            full_index=args.full_index,
            mode=args.glossary_mode,
        )
    finally:
        factory.persist_audit(
            {
                "provider": model.provider,
                "model": model.model_id,
                "effort": model.effort,
                "purpose": "glossary",
            }
        )


if __name__ == "__main__":
    main()
