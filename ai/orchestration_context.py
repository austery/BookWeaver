from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


_DEFAULT_AUDIENCE = "General readers interested in practical philosophy."
_DEFAULT_STYLE = "Accurate, concise, and natural modern Chinese prose."


@dataclass(frozen=True, slots=True)
class OrchestrationContext:
    audience: str
    style: str
    glossary: dict[str, str]


def _normalize_non_empty_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text


def _normalize_glossary(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = _normalize_non_empty_text(key)
        normalized_value = _normalize_non_empty_text(value)
        if normalized_key is None or normalized_value is None:
            continue
        normalized[normalized_key] = normalized_value
    return normalized


def _is_zh_output(output_lang: str) -> bool:
    normalized_lang = output_lang.strip().lower().replace("_", "-")
    if not normalized_lang:
        return False
    primary_lang = normalized_lang.split("-", 1)[0]
    return primary_lang == "zh"


def _load_builtin_glossary(output_lang: str, script_dir: Path) -> dict[str, str]:
    if not _is_zh_output(output_lang):
        return {}

    glossary_path = script_dir / "config" / "glossaries" / "en_zh_glossary.json"
    if not glossary_path.exists():
        return {}

    try:
        raw_payload = json.loads(glossary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return _normalize_glossary(raw_payload)


def _extract_orchestrated_config(runtime_config: dict[str, Any]) -> dict[str, Any]:
    orchestrated = runtime_config.get("orchestrated")
    if isinstance(orchestrated, dict):
        return orchestrated
    return {}


def load_orchestration_context(
    runtime_config: dict[str, Any],
    output_lang: str,
    script_dir: Path | None = None,
) -> OrchestrationContext:
    base_dir = script_dir or Path(__file__).resolve().parent.parent

    orchestrated_config = _extract_orchestrated_config(runtime_config)

    audience = _normalize_non_empty_text(orchestrated_config.get("audience")) or _DEFAULT_AUDIENCE
    style = _normalize_non_empty_text(orchestrated_config.get("style")) or _DEFAULT_STYLE

    merged_glossary: dict[str, str] = {}

    for source in (
        _load_builtin_glossary(output_lang=output_lang, script_dir=base_dir),
        _normalize_glossary(orchestrated_config.get("glossary")),
    ):
        for key, value in source.items():
            merged_glossary[key] = value

    return OrchestrationContext(
        audience=audience,
        style=style,
        glossary=merged_glossary,
    )
