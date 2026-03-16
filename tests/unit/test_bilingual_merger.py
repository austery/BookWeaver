from ai.bilingual_merger import BilingualMerger


def test_merge_alternating_pairs_in_order():
    merger = BilingualMerger()
    result = merger.merge(
        original_chunks=["Hello world", "Second paragraph"],
        translated_chunks=["你好，世界", "第二段"],
    )
    idx_en1 = result.index("Hello world")
    idx_zh1 = result.index("你好，世界")
    idx_en2 = result.index("Second paragraph")
    idx_zh2 = result.index("第二段")
    assert idx_en1 < idx_zh1 < idx_en2 < idx_zh2


def test_merge_raises_on_mismatched_chunk_count():
    merger = BilingualMerger()
    try:
        merger.merge(original_chunks=["A", "B"], translated_chunks=["甲"])
    except ValueError:
        return
    raise AssertionError("Expected ValueError on mismatched chunk count")

