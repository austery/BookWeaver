#!/usr/bin/env python3
"""
Step 3: Translate markdown files using Gemini CLI
Translates each pageXXXX.md file to output_pageXXXX.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict

from ai.gemini_provider import GeminiProvider
from ai.model_probe import ModelProbe
from ai.model_resolver import ModelResolver
from ai.model_selector import ModelSelector
from pipeline_utils import load_pipeline_config, get_language_name


class RuntimeConfig(TypedDict, total=False):
    """Typed configuration dict for the translation pipeline runtime."""

    default_model: str
    prompt_profile: str
    prompt_templates: dict[str, str]
    model_aliases: dict[str, str]
    fallback_chain: list[str]
    model_probe: dict[str, object]
    model_thresholds: dict[str, dict[str, object]]
    enable_fallback: bool
    output_format: str
    bilingual_style: str


def check_gemini_cli() -> bool:
    """Check if Gemini CLI is available"""
    try:
        result = subprocess.run(["gemini", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_info = result.stdout.strip().split("\n")[-1]
            print(f"Gemini CLI available: {version_info}")
            return True
        print(f"Gemini CLI check failed with code {result.returncode}")
        return False
    except subprocess.TimeoutExpired:
        print("Error: Gemini CLI version check timed out")
        return False
    except FileNotFoundError:
        print("Error: 'gemini' command not found")
        print("Please ensure Gemini CLI is installed and in your PATH")
        return False
    except Exception as e:
        print(f"Error checking Gemini CLI: {e}")
        return False


def _deep_merge_dict(base: RuntimeConfig, override: RuntimeConfig) -> RuntimeConfig:
    """Deep-merge two RuntimeConfig dicts; override values win on conflict."""
    result = _deep_merge_dict_impl(dict(base), dict(override))
    return result  # type: ignore[return-value]


def _deep_merge_dict_impl(
    base: dict[str, object], override: dict[str, object]
) -> dict[str, object]:
    """Recursive implementation for _deep_merge_dict."""
    result: dict[str, object] = dict(base)
    for key, value in override.items():
        base_val = result.get(key)
        if isinstance(base_val, dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict_impl(base_val, value)
        else:
            result[key] = value
    return result


def load_runtime_config() -> RuntimeConfig:
    """Load config from bundled example and user override."""
    script_dir = Path(__file__).resolve().parent
    bundled_config_path = script_dir / "config" / "config.json.example"
    user_config_path = Path.home() / ".config" / "translatebook" / "config.json"

    config: RuntimeConfig = {}

    if bundled_config_path.exists():
        try:
            with open(bundled_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"Bundled config '{bundled_config_path}' is not valid JSON: {exc.msg}",
                exc.doc,
                exc.pos,
            ) from exc

    if user_config_path.exists():
        try:
            with open(user_config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"User config '{user_config_path}' is not valid JSON — check for syntax errors: {exc.msg}",
                exc.doc,
                exc.pos,
            ) from exc
        config = _deep_merge_dict(config, user_config)

    if "default_model" not in config:
        config["default_model"] = "gemini-2.5-flash"
    if "prompt_profile" not in config:
        config["prompt_profile"] = "default"
    prompt_templates = config.get("prompt_templates")
    if not isinstance(prompt_templates, dict):
        prompt_templates = {}
    prompt_templates.setdefault("default", "config/prompts/default_prompt.txt")
    prompt_templates.setdefault("ebook", "config/prompts/ebook_prompt.txt")
    config["prompt_templates"] = prompt_templates
    model_aliases = config.get("model_aliases")
    if not isinstance(model_aliases, dict):
        model_aliases = {}
    config["model_aliases"] = model_aliases
    fallback_chain = config.get("fallback_chain")
    if not isinstance(fallback_chain, list):
        fallback_chain = []
    config["fallback_chain"] = fallback_chain
    model_probe = config.get("model_probe")
    if not isinstance(model_probe, dict):
        model_probe = {}
    model_probe.setdefault("enabled", True)
    model_probe.setdefault("cache_ttl_seconds", 3600)
    model_probe.setdefault("cache_path", "~/.cache/bookweaver/model_probe_cache.json")
    model_probe.setdefault(
        "candidates",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    )
    config["model_probe"] = model_probe

    return config


def load_prompt_template(runtime_config: RuntimeConfig | None = None) -> str:
    """Load prompt template using profile name from runtime config."""
    script_dir = Path(__file__).resolve().parent
    config = runtime_config or {}
    profile = str(config.get("prompt_profile", "default"))
    configured_templates = config.get("prompt_templates")
    templates: dict[str, str] = {
        "default": "config/prompts/default_prompt.txt",
        "ebook": "config/prompts/ebook_prompt.txt",
    }
    if isinstance(configured_templates, dict):
        templates.update(
            {
                key: value
                for key, value in configured_templates.items()
                if isinstance(key, str) and isinstance(value, str) and value.strip()
            }
        )

    template_path_raw = templates.get(profile) or templates.get("default")
    if not template_path_raw:
        raise ValueError("No prompt template path configured")

    template_path = Path(template_path_raw)
    if not template_path.is_absolute():
        template_path = script_dir / template_path

    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    template_content = template_path.read_text(encoding="utf-8").strip()
    if not template_content:
        raise ValueError(f"Prompt template is empty: {template_path}")
    return template_content


def resolve_model_name(requested_model: str, runtime_config: RuntimeConfig | None = None) -> str:
    """Shim: alias-only resolution. Use ModelResolver directly for new code."""
    return ModelResolver(runtime_config or {}).resolve_alias(requested_model).name


def build_model_candidates(
    requested_model: str, runtime_config: RuntimeConfig | None = None
) -> list[str]:
    """Shim: returns alias-resolved primary + fallback chain. Use ModelResolver for new code."""
    config = runtime_config or {}
    primary = ModelResolver(config).resolve_alias(requested_model).name
    candidates: list[str] = [primary]
    if bool(config.get("enable_fallback", True)):
        fallback_chain = config.get("fallback_chain")
        if isinstance(fallback_chain, list):
            resolver = ModelResolver(config)
            for raw_fallback in fallback_chain:
                if not isinstance(raw_fallback, str) or not raw_fallback.strip():
                    continue
                resolved_fallback = resolver.resolve_alias(raw_fallback).name
                if resolved_fallback not in candidates:
                    candidates.append(resolved_fallback)
    return candidates


def _create_model_probe(runtime_config: RuntimeConfig) -> ModelProbe | None:
    """Shim: kept for backward compat. ModelResolver creates probes internally."""
    probe_config_raw = runtime_config.get("model_probe")
    if not isinstance(probe_config_raw, dict):
        return None
    if not bool(probe_config_raw.get("enabled", True)):
        return None

    ttl_raw = probe_config_raw.get("cache_ttl_seconds", 3600)
    ttl_seconds = int(ttl_raw) if isinstance(ttl_raw, (int, float)) else 3600
    cache_path_raw = probe_config_raw.get(
        "cache_path", "~/.cache/bookweaver/model_probe_cache.json"
    )
    cache_path = Path(str(cache_path_raw)).expanduser()
    return ModelProbe(cache_path=cache_path, ttl_seconds=max(ttl_seconds, 0))


def select_model_with_fallback(
    requested_model: str,
    runtime_config: RuntimeConfig | None = None,
    probe: ModelProbe | None = None,
) -> str:
    """Shim: full resolution with probe/fallback. Use ModelResolver directly for new code."""
    config = runtime_config or {}
    # Preserve legacy default: enable_fallback was True when not explicitly set
    if "enable_fallback" not in config:
        config = {**config, "enable_fallback": True}
    return ModelResolver(config, probe=probe).resolve(requested_model).name


def print_model_selection_preview(requested_model: str, runtime_config: RuntimeConfig) -> None:
    """Print model resolution details without translating files."""
    resolver = ModelResolver(runtime_config)
    alias_result = resolver.resolve_alias(requested_model)
    full_result = resolver.resolve(requested_model)
    print("Model selection preview:")
    print(f"  Requested: {requested_model}")
    if alias_result.name != requested_model:
        print(f"  Alias resolved: {requested_model} -> {alias_result.name}")
    if full_result.name != alias_result.name:
        print(f"  Fallback selected: {alias_result.name} -> {full_result.name}")
    print(f"  Final selected model: {full_result.name}")


def create_translation_prompt(
    output_lang: str,
    custom_prompt: str | None = None,
    runtime_config: RuntimeConfig | None = None,
    glossary_path: Path | None = None,
) -> str:
    """Create translation prompt with optional glossary constraints and custom additions."""
    lang_name = get_language_name(output_lang)
    template = load_prompt_template(runtime_config)

    glossary_block = ""
    if glossary_path is not None:
        from ai.glossary_injector import GlossaryInjector

        glossary_block = GlossaryInjector(glossary_path).format_block()

    custom_block = f"ADDITIONAL INSTRUCTIONS:\n{custom_prompt}" if custom_prompt else ""

    prompt = template.replace("{TARGET_LANGUAGE}", lang_name)
    prompt = prompt.replace("{GLOSSARY_BLOCK}", glossary_block)

    has_custom_placeholder = "{CUSTOM_INSTRUCTIONS_BLOCK}" in prompt
    if has_custom_placeholder:
        prompt = prompt.replace("{CUSTOM_INSTRUCTIONS_BLOCK}", custom_block)
    elif custom_block:
        prompt = f"{prompt.rstrip()}\n\n{custom_block}"

    prompt = prompt.rstrip()
    # "markdown文件正文:" is a hardcoded Chinese label that marks the
    # start of the document body in the translation prompt. It is intentionally
    # written in Chinese because the prompt targets Chinese-speaking models
    # and the label helps the model identify where the content begins.
    return f"{prompt}\n\n markdown文件正文:"


def translate_with_gemini_cli(
    text: str,
    output_lang: str,
    model: str,
    custom_prompt: str | None = None,
    max_retries: int = 3,
    runtime_config: RuntimeConfig | None = None,
) -> str | None:
    """Translate text using Gemini CLI via GeminiProvider."""
    prompt = create_translation_prompt(output_lang, custom_prompt, runtime_config=runtime_config)

    for attempt in range(max_retries):
        if attempt > 0:
            print(f"    Retry attempt {attempt + 1}/{max_retries}")
            time.sleep(1)

        try:
            provider = GeminiProvider(model=model)
            translated_text = provider.translate_chunk(
                text=text,
                chunk_size=len(text),
                system_prompt=prompt,
            )
            if translated_text.strip():
                return translated_text
            print(f"    Attempt {attempt + 1}: empty Gemini response")
        except Exception as e:
            print(f"    Attempt {attempt + 1}: Gemini translation error: {e}")

    print(f"    ✗ Translation failed after {max_retries} attempts, skipping file")
    return None


def append_progress_log(
    log_path: Path,
    *,
    filename: str,
    status: str,
    elapsed_seconds: float,
    model: str | None = None,
    message: str | None = None,
) -> None:
    """Append a JSONL progress entry for resumable translation visibility."""
    record: dict[str, str | float] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "filename": filename,
        "status": status,
        "elapsed_seconds": round(max(elapsed_seconds, 0.0), 3),
    }
    if model:
        record["model"] = model
    if message:
        record["message"] = message
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def translate_markdown_files(
    temp_dir: str,
    output_lang: str,
    custom_prompt: str | None = None,
    forced_model: str | None = None,
    runtime_config: RuntimeConfig | None = None,
    resume: bool = True,
) -> None:
    """Translate all markdown files in temp directory"""
    print(f"Translating markdown files to {output_lang}...")
    if custom_prompt:
        print(f"Using custom prompt: {custom_prompt[:100]}...")

    config = runtime_config or {}
    print(f"Prompt profile: {config.get('prompt_profile', 'default')}")
    print(f"Resume mode: {'enabled' if resume else 'disabled'}")
    selector = None
    probe = _create_model_probe(config)
    # Preserve legacy default: enable_fallback was True when not explicitly set
    resolver_config = config if "enable_fallback" in config else {**config, "enable_fallback": True}
    resolver = ModelResolver(resolver_config, probe=probe)
    thresholds = config.get("model_thresholds")
    if isinstance(thresholds, dict):
        try:
            selector = ModelSelector(config)
        except Exception as e:
            print(f"Warning: Invalid model thresholds in config, fallback to default model: {e}")

    # Find all pageXXXX.md files
    md_files = glob.glob(os.path.join(temp_dir, "page*.md"))
    md_files.sort()

    if not md_files:
        print("Error: No markdown files found. Run 02_split_to_md.py first.")
        sys.exit(1)

    total_files = len(md_files)
    translated_count = 0
    skipped_count = 0
    failed_count = 0
    start_time = time.perf_counter()
    progress_log_path = Path(temp_dir) / "translation_progress.log"
    print(f"Progress log: {progress_log_path}")

    for i, md_file in enumerate(md_files, 1):
        file_start_time = time.perf_counter()
        filename = os.path.basename(md_file)
        output_filename = f"output_{filename}"
        output_path = os.path.join(temp_dir, output_filename)

        # Skip if output file already exists (resume mode)
        if resume and os.path.exists(output_path):
            print(f"  [{i}/{total_files}] Skipping {filename} (already translated)")
            skipped_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="skipped_existing",
                elapsed_seconds=time.perf_counter() - file_start_time,
            )
            continue

        print(f"  [{i}/{total_files}] Translating {filename}...")

        # Read input file
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"    Error reading {filename}: {e}")
            failed_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="failed_read",
                elapsed_seconds=time.perf_counter() - file_start_time,
                message=str(e),
            )
            continue

        # Skip if file is empty or very short
        if len(content.strip()) < 1:
            print(f"    Skipping {filename} (too short)")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            skipped_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="skipped_short",
                elapsed_seconds=time.perf_counter() - file_start_time,
            )
            continue

        selected_model = forced_model
        if not selected_model:
            if selector is not None:
                selected_model = selector.select(len(content))
            else:
                selected_model = config.get("default_model", "gemini-2.5-flash")

        requested_model = selected_model
        try:
            resolved = resolver.resolve(requested_model)
            selected_model = resolved.name
        except Exception as e:
            print(f"    Error selecting model for {filename}: {e}")
            failed_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="failed_model_selection",
                elapsed_seconds=time.perf_counter() - file_start_time,
                message=str(e),
            )
            continue

        alias_resolved = resolver.resolve_alias(requested_model).name
        if alias_resolved != requested_model:
            print(f"    Model alias resolved: {requested_model} -> {alias_resolved}")
        if selected_model != alias_resolved:
            print(f"    Model fallback selected: {alias_resolved} -> {selected_model}")
        print(f"    Model: {selected_model}")
        translated_content = translate_with_gemini_cli(
            content,
            output_lang,
            selected_model,
            custom_prompt,
            runtime_config=config,
        )

        if translated_content:
            # Save translated content
            try:
                temp_output_path = f"{output_path}.tmp"
                with open(temp_output_path, "w", encoding="utf-8") as f:
                    f.write(translated_content)
                os.replace(temp_output_path, output_path)
                print(f"    ✓ Translated and saved to {output_filename}")
                translated_count += 1
                append_progress_log(
                    progress_log_path,
                    filename=filename,
                    status="translated",
                    elapsed_seconds=time.perf_counter() - file_start_time,
                    model=selected_model,
                )
            except Exception as e:
                print(f"    Error saving {output_filename}: {e}")
                failed_count += 1
                append_progress_log(
                    progress_log_path,
                    filename=filename,
                    status="failed_save",
                    elapsed_seconds=time.perf_counter() - file_start_time,
                    model=selected_model,
                    message=str(e),
                )
        else:
            # Translation failed after all retries - skip file creation completely
            print(f"    ✗ Failed to translate {filename} after retries, skipping file creation")
            failed_count += 1
            append_progress_log(
                progress_log_path,
                filename=filename,
                status="failed_translation",
                elapsed_seconds=time.perf_counter() - file_start_time,
                model=selected_model,
            )

        # Add delay to avoid rate limits
        if i < total_files:
            time.sleep(0.5)  # Reduced delay for CLI

    total_elapsed = time.perf_counter() - start_time
    print(f"\nTranslation complete:")
    print(f"  Translated: {translated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {total_files}")
    print(f"  Elapsed: {total_elapsed:.1f}s")
    print(f"  Progress log: {progress_log_path}")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Book Translation Tool - Step 3: Translate Markdown using Gemini CLI"
    )

    parser.add_argument(
        "-p",
        "--prompt",
        default=None,
        help="Additional custom prompt to add to the translation instructions",
    )

    parser.add_argument("--temp-dir", required=True, help="Temp directory path (required)")

    parser.add_argument("--output-lang", default=None, help="Override output language from config")

    parser.add_argument(
        "--retry-failed", action="store_true", help="Retry translating files that failed previously"
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Force model for all chunks. Accepts aliases or full model names.",
    )

    parser.add_argument(
        "--preview-model-selection",
        action="store_true",
        help="Preview prompt profile and model resolution chain without translating files.",
    )

    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Disable model probe (useful for no-side-effect previews).",
    )

    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume mode and re-translate even when output_page*.md already exists.",
    )

    return parser.parse_args()


def main() -> None:
    """Main function"""
    print("=== Book Translation Tool - Step 3: Translate Markdown (Gemini CLI) ===")

    # Parse arguments
    args = parse_arguments()

    # Check Gemini CLI availability
    if not check_gemini_cli():
        sys.exit(1)

    runtime_config = load_runtime_config()
    print(f"Prompt profile: {runtime_config.get('prompt_profile', 'default')}")
    fallback_chain = runtime_config.get("fallback_chain")
    if isinstance(fallback_chain, list) and fallback_chain:
        print(f"Fallback chain: {' -> '.join(str(item) for item in fallback_chain)}")
    probe_config = runtime_config.get("model_probe")
    if isinstance(probe_config, dict) and bool(probe_config.get("enabled", True)):
        print(
            "Model probe: enabled "
            f"(ttl={probe_config.get('cache_ttl_seconds', 3600)}s, "
            f"cache={probe_config.get('cache_path', '~/.cache/bookweaver/model_probe_cache.json')})"
        )
    if args.model:
        print(f"Forced model from CLI: {args.model}")

    if args.preview_model_selection:
        preview_runtime_config = runtime_config
        if args.skip_probe:
            preview_runtime_config = _deep_merge_dict(
                runtime_config,
                {"model_probe": {"enabled": False}},
            )
            print("Model probe: disabled for preview")
        requested_model = args.model or str(
            preview_runtime_config.get("default_model", "gemini-2.5-flash")
        )
        print_model_selection_preview(requested_model, preview_runtime_config)
        return

    # Find temp directory
    temp_dir = args.temp_dir
    if not os.path.exists(temp_dir):
        print(f"Error: Specified temp directory not found: {temp_dir}")
        sys.exit(1)

    print(f"Using temp directory: {temp_dir}")

    # Load configuration
    config = load_pipeline_config(temp_dir)
    output_lang = args.output_lang or config["output_lang"]

    print(f"Target language: {output_lang}")

    if args.prompt:
        print(f"Custom prompt: {args.prompt}")

    # If retry failed, remove existing output files that might be incomplete
    if args.retry_failed:
        print("Retry mode: removing potentially incomplete translation files...")
        output_files = glob.glob(os.path.join(temp_dir, "output_page*.md"))
        for output_file in output_files:
            try:
                # Check if file is very small (likely failed)
                if os.path.getsize(output_file) < 50:
                    os.remove(output_file)
                    print(f"  Removed: {os.path.basename(output_file)}")
            except Exception as e:
                print(f"⚠️  Cleanup error: {e}", file=sys.stderr)

    # Translate markdown files
    translate_markdown_files(
        temp_dir,
        output_lang,
        args.prompt,
        forced_model=args.model,
        runtime_config=runtime_config,
        resume=not args.no_resume,
    )

    print("\n=== Step 3 Complete ===")
    print("Next step: Run 04_merge_md.py")


if __name__ == "__main__":
    main()
