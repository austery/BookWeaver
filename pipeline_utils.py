"""
Pipeline infrastructure utilities shared by pipeline scripts.

Placed at root level (infrastructure layer) rather than inside ai/ (domain layer)
to respect Clean Architecture separation. This module will be superseded by
SPEC-007 unified YAML configuration when that work is implemented.
"""

from __future__ import annotations

import os


def load_pipeline_config(temp_dir: str) -> dict[str, str]:
    """Load pipeline config.txt written by 01_convert_to_htmlz.py.

    Args:
        temp_dir: Path to the temp directory containing config.txt.

    Returns:
        Dict of key=value pairs parsed from config.txt.

    Raises:
        FileNotFoundError: If config.txt not found. Message includes actionable hint.
        UnicodeDecodeError: If file contains non-UTF-8 bytes.
    """
    config_path = os.path.join(temp_dir, "config.txt")
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"config.txt not found in '{temp_dir}'. Run 01_convert_to_htmlz.py first."
        )
    config: dict[str, str] = {}
    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value
    return config


def get_language_name(code: str) -> str:
    """Convert ISO language code to full English name.

    Returns the code as-is if unrecognized. Case-insensitive lookup.

    Args:
        code: ISO 639-1 language code (e.g. "zh", "en").

    Returns:
        Full language name (e.g. "Chinese") or the original code if unknown.
    """
    _LANG_MAP: dict[str, str] = {
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
    return _LANG_MAP.get(code.lower(), code)
