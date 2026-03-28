"""Load extracted glossary JSON and format a prompt-injectable terminology block."""

from __future__ import annotations

import json
from pathlib import Path


class GlossaryInjector:
    """Loads an extracted glossary and formats it for prompt injection.

    Expected JSON schema:
        {
          "critical_terminology": [
            {
              "term": str,
              "suggested_translation": str,
              "negative_constraint": str | None,  # optional
              "reason": str | None,               # optional
              "priority": "critical" | "high" | "medium"
            }
          ]
        }
    """

    _PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

    def __init__(self, glossary_path: Path) -> None:
        if not glossary_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {glossary_path}")
        raw = glossary_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid glossary JSON at {glossary_path}: {exc}") from exc
        if "critical_terminology" not in data:
            raise ValueError(f"Glossary at {glossary_path} missing 'critical_terminology' key")
        self.terms: list[dict] = sorted(
            data["critical_terminology"],
            key=lambda t: self._PRIORITY_ORDER.get(t.get("priority", "medium"), 2),
        )

    def format_block(self, min_priority: str | None = None) -> str:
        """Return a prompt block string, or empty string if no terms.

        Args:
            min_priority: If set, only include terms at this priority or higher.
                          Values: "critical" (strictest), "high", "medium" (all).
                          Default None means include all terms.
        """
        terms = self.terms
        if min_priority is not None:
            cutoff = self._PRIORITY_ORDER.get(min_priority, 2)
            terms = [
                t
                for t in terms
                if self._PRIORITY_ORDER.get(t.get("priority", "medium"), 2) <= cutoff
            ]
        if not terms:
            return ""
        lines: list[str] = ["【关键术语约束】以下术语必须严格遵守标准译法："]
        for entry in terms:
            term = entry.get("term", "")
            translation = entry.get("suggested_translation", "")
            negative = entry.get("negative_constraint", "")
            line = f"  • {term} → {translation}"
            if negative:
                line += f"（{negative}）"
            lines.append(line)
        return "\n".join(lines)
