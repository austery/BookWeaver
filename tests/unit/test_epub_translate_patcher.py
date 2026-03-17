from __future__ import annotations

import pytest


def test_patch_xhtml_with_alternating_bilingual_keeps_anchor_ids() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p id='p1'>Hello.</p></body></html>"
    patched = patch_xhtml_alternating(source, translations=["你好。"])
    assert 'id="p1"' in patched
    assert "Hello." in patched
    assert "你好。" in patched


def test_patch_xhtml_alternating_requires_matching_translation_count() -> None:
    from ai.epub_package import extract_translatable_segments, patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Hello.</p></body></html>"
    segments = extract_translatable_segments(source)
    assert len(segments) == 1
    with pytest.raises(ValueError, match="translation count"):
        patch_xhtml_alternating(source, translations=[])
