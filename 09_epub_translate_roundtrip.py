#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
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
    parser.add_argument(
        "--provider",
        default="cli",
        choices=["cli", "api"],
        help="Translation provider (cli or api, default: cli)",
    )
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


def load_runtime_config() -> dict[str, object]:
    script_dir = Path(__file__).resolve().parent
    bundled_config_path = script_dir / "config" / "config.json.example"
    workspace_config_path = script_dir / "config" / "config.json"
    user_config_path = Path.home() / ".config" / "translatebook" / "config.json"

    config: dict[str, object] = {}
    if bundled_config_path.exists():
        with open(bundled_config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update(loaded)

    if workspace_config_path.exists():
        with open(workspace_config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update(loaded)

    if user_config_path.exists():
        with open(user_config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update(loaded)
    return config


def resolve_api_key_from_config(config: dict[str, object]) -> str | None:
    gemini_api = config.get("gemini_api")
    if isinstance(gemini_api, dict):
        api_key = gemini_api.get("api_key")
        if isinstance(api_key, str) and api_key.strip():
            return api_key.strip()
    return None


def main() -> None:
    args = parse_arguments()
    source_epub = Path(args.input_epub).expanduser().resolve()
    output_epub = Path(args.output).expanduser().resolve()
    checkpoint_dir = (
        Path(args.checkpoint_dir).expanduser().resolve() if args.checkpoint_dir else None
    )
    runtime_config = load_runtime_config()
    api_key = resolve_api_key_from_config(runtime_config) if args.provider == "api" else None

    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        provider_name=args.provider,
        api_key=api_key,
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
