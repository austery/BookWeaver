#!/usr/bin/env python3
"""
Step 3: Translate markdown files using Gemini CLI
Translates each pageXXXX.md file to output_pageXXXX.md
"""

from __future__ import annotations

import os
import sys
import glob
import time
import argparse
import subprocess
import json
from pathlib import Path
from typing import Any

from ai.gemini_provider import GeminiProvider
from ai.model_probe import ModelProbe
from ai.model_selector import ModelSelector


def load_config(temp_dir: str) -> dict[str, Any]:
    """Load configuration from step 1"""
    config_file = os.path.join(temp_dir, "config.txt")
    if not os.path.exists(config_file):
        print("Error: config.txt not found. Run 01_prepare_env.py first.")
        sys.exit(1)

    config = {}
    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value

    return config


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


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        base_val = result.get(key)
        if isinstance(base_val, dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict(base_val, value)
        else:
            result[key] = value
    return result


def load_runtime_config() -> dict[str, Any]:
    """Load config from bundled example and user override."""
    script_dir = Path(__file__).resolve().parent
    bundled_config_path = script_dir / "config" / "config.json.example"
    user_config_path = Path.home() / ".config" / "translatebook" / "config.json"

    config: dict[str, Any] = {}

    if bundled_config_path.exists():
        with open(bundled_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    if user_config_path.exists():
        with open(user_config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
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


def get_language_name(lang_code: str) -> str:
    """Convert language code to full name"""
    lang_map = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
        "ar": "Arabic",
        "hi": "Hindi",
        "th": "Thai",
        "vi": "Vietnamese",
    }
    return lang_map.get(lang_code.lower(), lang_code)


def load_prompt_template(runtime_config: dict[str, Any] | None = None) -> str:
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


def resolve_model_name(requested_model: str, runtime_config: dict[str, Any] | None = None) -> str:
    """Resolve a model alias to the concrete model name."""
    if not isinstance(requested_model, str) or not requested_model.strip():
        raise ValueError("requested_model must be a non-empty string")

    config = runtime_config or {}
    aliases_raw = config.get("model_aliases")
    aliases: dict[str, str] = {}
    if isinstance(aliases_raw, dict):
        aliases = {
            key: value.strip()
            for key, value in aliases_raw.items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }

    resolved_model = requested_model.strip()
    visited: set[str] = set()
    while resolved_model in aliases:
        if resolved_model in visited:
            raise ValueError(f"Model alias cycle detected at '{resolved_model}'")
        visited.add(resolved_model)
        resolved_model = aliases[resolved_model]
    return resolved_model


def build_model_candidates(
    requested_model: str, runtime_config: dict[str, Any] | None = None
) -> list[str]:
    """Build requested->fallback ordered candidate model list."""
    config = runtime_config or {}
    candidates: list[str] = [resolve_model_name(requested_model, config)]

    if bool(config.get("enable_fallback", True)):
        fallback_chain = config.get("fallback_chain")
        if isinstance(fallback_chain, list):
            for raw_fallback in fallback_chain:
                if not isinstance(raw_fallback, str) or not raw_fallback.strip():
                    continue
                resolved_fallback = resolve_model_name(raw_fallback, config)
                if resolved_fallback not in candidates:
                    candidates.append(resolved_fallback)
    return candidates


def _create_model_probe(runtime_config: dict[str, Any]) -> ModelProbe | None:
    probe_config_raw = runtime_config.get("model_probe")
    if not isinstance(probe_config_raw, dict):
        return None
    if not bool(probe_config_raw.get("enabled", True)):
        return None

    ttl_raw = probe_config_raw.get("cache_ttl_seconds", 3600)
    ttl_seconds = 3600
    if isinstance(ttl_raw, (int, float)):
        ttl_seconds = int(ttl_raw)

    cache_path_raw = probe_config_raw.get(
        "cache_path", "~/.cache/bookweaver/model_probe_cache.json"
    )
    cache_path = Path(str(cache_path_raw)).expanduser()
    return ModelProbe(cache_path=cache_path, ttl_seconds=max(ttl_seconds, 0))


def select_model_with_fallback(
    requested_model: str,
    runtime_config: dict[str, Any] | None = None,
    probe: ModelProbe | None = None,
) -> str:
    """Select first available model from requested->fallback chain."""
    config = runtime_config or {}
    candidates = build_model_candidates(requested_model, config)
    if not candidates:
        raise RuntimeError("No model candidates available")

    probe_config_raw = config.get("model_probe")
    probe_enabled = True
    if isinstance(probe_config_raw, dict):
        probe_enabled = bool(probe_config_raw.get("enabled", True))

    if not probe_enabled:
        return candidates[0]

    effective_probe = probe if probe is not None else _create_model_probe(config)
    if effective_probe is None:
        return candidates[0]

    availability = effective_probe.probe(candidates)
    for candidate in candidates:
        if availability.get(candidate, False):
            return candidate

    errors_raw = getattr(effective_probe, "last_probe_errors", {})
    errors: dict[str, str] = errors_raw if isinstance(errors_raw, dict) else {}
    attempted = ", ".join(candidates)
    error_details = "; ".join(
        f"{model}: {errors[model]}" for model in candidates if model in errors
    )
    if not error_details:
        error_details = "No stderr details from probe"
    raise RuntimeError(
        f"No available Gemini model after probe. Attempted: {attempted}. Errors: {error_details}"
    )


def print_model_selection_preview(requested_model: str, runtime_config: dict[str, Any]) -> None:
    """Print model resolution details without translating files."""
    resolved_model = resolve_model_name(requested_model, runtime_config)
    candidates = build_model_candidates(requested_model, runtime_config)
    print("Model selection preview:")
    print(f"  Requested: {requested_model}")
    if resolved_model != requested_model:
        print(f"  Alias resolved: {requested_model} -> {resolved_model}")
    print(f"  Candidates: {' -> '.join(candidates)}")
    selected_model = select_model_with_fallback(requested_model, runtime_config)
    if selected_model != resolved_model:
        print(f"  Fallback selected: {resolved_model} -> {selected_model}")
    print(f"  Final selected model: {selected_model}")


def create_translation_prompt(
    output_lang: str, custom_prompt: str | None = None, runtime_config: dict[str, Any] | None = None
) -> str:
    """Create translation prompt with optional custom additions."""
    lang_name = get_language_name(output_lang)
    template = load_prompt_template(runtime_config)
    has_custom_placeholder = "{CUSTOM_INSTRUCTIONS_BLOCK}" in template
    custom_block = f"ADDITIONAL INSTRUCTIONS:\n{custom_prompt}" if custom_prompt else ""

    prompt = template.replace("{TARGET_LANGUAGE}", lang_name)
    if has_custom_placeholder:
        prompt = prompt.replace("{CUSTOM_INSTRUCTIONS_BLOCK}", custom_block)
    elif custom_block:
        prompt = f"{prompt.rstrip()}\n\n{custom_block}"

    prompt = prompt.rstrip()
    return f"{prompt}\n\n markdown文件正文:"


def translate_with_gemini_cli(
    text: str,
    output_lang: str,
    model: str,
    custom_prompt: str | None = None,
    max_retries: int = 3,
    runtime_config: dict[str, Any] | None = None,
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
    record: dict[str, Any] = {
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
    runtime_config: dict[str, Any] | None = None,
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
            selected_model = select_model_with_fallback(
                requested_model,
                config,
                probe=probe,
            )
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

        resolved_requested_model = resolve_model_name(requested_model, config)
        if resolved_requested_model != requested_model:
            print(f"    Model alias resolved: {requested_model} -> {resolved_requested_model}")
        if selected_model != resolved_requested_model:
            print(f"    Model fallback selected: {resolved_requested_model} -> {selected_model}")
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


def parse_arguments():
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
    config = load_config(temp_dir)
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
