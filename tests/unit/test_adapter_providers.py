"""Unit tests for the provider adapter layer.

Tests delimiter join/split logic and adapter retry/error-mapping behavior.
Uses fake raw providers — no real API calls or subprocess invocations.
"""

from __future__ import annotations

import pytest

from ai.adapters.providers._delimiter import (
    PROTOCOL_SEGMENT_TAGS,
    SEPARATOR_OVERHEAD,
    augment_prompt_for_batch,
    join_segments,
    split_response,
)
from ai.ports.provider import TranslationError


# ── Delimiter helpers ─────────────────────────────────────────


class TestJoinSegments:
    def test_empty(self) -> None:
        assert join_segments([]) == ""

    def test_single(self) -> None:
        assert join_segments(["Hello"]) == "Hello"

    def test_multiple(self) -> None:
        assert join_segments(["A", "B"]) == "A\n\n%%\n\nB"

    def test_three(self) -> None:
        assert join_segments(["X", "Y", "Z"]) == "X\n\n%%\n\nY\n\n%%\n\nZ"

    def test_segment_tags_protocol(self) -> None:
        assert (
            join_segments(
                ["A", "B"],
                protocol=PROTOCOL_SEGMENT_TAGS,
            )
            == '<segment id="1">A</segment>\n\n<segment id="2">B</segment>'
        )


class TestSplitResponse:
    def test_single_returns_stripped(self) -> None:
        assert split_response("  hello  ", 1) == ["hello"]

    def test_exact_separator(self) -> None:
        assert split_response("甲\n\n%%\n\n乙", 2) == ["甲", "乙"]

    def test_flexible_whitespace(self) -> None:
        assert split_response("A\n %%  \nB", 2) == ["A", "B"]

    def test_mismatch_raises(self) -> None:
        with pytest.raises(TranslationError, match="count mismatch"):
            split_response("only-one", 2)

    def test_zero_expected(self) -> None:
        assert split_response("anything", 0) == []

    def test_three_segments(self) -> None:
        text = "一\n\n%%\n\n二\n\n%%\n\n三"
        assert split_response(text, 3) == ["一", "二", "三"]

    def test_segment_tags_exact(self) -> None:
        text = '<segment id="1">甲</segment>\n<segment id="2">乙</segment>'
        assert split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS) == ["甲", "乙"]

    def test_segment_tags_with_markdown_fence_wrapper(self) -> None:
        text = '```xml\n<segment id="1">甲</segment>\n<segment id="2">乙</segment>\n```'
        assert split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS) == ["甲", "乙"]

    def test_segment_tags_allows_empty_segment_body(self) -> None:
        text = '<segment id="1">甲</segment>\n<segment id="2">   </segment>'
        assert split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS) == ["甲", ""]

    def test_segment_tags_duplicate_id_raises(self) -> None:
        text = '<segment id="1">甲</segment>\n<segment id="1">乙</segment>'
        with pytest.raises(TranslationError, match="duplicate ids"):
            split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS)

    def test_segment_tags_missing_id_raises(self) -> None:
        text = '<segment id="1">甲</segment>\n<segment id="3">乙</segment>'
        with pytest.raises(TranslationError, match=r"missing=\[2\]"):
            split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS)

    def test_segment_tags_text_outside_tags_raises(self) -> None:
        text = '<segment id="1">甲</segment>\nextra\n<segment id="2">乙</segment>'
        with pytest.raises(TranslationError, match="outside tags"):
            split_response(text, 2, protocol=PROTOCOL_SEGMENT_TAGS)

    def test_empty_output_single_segment_raises(self) -> None:
        """Empty provider output must raise TranslationError, not return ['']."""
        with pytest.raises(TranslationError, match="empty"):
            split_response("", 1)

    def test_whitespace_only_output_single_segment_raises(self) -> None:
        """Whitespace-only output is also empty — must raise TranslationError."""
        with pytest.raises(TranslationError, match="empty"):
            split_response("   \n  ", 1)


class TestAugmentPrompt:
    def test_single_segment_unchanged(self) -> None:
        assert augment_prompt_for_batch("prompt", 1) == "prompt"

    def test_multi_segment_adds_instructions(self) -> None:
        result = augment_prompt_for_batch("prompt", 2)
        assert "%%" in result
        assert "IMPORTANT" in result

    def test_zero_segments_unchanged(self) -> None:
        assert augment_prompt_for_batch("prompt", 0) == "prompt"

    def test_segment_tags_adds_strict_contract(self) -> None:
        result = augment_prompt_for_batch("prompt", 2, protocol=PROTOCOL_SEGMENT_TAGS)
        assert "STRICT OUTPUT CONTRACT" in result
        assert '<segment id="1">' in result


class TestSeparatorOverhead:
    def test_is_six(self) -> None:
        assert SEPARATOR_OVERHEAD == 6
