"""Unit tests for ai.core.batcher.TextBatcher.

Tests the pure domain logic of size-based segment grouping.
No transport concerns (delimiters, API calls) involved.
"""

from __future__ import annotations

import pytest

from ai.core.batcher import TextBatcher


# ── Construction ──────────────────────────────────────────────


class TestTextBatcherConstruction:
    def test_valid_construction(self) -> None:
        b = TextBatcher(max_batch_chars=100, separator_overhead=6)
        assert b.max_batch_chars == 100
        assert b.separator_overhead == 6

    def test_default_separator_overhead_is_zero(self) -> None:
        b = TextBatcher(max_batch_chars=50)
        assert b.separator_overhead == 0

    def test_rejects_zero_max(self) -> None:
        with pytest.raises(ValueError, match="max_batch_chars must be > 0"):
            TextBatcher(max_batch_chars=0)

    def test_rejects_negative_max(self) -> None:
        with pytest.raises(ValueError, match="max_batch_chars must be > 0"):
            TextBatcher(max_batch_chars=-1)

    def test_rejects_negative_separator(self) -> None:
        with pytest.raises(ValueError, match="separator_overhead must be >= 0"):
            TextBatcher(max_batch_chars=100, separator_overhead=-1)


# ── Empty / trivial inputs ───────────────────────────────────


class TestPlanBatchesEdgeCases:
    def test_empty_list_returns_empty(self) -> None:
        b = TextBatcher(max_batch_chars=100)
        assert b.plan_batches([]) == []

    def test_single_segment_within_limit(self) -> None:
        b = TextBatcher(max_batch_chars=100)
        assert b.plan_batches(["hello"]) == [["hello"]]

    def test_single_segment_at_exact_limit(self) -> None:
        b = TextBatcher(max_batch_chars=5)
        assert b.plan_batches(["hello"]) == [["hello"]]

    def test_single_oversized_segment_placed_alone(self) -> None:
        """A segment larger than max_batch_chars is never split."""
        b = TextBatcher(max_batch_chars=3)
        assert b.plan_batches(["toolong"]) == [["toolong"]]


# ── Grouping without separator ───────────────────────────────


class TestPlanBatchesNoSeparator:
    def test_two_segments_fit_one_batch(self) -> None:
        b = TextBatcher(max_batch_chars=10)
        assert b.plan_batches(["abc", "def"]) == [["abc", "def"]]

    def test_two_segments_exceed_limit_split(self) -> None:
        b = TextBatcher(max_batch_chars=5)
        assert b.plan_batches(["abc", "def"]) == [["abc"], ["def"]]

    def test_multiple_segments_greedy_packing(self) -> None:
        b = TextBatcher(max_batch_chars=10)
        # 3 + 3 = 6 ≤ 10 → same batch; 6 + 5 = 11 > 10 → new batch
        result = b.plan_batches(["aaa", "bbb", "ccccc"])
        assert result == [["aaa", "bbb"], ["ccccc"]]

    def test_order_preserved_across_batches(self) -> None:
        b = TextBatcher(max_batch_chars=4)
        segments = ["aa", "bb", "cc", "dd"]
        result = b.plan_batches(segments)
        flat = [s for batch in result for s in batch]
        assert flat == segments

    def test_exact_boundary_fits(self) -> None:
        """Two segments summing to exactly max_batch_chars → one batch."""
        b = TextBatcher(max_batch_chars=6)
        assert b.plan_batches(["abc", "def"]) == [["abc", "def"]]


# ── Grouping with separator overhead ─────────────────────────


class TestPlanBatchesWithSeparator:
    def test_separator_causes_split(self) -> None:
        # "abc" (3) + sep(6) + "def" (3) = 12 > 10 → split
        b = TextBatcher(max_batch_chars=10, separator_overhead=6)
        assert b.plan_batches(["abc", "def"]) == [["abc"], ["def"]]

    def test_separator_fits_when_larger_limit(self) -> None:
        # "abc" (3) + sep(6) + "def" (3) = 12 ≤ 12 → one batch
        b = TextBatcher(max_batch_chars=12, separator_overhead=6)
        assert b.plan_batches(["abc", "def"]) == [["abc", "def"]]

    def test_separator_not_counted_for_first_segment(self) -> None:
        # First segment: 3 chars (no separator).
        # Second: 3 + 2 (sep) = 5, total 8 ≤ 8 → fits
        b = TextBatcher(max_batch_chars=8, separator_overhead=2)
        assert b.plan_batches(["abc", "def"]) == [["abc", "def"]]

    def test_multiple_batches_with_separator(self) -> None:
        # sep=6, max=15
        # Batch 1: "aaaa"(4) + sep(6) + "bbbb"(4) = 14 ≤ 15 ✓
        # Adding "cccc": 14 + 6 + 4 = 24 > 15 → new batch
        # Batch 2: "cccc"(4) + sep(6) + "dddd"(4) = 14 ≤ 15 ✓
        b = TextBatcher(max_batch_chars=15, separator_overhead=6)
        result = b.plan_batches(["aaaa", "bbbb", "cccc", "dddd"])
        assert result == [["aaaa", "bbbb"], ["cccc", "dddd"]]

    def test_parity_with_legacy_separator_size(self) -> None:
        """Match the legacy _BATCH_SEPARATOR = '\\n\\n%%\\n\\n' (6 chars)."""
        b = TextBatcher(max_batch_chars=60_000, separator_overhead=6)
        # Small segments: all fit in one batch
        segs = [f"segment-{i}" * 10 for i in range(100)]
        result = b.plan_batches(segs)
        total_chars = sum(len(s) for s in segs) + 6 * (len(segs) - 1)
        if total_chars <= 60_000:
            assert len(result) == 1
        else:
            assert len(result) > 1


# ── Stress / realistic scenarios ─────────────────────────────


class TestPlanBatchesRealistic:
    def test_many_small_segments_few_batches(self) -> None:
        b = TextBatcher(max_batch_chars=1000, separator_overhead=6)
        segments = ["x" * 50 for _ in range(100)]
        result = b.plan_batches(segments)
        # Each segment = 50 chars. With sep: 50 + 6 = 56 per additional.
        # Batch capacity ≈ 50 + (n-1)*56 ≤ 1000 → n ≈ 17-18 per batch
        assert len(result) < 10
        flat = [s for batch in result for s in batch]
        assert flat == segments

    def test_mixed_sizes(self) -> None:
        b = TextBatcher(max_batch_chars=20, separator_overhead=0)
        segments = ["a", "b" * 15, "c", "d" * 18, "e"]
        result = b.plan_batches(segments)
        # "a"(1) + "b*15"(15) = 16 ≤ 20; + "c"(1) = 17 ≤ 20
        # + "d*18"(18) = 35 > 20 → new batch
        # "d*18"(18) + "e"(1) = 19 ≤ 20
        assert result == [["a", "b" * 15, "c"], ["d" * 18, "e"]]

    def test_all_oversized_each_gets_own_batch(self) -> None:
        b = TextBatcher(max_batch_chars=5)
        segments = ["toolong1", "toolong2", "toolong3"]
        result = b.plan_batches(segments)
        assert result == [["toolong1"], ["toolong2"], ["toolong3"]]
