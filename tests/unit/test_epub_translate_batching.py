from __future__ import annotations

import pytest


def test_join_segments_uses_percent_delimiter() -> None:
    from ai.epub_translate_roundtrip import join_segments_for_batch

    assert join_segments_for_batch(["A", "B"]) == "A\n\n%%\n\nB"
    assert join_segments_for_batch(["A"]) == "A"


def test_split_batch_translation_validates_count() -> None:
    from ai.epub_translate_roundtrip import split_batch_translation

    assert split_batch_translation("甲\n\n%%\n\n乙", expected_count=2) == ["甲", "乙"]
    assert split_batch_translation("仅一段", expected_count=1) == ["仅一段"]


def test_split_batch_translation_raises_on_mismatch() -> None:
    from ai.epub_translate_roundtrip import split_batch_translation

    with pytest.raises(ValueError, match="count mismatch"):
        split_batch_translation("only-one", expected_count=2)


def test_split_batch_translation_rejects_delimiter_for_single_expected_segment() -> None:
    from ai.epub_translate_roundtrip import split_batch_translation

    with pytest.raises(ValueError, match="count mismatch"):
        split_batch_translation("A\n\n%%\n\nB", expected_count=1)
