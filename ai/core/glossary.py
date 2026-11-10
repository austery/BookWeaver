"""Glossary domain primitives shared by extraction and injection paths."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2}
# SPEC-028 §3.5: a term without a tier is fixed. A glossary with no tier anywhere renders exactly
# as it did before tiers existed, because the block feeds every saved book's prompt hash.
TermTier = Literal["fixed", "preferred"]
_TIERS: tuple[TermTier, ...] = ("fixed", "preferred")
_FIXED_HEADING = "【关键术语约束】以下术语必须严格遵守标准译法："
_PREFERRED_HEADING = (
    "【建议术语】以下译法一般情况下采用；如果某句的语境需要，"
    "可以改用更贴切、更通顺的译法，但不得改变原意："
)
# A slash can mark alternatives (疏离 / 隔阂) or belong to one translation (客户端/服务器架构).
_SLASH = re.compile(r"\s*[/／]\s*")


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

        fixed = [term for term in terms if term.get("tier") != "preferred"]
        preferred = [term for term in terms if term.get("tier") == "preferred"]
        blocks: list[str] = []
        if fixed:
            blocks.append("\n".join([_FIXED_HEADING, *(_term_line(term) for term in fixed)]))
        if preferred:
            lines = [_term_line(term, with_alternatives=True) for term in preferred]
            blocks.append("\n".join([_PREFERRED_HEADING, *lines]))
        return "\n\n".join(blocks)


def _term_line(entry: dict[str, object], *, with_alternatives: bool = False) -> str:
    line = f"  • {entry.get('term', '')} → {entry.get('suggested_translation', '')}"
    if with_alternatives:
        alternatives = _alternatives(entry)
        if alternatives:
            line += f"（也可：{'、'.join(alternatives)}）"
    negative = str(entry.get("negative_constraint", "") or "")
    if negative:
        line += f"（{negative}）"
    return line


def _alternatives(entry: dict[str, object]) -> list[str]:
    listed = entry.get("alternatives")
    if not isinstance(listed, list):
        return []
    return [item.strip() for item in listed if isinstance(item, str) and item.strip()]


@dataclass(frozen=True)
class TermUsage:
    """How one glossary term was translated across the segments that contain it."""

    term: str
    translation: str
    segments: int
    option_counts: dict[str, int]
    missing: int
    tier: TermTier | None = None

    @property
    def consistent(self) -> bool:
        used = sum(1 for count in self.option_counts.values() if count)
        return self.missing == 0 and used <= 1


def terms_with_a_slash(data: dict[str, object]) -> list[str]:
    """Terms whose translation may offer a choice.

    Only a person or a judge can tell alternatives from one translation, and a wrong cut would
    constrain the whole book. So this names the terms and never changes them.
    """
    raw_terms = data.get("critical_terminology")
    if not isinstance(raw_terms, list):
        return []
    flagged: list[str] = []
    for entry in raw_terms:
        translation = entry.get("suggested_translation") if isinstance(entry, dict) else None
        if isinstance(translation, str) and _SLASH.search(translation):
            flagged.append(str(entry.get("term", "")))
    return flagged


def measure_term_usage(
    terms: Iterable[dict[str, object]], pairs: Iterable[tuple[str, str]]
) -> list[TermUsage]:
    """Count the translations used for each term across (source, translated) segment pairs.

    This is a signal, not a verdict: a plural source form is not matched, a sound rewording
    counts as missing, and a part of a compound translation can count as another option.
    """
    segments = list(pairs)
    usage: list[TermUsage] = []
    for entry in terms:
        term = str(entry.get("term", "")).strip()
        translation = str(entry.get("suggested_translation", "")).strip()
        if not term or not translation:
            continue
        words = r"\s+".join(re.escape(word) for word in term.split())
        pattern = re.compile(rf"(?<!\w){words}(?!\w)", re.IGNORECASE)
        matched = [target for source, target in segments if pattern.search(source)]
        tier = entry.get("tier")
        # A fixed term must use its own translation; its alternatives then count as missing.
        alternatives = [] if tier == "fixed" else _alternatives(entry)
        parts = [part for part in [*_SLASH.split(translation), *alternatives] if part]
        # The whole translation and the longest part first, so that a part found only inside
        # a longer one is not counted as a second translation.
        ordered = sorted({translation, *parts}, key=len, reverse=True)
        counts = dict.fromkeys(parts, 0)
        missing = 0
        for target in matched:
            remaining = target
            found = False
            for option in ordered:
                if option in remaining:
                    counts[option] = counts.get(option, 0) + 1
                    remaining = remaining.replace(option, "")
                    found = True
            missing += not found
        usage.append(
            TermUsage(
                term,
                translation,
                len(matched),
                counts,
                missing,
                cast(TermTier, tier) if tier in _TIERS else None,
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
        if "tier" in entry and entry["tier"] not in _TIERS:
            raise ValueError(
                f"{source} critical_terminology[{index}] has tier {entry['tier']!r}; "
                f"use one of {', '.join(_TIERS)}"
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
