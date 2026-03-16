#!/usr/bin/env python3
"""
Step 3: Translate markdown files using Gemini CLI
Translates each pageXXXX.md file to output_pageXXXX.md
"""

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
from ai.model_selector import ModelSelector

def load_config(temp_dir):
    """Load configuration from step 1"""
    config_file = os.path.join(temp_dir, 'config.txt')
    if not os.path.exists(config_file):
        print("Error: config.txt not found. Run 01_prepare_env.py first.")
        sys.exit(1)
    
    config = {}
    with open(config_file, 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                config[key] = value
    
    return config

def check_claude_cli():
    """Check if Claude CLI is available"""
    try:
        result = subprocess.run(['claude', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_info = result.stdout.strip().split('\n')[-1]
            print(f"Claude CLI available: {version_info}")
            return True
        else:
            print(f"Claude CLI check failed with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print("Error: Claude CLI version check timed out")
        return False
    except FileNotFoundError:
        print("Error: 'claude' command not found")
        print("Please ensure Claude CLI is installed and in your PATH")
        return False
    except Exception as e:
        print(f"Error checking Claude CLI: {e}")
        return False


def check_gemini_cli():
    """Check if Gemini CLI is available"""
    try:
        result = subprocess.run(
            ["gemini", "--version"], capture_output=True, text=True, timeout=10
        )
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


def load_runtime_config():
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

    if "prompt_templates" not in config:
        config["prompt_templates"] = {"default": "config/prompts/default_prompt.txt"}

    if "model_aliases" not in config:
        config["model_aliases"] = {
            "pro": "gemini-2.5-pro",
            "flash": "gemini-2.5-flash",
            "lite": "gemini-2.5-flash-lite",
        }

    return config

def get_language_name(lang_code):
    """Convert language code to full name"""
    lang_map = {
        'zh': 'Chinese',
        'en': 'English',
        'ja': 'Japanese',
        'ko': 'Korean',
        'fr': 'French',
        'de': 'German',
        'es': 'Spanish',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'th': 'Thai',
        'vi': 'Vietnamese'
    }
    return lang_map.get(lang_code.lower(), lang_code)

def _default_prompt_template_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    return script_dir / "config" / "prompts" / "default_prompt.txt"


def load_prompt_template(runtime_config: dict[str, Any] | None = None) -> str:
    """Load prompt template from config path, fallback to bundled default."""
    config = runtime_config or {}
    profile = config.get("prompt_profile", "default")
    templates = config.get("prompt_templates", {})

    candidate_path: Path | None = None
    if isinstance(templates, dict):
        raw_path = templates.get(profile)
        if isinstance(raw_path, str) and raw_path.strip():
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = Path(__file__).resolve().parent / candidate
            candidate_path = candidate

    if candidate_path and candidate_path.exists():
        return candidate_path.read_text(encoding="utf-8")

    default_path = _default_prompt_template_path()
    if default_path.exists():
        return default_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Prompt template not found. Tried: {candidate_path} and {default_path}"
    )


def create_translation_prompt(
    output_lang, custom_prompt=None, runtime_config: dict[str, Any] | None = None
):
    """Create translation prompt from external template with optional custom additions."""
    lang_name = get_language_name(output_lang)

    template = load_prompt_template(runtime_config)
    custom_block = ""
    if custom_prompt:
        custom_block = f"\n\nADDITIONAL INSTRUCTIONS:\n{custom_prompt}"

    prompt = template.replace("{TARGET_LANGUAGE}", lang_name).replace(
        "{CUSTOM_INSTRUCTIONS_BLOCK}", custom_block
    )
    return prompt


def resolve_model_name(model_name: str, runtime_config: dict[str, Any] | None = None) -> str:
    """Resolve user-facing aliases to concrete model names."""
    raw = (model_name or "").strip()
    if not raw:
        raise ValueError("model name must not be empty")

    aliases: dict[str, str] = {}
    if runtime_config:
        raw_aliases = runtime_config.get("model_aliases")
        if isinstance(raw_aliases, dict):
            aliases.update(
                {
                    str(k).strip().lower(): str(v).strip()
                    for k, v in raw_aliases.items()
                    if str(k).strip() and str(v).strip()
                }
            )

    if not aliases:
        aliases = {
            "pro": "gemini-2.5-pro",
            "flash": "gemini-2.5-flash",
            "lite": "gemini-2.5-flash-lite",
        }

    return aliases.get(raw.lower(), raw)

def translate_with_claude_cli(text, output_lang, custom_prompt=None, max_retries=3):
    """Translate text using Claude CLI with retry mechanism and real-time output"""
    
    # Create translation prompt
    prompt = create_translation_prompt(output_lang, custom_prompt)
    
    def run_claude_with_realtime_output(full_input, attempt_num):
        """Run Claude CLI and show real-time output"""
        print(f"    Starting Claude translation (attempt {attempt_num})...")
        
        try:
            # Start Claude process
            command = ['claude']
            
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1,
                universal_newlines=True
            )
            
            # Send input to Claude
            stdout, stderr = process.communicate(input=full_input, timeout=180)
            
            # Show real-time output
            if stdout:
                print("    Claude output:")
                # Split output into lines and print with indentation
                for line in stdout.split('\n'):
                    if line.strip():
                        print(f"      {line}")
                print("    Claude output complete.")
            
            return process.returncode, stdout, stderr
            
        except subprocess.TimeoutExpired:
            process.kill()
            return -1, "", "Translation timeout (3 minutes)"
        except Exception as e:
            return -1, "", str(e)
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"    Retry attempt {attempt + 1}/{max_retries}")
            time.sleep(1)  # Brief delay before retry
        
        try:
            # Prepare the full input text
            full_input = f"{prompt}\n\n{text}"
            
            # Run Claude with real-time output
            returncode, stdout, stderr = run_claude_with_realtime_output(full_input, attempt + 1)
            
            if returncode == 0:
                translated_text = stdout.strip()
                
                # Strictly extract content between START and END markers
                def extract_content_between_markers(text):
                    """Strictly extract content between START and END markers"""
                    start_marker = '<!-- START -->'
                    end_marker = '<!-- END -->'
                    
                    # Find the positions of markers
                    start_pos = text.find(start_marker)
                    end_pos = text.find(end_marker)
                    
                    if start_pos == -1:
                        # Try to find markers with variations
                        for variation in ['<!--START-->', '<!-- START-->', '<!--START -->', '<!-- START-->']:
                            start_pos = text.find(variation)
                            if start_pos != -1:
                                start_marker = variation
                                break
                    
                    if end_pos == -1:
                        # Try to find markers with variations
                        for variation in ['<!--END-->', '<!-- END-->', '<!--END -->', '<!-- END-->']:
                            end_pos = text.find(variation)
                            if end_pos != -1:
                                end_marker = variation
                                break
                    
                    if start_pos != -1 and end_pos != -1 and start_pos < end_pos:
                        # Extract content between markers
                        content_start = start_pos + len(start_marker)
                        extracted = text[content_start:end_pos].strip()
                        return extracted
                    
                    return None
                
                # Try to extract content
                extracted_content = extract_content_between_markers(translated_text)
                
                if extracted_content and len(extracted_content.strip()) > 0:
                    if attempt > 0:
                        print(f"    ✓ Translation successful on attempt {attempt + 1}")
                    return extracted_content
                else:
                    # Show detailed debug information
                    print(f"    Attempt {attempt + 1}: Failed to extract content between START/END markers")
                    print(f"    Raw output (first 300 chars): {translated_text[:300]}...")
                    
                    # Check if markers exist at all
                    has_start = False
                    has_end = False
                    
                    start_variations = ['<!-- START -->', '<!--START-->', '<!-- START-->', '<!--START -->']
                    end_variations = ['<!-- END -->', '<!--END-->', '<!-- END-->', '<!--END -->']
                    
                    for var in start_variations:
                        if var in translated_text:
                            has_start = True
                            print(f"    Found START marker: {var}")
                            break
                    
                    for var in end_variations:
                        if var in translated_text:
                            has_end = True
                            print(f"    Found END marker: {var}")
                            break
                    
                    if not has_start:
                        print(f"    No START marker found")
                    if not has_end:
                        print(f"    No END marker found")
                    
                    # Last resort: if both markers exist but extraction failed, try emergency extraction
                    if has_start and has_end:
                        print(f"    Attempting emergency extraction...")
                        lines = translated_text.split('\n')
                        start_line = -1
                        end_line = -1
                        
                        for i, line in enumerate(lines):
                            if any(marker in line for marker in start_variations):
                                start_line = i
                            if any(marker in line for marker in end_variations):
                                end_line = i
                                break
                        
                        if start_line != -1 and end_line != -1 and start_line < end_line:
                            emergency_content = '\n'.join(lines[start_line+1:end_line]).strip()
                            if emergency_content:
                                print(f"    Emergency extraction successful")
                                return emergency_content
                    
                    continue  # Retry
            else:
                error_msg = stderr.strip() if stderr else "No error message"
                print(f"    Attempt {attempt + 1}: Claude CLI error (code {returncode}): {error_msg}")
                continue  # Retry
                
        except FileNotFoundError:
            print(f"    Error: 'claude' command not found. Please ensure Claude CLI is installed and in PATH")
            return None  # Don't retry for this error
        except Exception as e:
            print(f"    Attempt {attempt + 1}: Error calling Claude CLI: {e}")
            continue  # Retry
    
    # All retries failed
    print(f"    ✗ Translation failed after {max_retries} attempts, skipping file")
    return None

def translate_with_gemini_cli(
    text, output_lang, model, custom_prompt=None, max_retries=3, runtime_config=None
):
    """Translate text using Gemini CLI via GeminiProvider."""
    prompt = create_translation_prompt(output_lang, custom_prompt, runtime_config)

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


def translate_markdown_files(
    temp_dir, output_lang, custom_prompt=None, forced_model=None, runtime_config=None
):
    """Translate all markdown files in temp directory"""
    print(f"Translating markdown files to {output_lang}...")
    if custom_prompt:
        print(f"Using custom prompt: {custom_prompt[:100]}...")

    config = runtime_config or {}
    selector = None
    thresholds = config.get("model_thresholds")
    if isinstance(thresholds, dict):
        try:
            selector = ModelSelector(config)
        except Exception as e:
            print(f"Warning: Invalid model thresholds in config, fallback to default model: {e}")
    
    # Find all pageXXXX.md files
    md_files = glob.glob(os.path.join(temp_dir, 'page*.md'))
    md_files.sort()
    
    if not md_files:
        print("Error: No markdown files found. Run 02_split_to_md.py first.")
        sys.exit(1)
    
    total_files = len(md_files)
    translated_count = 0
    skipped_count = 0
    failed_count = 0
    
    for i, md_file in enumerate(md_files, 1):
        filename = os.path.basename(md_file)
        output_filename = f"output_{filename}"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Skip if output file already exists
        if os.path.exists(output_path):
            print(f"  [{i}/{total_files}] Skipping {filename} (already translated)")
            skipped_count += 1
            continue
        
        print(f"  [{i}/{total_files}] Translating {filename}...")
        
        # Read input file
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"    Error reading {filename}: {e}")
            failed_count += 1
            continue
        
        # Skip if file is empty or very short
        if len(content.strip()) < 1:
            print(f"    Skipping {filename} (too short)")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            skipped_count += 1
            continue
        
        selected_model = forced_model
        if not selected_model:
            if selector is not None:
                selected_model = selector.select(len(content))
            else:
                selected_model = config.get("default_model", "gemini-2.5-flash")

        print(f"    Model: {selected_model}")
        translated_content = translate_with_gemini_cli(
            content,
            output_lang,
            selected_model,
            custom_prompt,
            runtime_config=runtime_config,
        )
        
        if translated_content:
            # Save translated content
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(translated_content)
                print(f"    ✓ Translated and saved to {output_filename}")
                translated_count += 1
            except Exception as e:
                print(f"    Error saving {output_filename}: {e}")
                failed_count += 1
        else:
            # Translation failed after all retries - skip file creation completely
            print(f"    ✗ Failed to translate {filename} after retries, skipping file creation")
            failed_count += 1
        
        # Add delay to avoid rate limits
        if i < total_files:
            time.sleep(0.5)  # Reduced delay for CLI
    
    print(f"\nTranslation complete:")
    print(f"  Translated: {translated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {total_files}")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Book Translation Tool - Step 3: Translate Markdown using Gemini CLI"
    )
    
    parser.add_argument(
        '-p', '--prompt',
        default=None,
        help="Additional custom prompt to add to the translation instructions"
    )
    
    parser.add_argument(
        '--temp-dir',
        required=True,
        help="Temp directory path (required)"
    )
    
    parser.add_argument(
        '--output-lang',
        default=None,
        help="Override output language from config"
    )
    
    parser.add_argument(
        '--retry-failed',
        action='store_true',
        help="Retry translating files that failed previously"
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Force model for all chunks. Supports aliases (pro|flash|lite) and full model names.",
    )
    
    return parser.parse_args()

