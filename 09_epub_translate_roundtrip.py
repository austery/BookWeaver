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
    parser.add_argument(
        "--cli-api-fallback",
        action="store_true",
        help="Enable fallback from CLI provider to API provider on CLI failures",
    )
    parser.add_argument("-p", "--prompt", default=None, help="Additional translation instructions")
    parser.add_argument(
        "--glossary",
        default=None,
        help="Path to extracted glossary JSON (from 00_extract_glossary.py)",
    )
    parser.add_argument(
        "--glossary-min-priority",
        default=None,
        choices=["critical", "high", "medium"],
        help="Only inject glossary terms at this priority or higher (default: all terms).",
    )
    parser.add_argument(
        "--only-docs",
        default=None,
        help="Comma-separated list of spine doc filenames to translate (e.g. kindle_split_013.html,kindle_split_015.html). Others are passed through untranslated.",
    )
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


def _to_int_tuple(value: object, *, field_name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of positive integers")
    resolved: list[int] = []
    for item in value:
        if not isinstance(item, int) or item <= 0:
            raise ValueError(f"{field_name} must contain positive integers only")
        resolved.append(item)
    return tuple(resolved)


def resolve_epub_resilience_config(config: dict[str, object]) -> dict[str, object]:
    raw = config.get("epub_resilience")
    if not isinstance(raw, dict):
        return {}

    resolved: dict[str, object] = {}
    if "rate_limit_backoff_seconds" in raw:
        value = raw["rate_limit_backoff_seconds"]
        if value is not None:
            resolved["rate_limit_backoff_seconds"] = _to_int_tuple(
                value, field_name="rate_limit_backoff_seconds"
            )
    if "timeout_backoff_seconds" in raw:
        value = raw["timeout_backoff_seconds"]
        if value is not None:
            resolved["timeout_backoff_seconds"] = _to_int_tuple(
                value, field_name="timeout_backoff_seconds"
            )
    if "transient_backoff_seconds" in raw:
        value = raw["transient_backoff_seconds"]
        if value is not None:
            resolved["transient_backoff_seconds"] = _to_int_tuple(
                value, field_name="transient_backoff_seconds"
            )
    if "max_split_depth" in raw:
        value = raw["max_split_depth"]
        if value is not None:
            if not isinstance(value, int) or value < 0:
                raise ValueError("max_split_depth must be >= 0")
            resolved["max_split_depth"] = value
    if "doc_failure_budget" in raw:
        value = raw["doc_failure_budget"]
        if value is not None:
            if not isinstance(value, int) or value <= 0:
                raise ValueError("doc_failure_budget must be > 0")
            resolved["doc_failure_budget"] = value
    if "cli_api_fallback_enabled" in raw:
        value = raw["cli_api_fallback_enabled"]
        if value is not None:
            if not isinstance(value, bool):
                raise ValueError("cli_api_fallback_enabled must be boolean")
            resolved["cli_api_fallback_enabled"] = value
    if "pro_timeout_seconds" in raw:
        value = raw["pro_timeout_seconds"]
        if value is not None:
            if not isinstance(value, int) or value <= 0:
                raise ValueError("pro_timeout_seconds must be > 0")
            resolved["pro_timeout_seconds"] = value
    if "non_pro_timeout_seconds" in raw:
        value = raw["non_pro_timeout_seconds"]
        if value is not None:
            if not isinstance(value, int) or value <= 0:
                raise ValueError("non_pro_timeout_seconds must be > 0")
            resolved["non_pro_timeout_seconds"] = value
    if "failed_docs_path" in raw:
        value = raw["failed_docs_path"]
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("failed_docs_path must be a non-empty string")
            resolved["failed_docs_path"] = str(Path(value).expanduser().resolve())

    return resolved


def main() -> None:
    args = parse_arguments()
    source_epub = Path(args.input_epub).expanduser().resolve()
    output_epub = Path(args.output).expanduser().resolve()
    checkpoint_dir = (
        Path(args.checkpoint_dir).expanduser().resolve() if args.checkpoint_dir else None
    )
    glossary_path = Path(args.glossary).expanduser().resolve() if args.glossary else None
    only_docs = set(args.only_docs.split(",")) if args.only_docs else None
    glossary_min_priority = args.glossary_min_priority
    runtime_config = load_runtime_config()
    api_key = resolve_api_key_from_config(runtime_config) if args.provider == "api" else None
    resilience_overrides = resolve_epub_resilience_config(runtime_config)
    if "failed_docs_path" in resilience_overrides:
        resilience_overrides["failed_docs_path"] = Path(
            str(resilience_overrides["failed_docs_path"])
        )
    if args.cli_api_fallback:
        resilience_overrides["cli_api_fallback_enabled"] = True

    result = run_translate_roundtrip(
        source_epub=source_epub,
        output_epub=output_epub,
        output_lang=args.output_lang,
        bilingual_style=args.bilingual_style,
        model=args.model,
        config=runtime_config,
        provider_name=args.provider,
        api_key=api_key,
        custom_prompt=args.prompt,
        checkpoint_dir=checkpoint_dir,
        force_resume=args.force_resume,
        glossary_path=glossary_path,
        only_docs=only_docs,
        glossary_min_priority=glossary_min_priority,
        **resilience_overrides,
    )
    print(
        f"Translated roundtrip generated: {result.output_epub} "
        f"(docs={result.translated_docs}, segments={result.translated_segments})"
    )


if __name__ == "__main__":
    main()
