"""Batch delimiter protocol for LLM segment translation.

Encapsulates the ``%%`` separator convention used to batch multiple
text segments into a single LLM call and parse them back out.

This module is a **transport concern** — private to the adapter
package.  Core domain code must never import from here.
"""

from __future__ import annotations

import re

from ai.ports.provider import TranslationError

_SEGMENT_DELIMITER = "%%"
_BATCH_SEPARATOR = f"\n\n{_SEGMENT_DELIMITER}\n\n"
_BATCH_SPLIT_PATTERN = re.compile(rf"\n\s*{re.escape(_SEGMENT_DELIMITER)}\s*\n")

SEPARATOR_OVERHEAD: int = len(_BATCH_SEPARATOR)  # 6 chars

_BATCH_PROMPT_ADDENDUM = (
    "\n\nIMPORTANT: The input contains multiple text sections separated"
    " by %%. Translate each section independently and preserve the %%"
    " separators in your output. Output exactly the same number of"
    " sections as the input."
)


def join_segments(segments: list[str]) -> str:
    """Join segments with the ``%%`` batch separator.

    - Empty list → ``""``
    - Single segment → returned as-is
    - Multiple → joined with ``\\n\\n%%\\n\\n``
    """
    if not segments:
        return ""
    if len(segments) == 1:
        return segments[0]
    return _BATCH_SEPARATOR.join(segments)


def split_response(output: str, expected_count: int) -> list[str]:
    """Split a batch translation response back into segments.

    Uses two parsing strategies:
    1. Exact ``\\n\\n%%\\n\\n`` split
    2. Flexible whitespace pattern around ``%%``

    Raises:
        TranslationError: If segment count does not match *expected_count*.
    """
    if expected_count <= 0:
        return []

    normalized = output.strip()
    if expected_count == 1:
        if not normalized:
            raise TranslationError("provider returned empty translation")
        return [normalized]

    # Strategy 1: exact separator
    parts = [p.strip() for p in normalized.split(_BATCH_SEPARATOR)]
    parts = [p for p in parts if p]
    if len(parts) == expected_count:
        return parts

    # Strategy 2: flexible whitespace around %%
    parts = [p.strip() for p in _BATCH_SPLIT_PATTERN.split(normalized)]
    parts = [p for p in parts if p]
    if len(parts) == expected_count:
        return parts

    raise TranslationError(
        f"batch segment count mismatch: expected {expected_count}, got {len(parts)}"
    )


def augment_prompt_for_batch(
    system_prompt: str,
    segment_count: int,
) -> str:
    """Add ``%%`` handling instructions when batching multiple segments."""
    if segment_count <= 1:
        return system_prompt
    return system_prompt + _BATCH_PROMPT_ADDENDUM