def main():
    """Main function"""
    print("=== Book Translation Tool - Step 3: Translate Markdown (Gemini CLI) ===")
    
    # Parse arguments
    args = parse_arguments()
    
    # Check Gemini CLI availability
    if not check_gemini_cli():
        sys.exit(1)
    
    # Find temp directory
    temp_dir = args.temp_dir
    if not os.path.exists(temp_dir):
        print(f"Error: Specified temp directory not found: {temp_dir}")
        sys.exit(1)
    
    print(f"Using temp directory: {temp_dir}")
    
    # Load configuration
    config = load_config(temp_dir)
    output_lang = args.output_lang or config['output_lang']
    
    print(f"Target language: {output_lang}")
    runtime_config = load_runtime_config()
    if args.model:
        resolved_model = resolve_model_name(args.model, runtime_config)
        if resolved_model != args.model:
            print(f"Forced model alias resolved: {args.model} -> {resolved_model}")
        else:
            print(f"Forced model from CLI: {resolved_model}")
    else:
        resolved_model = None
    
    if args.prompt:
        print(f"Custom prompt: {args.prompt}")
    
    # If retry failed, remove existing output files that might be incomplete
    if args.retry_failed:
        print("Retry mode: removing potentially incomplete translation files...")
        output_files = glob.glob(os.path.join(temp_dir, 'output_page*.md'))
        for output_file in output_files:
            try:
                # Check if file is very small (likely failed)
                if os.path.getsize(output_file) < 50:
                    os.remove(output_file)
                    print(f"  Removed: {os.path.basename(output_file)}")
            except:
                pass
    
    # Translate markdown files
    translate_markdown_files(
        temp_dir,
        output_lang,
        args.prompt,
        forced_model=resolved_model,
        runtime_config=runtime_config,
    )
    
    print("\n=== Step 3 Complete ===")
    print("Next step: Run 04_merge_md.py")

if __name__ == "__main__":
    main()
