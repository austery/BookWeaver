"""Batch protocol helpers for LLM segment translation.

Supports two transport protocols:

- ``delimiter``: legacy ``%%`` separator convention
- ``segment_tags``: EPUB-focused tagged framing

This module is a **transport concern** — private to the adapter
package. Core domain code must never import from here.
"""

from __future__ import annotations

import re

from ai.ports.provider import TranslationError

_SEGMENT_DELIMITER = "%%"
_BATCH_SEPARATOR = f"\n\n{_SEGMENT_DELIMITER}\n\n"
_BATCH_SPLIT_PATTERN = re.compile(rf"\n\s*{re.escape(_SEGMENT_DELIMITER)}\s*\n")
_TAGGED_SEGMENT_PATTERN = re.compile(
    r"<segment\s+id\s*=\s*['\"](?P<id>\d+)['\"]\s*>(?P<body>.*?)</segment>",
    re.IGNORECASE | re.DOTALL,
)
_FENCED_WRAPPER_PATTERN = re.compile(
    r"^\s*```[a-zA-Z0-9_-]*\s*\n(?P<body>.*)\n```\s*$",
    re.DOTALL,
)

PROTOCOL_DELIMITER = "delimiter"
PROTOCOL_SEGMENT_TAGS = "segment_tags"

SEPARATOR_OVERHEAD: int = len(_BATCH_SEPARATOR)  # 6 chars

_BATCH_PROMPT_ADDENDUM = (
    "\n\nIMPORTANT: The input contains multiple text sections separated"
    " by %%. Translate each section independently and preserve the %%"
    " separators in your output. Output exactly the same number of"
    " sections as the input."
)
_TAGGED_PROMPT_ADDENDUM = (
    "\n\n[STRICT OUTPUT CONTRACT]\n"
    "Return exactly one XML block per section using this structure:\n"
    '<segment id="1">...</segment>\n'
    '<segment id="2">...</segment>\n'
    "...\n"
    "Rules:\n"
    "1) Preserve every segment id from 1..N exactly once.\n"
    "2) Do NOT merge, split, reorder, add, or drop segments.\n"
    "3) Output only <segment> blocks (no prose, no markdown fences).\n"
    "4) Keep empty sections as empty content inside their original tags.\n"
    "If any id is missing or duplicated, the task is considered failed."
)


def _validate_protocol(protocol: str) -> str:
    if protocol in (PROTOCOL_DELIMITER, PROTOCOL_SEGMENT_TAGS):
        return protocol
    msg = f"unknown batch protocol: {protocol}"
    raise ValueError(msg)


def _strip_fenced_wrapper(text: str) -> str:
    match = _FENCED_WRAPPER_PATTERN.match(text)
    if match is None:
        return text
    return match.group("body").strip()


def join_segments(
    segments: list[str],
    *,
    protocol: str = PROTOCOL_DELIMITER,
) -> str:
    """Join segments with the selected batch protocol.

    - Empty list → ``""``
    - Single segment → returned as-is
    - Multiple + delimiter → joined with ``\\n\\n%%\\n\\n``
    - Multiple + segment_tags → wrapped in ``<segment id="n">...</segment>``
    """
    mode = _validate_protocol(protocol)
    if not segments:
        return ""
    if len(segments) == 1:
        return segments[0]
    if mode == PROTOCOL_DELIMITER:
        return _BATCH_SEPARATOR.join(segments)
    return "\n\n".join(
        f'<segment id="{idx}">{segment}</segment>' for idx, segment in enumerate(segments, start=1)
    )


def split_response(
    output: str,
    expected_count: int,
    *,
    protocol: str = PROTOCOL_DELIMITER,
) -> list[str]:
    """Split a batch translation response back into segments.

    Uses two parsing strategies:
    1. ``delimiter``: exact/flexible ``%%`` split
    2. ``segment_tags``: regex capture of ``<segment id="n">...</segment>``

    Raises:
        TranslationError: If segment count does not match *expected_count*.
    """
    mode = _validate_protocol(protocol)
    if expected_count <= 0:
        return []

    normalized = output.strip()
    if expected_count == 1:
        if not normalized:
            raise TranslationError("provider returned empty translation")
        return [normalized]

    if mode == PROTOCOL_SEGMENT_TAGS:
        parsed = _strip_fenced_wrapper(normalized)
        matches = list(_TAGGED_SEGMENT_PATTERN.finditer(parsed))
        if not matches:
            raise TranslationError("batch segment parse failure: no <segment> tags found")

        outside = _TAGGED_SEGMENT_PATTERN.sub("", parsed).strip()
        if outside:
            raise TranslationError("batch segment parse failure: unexpected content outside tags")

        parsed_items: list[tuple[int, str]] = [
            (int(match.group("id")), match.group("body").strip()) for match in matches
        ]
        if len(parsed_items) != expected_count:
            raise TranslationError(
                f"batch segment count mismatch: expected {expected_count}, got {len(parsed_items)}"
            )

        ids = [item[0] for item in parsed_items]
        unique_ids = set(ids)
        if len(unique_ids) != len(ids):
            raise TranslationError("batch segment id mismatch: duplicate ids in response")

        expected_ids = set(range(1, expected_count + 1))
        if unique_ids != expected_ids:
            missing = sorted(expected_ids - unique_ids)
            extra = sorted(unique_ids - expected_ids)
            raise TranslationError(f"batch segment id mismatch: missing={missing} extra={extra}")

        body_by_id = {idx: body for idx, body in parsed_items}
        return [body_by_id[idx] for idx in range(1, expected_count + 1)]

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
    *,
    protocol: str = PROTOCOL_DELIMITER,
) -> str:
    """Add protocol-specific handling instructions for multi-segment batches."""
    mode = _validate_protocol(protocol)
    if segment_count <= 1:
        return system_prompt
    if mode == PROTOCOL_DELIMITER:
        return system_prompt + _BATCH_PROMPT_ADDENDUM
    return system_prompt + _TAGGED_PROMPT_ADDENDUM
