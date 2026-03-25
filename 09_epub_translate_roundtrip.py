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
        "--force-resume",
        action="store_true",
        help="Allow resuming with different model (may cause quality inconsistency)",
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
        force_resume=args.force_resume,
    )
    print(
        f"Translated roundtrip generated: {result.output_epub} "
        f"(docs={result.translated_docs}, segments={result.translated_segments})"
    )


if __name__ == "__main__":
    main()
