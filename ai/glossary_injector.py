"""Load extracted glossary JSON and format a prompt-injectable terminology block."""

from __future__ import annotations

from pathlib import Path

from ai.core.glossary import GlossaryManager


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

    def __init__(self, glossary_path: Path) -> None:
        self._manager = GlossaryManager.from_json_file(glossary_path)
        self.terms: list[dict[str, object]] = list(self._manager.terms)

    def format_block(self, min_priority: str | None = None) -> str:
        """Return a prompt block string, or empty string if no terms.

        Args:
            min_priority: If set, only include terms at this priority or higher.
                          Values: "critical" (strictest), "high", "medium" (all).
                          Default None means include all terms.
        """
        return self._manager.format_block(min_priority=min_priority)
