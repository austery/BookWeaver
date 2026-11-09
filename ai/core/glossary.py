"""Glossary domain primitives shared by extraction and injection paths."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2}
# Spaces or a full-width slash mark alternatives. A plain slash can belong to one translation (输入/输出).
_OPTION_SEPARATOR = re.compile(r"\s+/\s+|\s*／\s*")


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


@dataclass(frozen=True)
class TermUsage:
    """How one glossary term was translated across the segments that contain it."""

    term: str
    translation: str
    segments: int
    option_counts: dict[str, int]
    missing: int

    @property
    def consistent(self) -> bool:
        used = sum(1 for count in self.option_counts.values() if count)
        return self.missing == 0 and used <= 1


def translation_options(translation: str) -> list[str]:
    """The alternatives a suggested translation offers; one item when it offers no choice."""
    return [option.strip() for option in _OPTION_SEPARATOR.split(translation) if option.strip()]


def keep_first_translation(data: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    """Leave one translation per term, so a prompt cannot offer a choice that varies by batch.

    Returns the glossary and the terms changed. Only a newly extracted glossary goes through
    this: a saved glossary feeds the prompt hash, so changing it would break resume.
    """
    raw_terms = data.get("critical_terminology")
    if not isinstance(raw_terms, list):
        return data, []
    changed: list[str] = []
    terms: list[object] = []
    for entry in raw_terms:
        translation = entry.get("suggested_translation") if isinstance(entry, dict) else None
        options = translation_options(translation) if isinstance(translation, str) else []
        if len(options) > 1:
            changed.append(str(entry.get("term", "")))
            entry = {**entry, "suggested_translation": options[0]}
        terms.append(entry)
    return {**data, "critical_terminology": terms}, changed


def measure_term_usage(
    terms: Iterable[dict[str, object]], pairs: Iterable[tuple[str, str]]
) -> list[TermUsage]:
    """Count the translations used for each term across (source, translated) segment pairs.

    This is a signal, not a verdict: a plural source form is not matched, and a sound
    rewording counts as missing.
    """
    segments = list(pairs)
    usage: list[TermUsage] = []
    for entry in terms:
        term = str(entry.get("term", "")).strip()
        translation = str(entry.get("suggested_translation", "")).strip()
        if not term:
            continue
        words = r"\s+".join(re.escape(word) for word in term.split())
        pattern = re.compile(rf"(?<!\w){words}(?!\w)", re.IGNORECASE)
        matched = [target for source, target in segments if pattern.search(source)]
        options = translation_options(translation)
        usage.append(
            TermUsage(
                term,
                translation,
                len(matched),
                {option: sum(option in target for target in matched) for option in options},
                sum(not any(option in target for option in options) for target in matched),
            )
        )
    return usage


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
