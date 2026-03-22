#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from ai.epub_translate_roundtrip import run_translate_roundtrip


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EPUB translate roundtrip mode")
    parser.add_argument("input_epub", help="Source EPUB path")
    parser.add_argument("--output", required=True, help="Output EPUB path")
    parser.add_argument("--output-lang", default="zh", help="Target language code (default: zh)")
    parser.add_argument(
        "--bilingual-style",
        default="alternating",
        choices=["alternating"],
        help="Bilingual style (currently alternating only)",
    )
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model name")
    parser.add_argument("-p", "--prompt", default=None, help="Additional translation instructions")
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Optional checkpoint directory for resume; if omitted, no checkpoint is written",
    )
    parser.add_argument(
        "--context-pass-mode",
        default="auto",
        choices=["auto", "off"],
        help="Context pass mode (default: auto)",
    )
    parser.add_argument(
        "--force-context-rebuild",
        action="store_true",
        help="Force rebuilding context artifacts",
    )
    parser.add_argument(
        "--context-max-paragraphs-per-doc",
        type=int,
        default=8,
        help="Max sampled paragraphs per context document (default: 8)",
    )
    parser.add_argument(
        "--context-max-paragraphs-total",
        type=int,
        default=120,
        help="Max sampled paragraphs across context documents (default: 120)",
    )
    parser.add_argument(
        "--audience",
        default=None,
        help="Target audience preset override (e.g. general|technical|academic|business)",
    )
    parser.add_argument(
        "--style",
        default=None,
        help=(
            "Translation style preset override "
            "(e.g. storytelling|formal|technical|literal|academic|business)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    source_epub = Path(args.input_epub).expanduser().resolve()
    output_epub = Path(args.output).expanduser().resolve()
    checkpoint_dir = (
        Path(args.checkpoint_dir).expanduser().resolve() if args.checkpoint_dir else None
    )

    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        custom_prompt=args.prompt,
        checkpoint_dir=checkpoint_dir,
        context_pass_mode=args.context_pass_mode,
        force_context_rebuild=args.force_context_rebuild,
        context_max_paragraphs_per_doc=args.context_max_paragraphs_per_doc,
        context_max_paragraphs_total=args.context_max_paragraphs_total,
        audience=args.audience,
        style=args.style,
    )
    print(
        f"Translated roundtrip generated: {result.output_epub} "
        f"(docs={result.translated_docs}, segments={result.translated_segments})"
    )


if __name__ == "__main__":
    main()
