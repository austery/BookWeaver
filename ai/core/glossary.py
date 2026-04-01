"""Glossary domain primitives shared by extraction and injection paths."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2}


@dataclass(frozen=True)
class GlossaryManager:
    """Validated glossary model with formatting behavior."""

    terms: list[dict[str, object]]

    @classmethod
    def from_json_file(cls, glossary_path: Path) -> "GlossaryManager":
        data = _load_glossary_json_file(glossary_path)
        return cls.from_dict(data, source=str(glossary_path))

    @classmethod
    def from_dict(cls, data: dict[str, object], *, source: str = "glossary") -> "GlossaryManager":
        terms = _validate_glossary_payload(data, source=source)
        sorted_terms = sorted(terms, key=lambda t: _priority_rank(t.get("priority")))
        return cls(terms=sorted_terms)

    def format_block(self, min_priority: str | None = None) -> str:
        terms = self.terms
        if min_priority is not None:
            cutoff = _priority_rank(min_priority)
            terms = [term for term in terms if _priority_rank(term.get("priority")) <= cutoff]
        if not terms:
            return ""

        lines = ["【关键术语约束】以下术语必须严格遵守标准译法："]
        for entry in terms:
            term = str(entry.get("term", ""))
            translation = str(entry.get("suggested_translation", ""))
            negative = str(entry.get("negative_constraint", "") or "")
            line = f"  • {term} → {translation}"
            if negative:
                line += f"（{negative}）"
            lines.append(line)
        return "\n".join(lines)


def validate_model_output(raw_output: str) -> dict[str, object]:
    """Validate model extraction output as glossary JSON payload."""
    cleaned = _strip_markdown_json_fence(raw_output)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Model output is not valid JSON: {exc}\nRaw output:\n{raw_output[:200]}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Model output must be a JSON object")
    if "critical_terminology" not in data:
        raise ValueError(
            f"model output missing 'critical_terminology' key. Got keys: {list(data.keys())}"
        )
    return data


def _validate_glossary_payload(data: dict[str, object], *, source: str) -> list[dict[str, object]]:
    if "critical_terminology" not in data:
        raise ValueError(
            f"{source} missing 'critical_terminology' key. Got keys: {list(data.keys())}"
        )

    raw_terms = data["critical_terminology"]
    if not isinstance(raw_terms, list):
        raise ValueError(f"{source} 'critical_terminology' must be a list")

    terms: list[dict[str, object]] = []
    for index, entry in enumerate(raw_terms):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{source} critical_terminology[{index}] must be an object, got {type(entry).__name__}"
            )
        terms.append(entry)
    return terms


def _priority_rank(value: object) -> int:
    if isinstance(value, str):
        return _PRIORITY_ORDER.get(value, 2)
    return 2


def _load_glossary_json_file(glossary_path: Path) -> dict[str, object]:
    if not glossary_path.exists():
        raise FileNotFoundError(f"Glossary file not found: {glossary_path}")

    raw = glossary_path.read_text(encoding="utf-8")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid glossary JSON at {glossary_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid glossary JSON at {glossary_path}: root must be an object")

    return loaded


def _strip_markdown_json_fence(raw_output: str) -> str:
    cleaned = raw_output.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()
