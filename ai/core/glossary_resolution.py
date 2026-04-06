"""Glossary request policy resolution.

Determines the glossary request mode based on CLI arguments.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlossaryRequest:
    """Resolved glossary request policy."""

    mode: str  # "manual", "deep-scan", "auto", or "none"
    glossary_path: str | None
    explicit: bool  # True if user explicitly requested a mode


def resolve_glossary_request(
    *,
    glossary: str | None = None,
    glossary_mode: str | None = None,
    extract_glossary: bool = False,
) -> GlossaryRequest:
    """Resolve glossary request precedence.

    Precedence:
    1. --glossary <path> → manual mode
    2. --glossary-mode deep-scan → deep-scan mode
    3. --glossary-mode auto or --extract-glossary → auto mode
    4. otherwise → none mode

    Args:
        glossary: Path to glossary file (--glossary)
        glossary_mode: Explicit mode (--glossary-mode)
        extract_glossary: Legacy flag (--extract-glossary)

    Returns:
        GlossaryRequest with resolved mode and metadata
    """
    # Precedence 1: --glossary <path> wins
    if glossary is not None:
        return GlossaryRequest(mode="manual", glossary_path=glossary, explicit=True)

    # Precedence 2: --glossary-mode deep-scan
    if glossary_mode == "deep-scan":
        return GlossaryRequest(mode="deep-scan", glossary_path=None, explicit=True)

    # Precedence 3: --glossary-mode auto or --extract-glossary
    if glossary_mode == "auto" or extract_glossary:
        explicit = glossary_mode == "auto"  # auto is explicit, extract_glossary is not
        return GlossaryRequest(mode="auto", glossary_path=None, explicit=explicit)

    # Precedence 4: no glossary requested
    return GlossaryRequest(mode="none", glossary_path=None, explicit=False)
