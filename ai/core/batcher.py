"""Text batching — pure domain logic for grouping segments by size.

This module knows nothing about delimiters, prompts, or transport.
It groups text items by character count and an optional segment-count limit.
"""

from __future__ import annotations

from collections.abc import Sequence


class TextBatcher:
    """Groups text segments using character and optional segment-count limits.

    The algorithm is greedy: segments are packed into the current batch
    until adding the next segment would exceed either configured limit. A
    single oversized segment is placed alone in its own batch (never
    split at this level — splitting is a transport-level retry concern).

    ``separator_overhead`` accounts for per-join characters the adapter
    will insert between segments (e.g. ``len("\\n\\n%%\\n\\n") == 6``).
    The batcher does *not* know what the separator is — only its size.
    """

    def __init__(
        self,
        max_batch_chars: int,
        separator_overhead: int = 0,
        *,
        max_batch_segments: int | None = None,
    ) -> None:
        if max_batch_chars <= 0:
            raise ValueError(f"max_batch_chars must be > 0, got {max_batch_chars}")
        if separator_overhead < 0:
            raise ValueError(f"separator_overhead must be >= 0, got {separator_overhead}")
        if max_batch_segments is not None and (
            type(max_batch_segments) is not int or max_batch_segments <= 0
        ):
            raise ValueError("max_batch_segments must be a positive integer")
        self._max_segments = max_batch_segments
        self._max = max_batch_chars
        self._sep = separator_overhead

    @property
    def max_batch_chars(self) -> int:
        """Maximum total characters per batch (including separator overhead)."""
        return self._max

    @property
    def separator_overhead(self) -> int:
        """Per-separator character count added between segments."""
        return self._sep

    def plan_batches(self, segments: Sequence[str]) -> list[list[str]]:
        """Group *segments* into batches respecting both configured limits.

        Args:
            segments: Ordered text segments to batch.

        Returns:
            List of batches, each a non-empty list of segments.
            Segment order is preserved across batches.
        """
        if not segments:
            return []

        batches: list[list[str]] = []
        current: list[str] = []
        current_chars = 0

        for segment in segments:
            seg_len = len(segment)
            sep_len = self._sep if current else 0
            projected = current_chars + sep_len + seg_len

            if current and (
                projected > self._max
                or (self._max_segments is not None and len(current) >= self._max_segments)
            ):
                batches.append(current)
                current = [segment]
                current_chars = seg_len
                continue

            current.append(segment)
            current_chars = projected

        if current:
            batches.append(current)

        return batches
