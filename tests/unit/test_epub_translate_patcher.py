from __future__ import annotations

import pytest


def test_patch_xhtml_with_alternating_bilingual_keeps_anchor_ids() -> None:
    from ai.epub_package import extract_translatable_segments, patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p id='p1'>Hello.</p></body></html>"
    segments = extract_translatable_segments(source)
    assert len(segments) == 1
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


def test_patch_xhtml_alternating_uses_block_translation_wrapper() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Hello.</p></body></html>"
    patched = patch_xhtml_alternating(source, translations=["你好。"])
    assert 'class="bw-translation"' in patched
    assert "Hello." in patched
    assert "你好。" in patched


def test_patch_xhtml_alternating_skips_heading_translation() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'>"
        "<body><h1>Foreword</h1><p>Body text.</p></body></html>"
    )
    patched = patch_xhtml_alternating(source, translations=["正文。"])
    assert "Foreword" in patched
    assert "前言" not in patched
    assert "正文。" in patched


def test_patch_xhtml_alternating_skips_toc_doc_translation() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'>"
        "<body><h1>Contents</h1><p><a href='c1.xhtml'>Chapter One</a></p></body></html>"
    )
    patched = patch_xhtml_alternating(
        source,
        translations=["第一章"],
        document_path="OEBPS/xhtml/04_Contents.xhtml",
    )
    assert "Contents" in patched
    assert "Chapter One" in patched
    assert "目录" not in patched
    assert "第一章" not in patched


def test_extract_translatable_segments_returns_block_level_segments() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Hello <a href='x'>link</a> world.</p>"
        "<p>Second paragraph.</p>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert len(segments) == 2
    assert segments[0].text == "Hello link world."
    assert segments[1].text == "Second paragraph."


def test_patch_xhtml_alternating_inserts_one_translation_block_per_source_block() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Alpha <a href='u'>Link</a> tail.</p>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["阿尔法链接尾部。"])
    assert patched.count('class="bw-translation"') == 1


def test_patch_xhtml_alternating_never_injects_translation_inside_anchor() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>Read <a href='https://example.com'>docs</a> now.</p>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["现在阅读文档。"])
    assert 'href="https://example.com"' in patched
    assert ">docs</" in patched
    assert "bw-translation" in patched
    assert (
        "bw-translation" not in patched.partition('href="https://example.com"')[2].split("</", 1)[0]
    )
