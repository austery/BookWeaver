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


def test_extract_translatable_segments_includes_leaf_div_prose() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='intro'>\n  Hello <span>world</span>!\n</div>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert len(segments) == 1
    assert segments[0].tag_name == "div"
    assert segments[0].text == "Hello world!"


def test_extract_translatable_segments_skips_short_bold_heading_div() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='chapter-heading'><b>Preface</b></div>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert segments == []


def test_extract_translatable_segments_skips_div_with_image_descendant() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='figure'><img src='figure.png' alt='Figure'/>Figure 1.</div>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert segments == []


def test_extract_translatable_segments_skips_outer_div_when_inner_paragraph_exists() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='wrapper'><p>Inner paragraph.</p></div>"
        "<div class='leaf'>\n Leaf div prose. \n</div>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert [segment.tag_name for segment in segments] == ["p", "div"]
    assert [segment.text for segment in segments] == ["Inner paragraph.", "Leaf div prose."]


def test_extract_translatable_segments_preserves_br_linebreaks() -> None:
    from ai.epub_package import extract_translatable_segments

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p><a href='#1'>AAA pattern</a><br/>\n"
        "    <a href='#2'>avoiding if statements</a><br/>\n"
        "    <a href='#3'>avoiding multiple AAA sections</a></p>"
        "</body></html>"
    )
    segments = extract_translatable_segments(source)
    assert len(segments) == 1
    assert segments[0].text == "AAA pattern\navoiding if statements\navoiding multiple AAA sections"


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


def test_patch_xhtml_alternating_preserves_default_xhtml_namespace_serialization() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Hello.</p></body></html>"
    patched = patch_xhtml_alternating(source, ["你好。"])
    assert "<html:" not in patched


def test_patch_xhtml_alternating_keeps_table_cells_source_only() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<table><thead><tr><th>OrderID</th><th>CustomerName</th></tr></thead>"
        "<tbody><tr><td>100</td><td>Joe Reis</td></tr></tbody></table>"
        "<p>After table.</p>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["表后文本。"])
    assert "OrderID" in patched and "CustomerName" in patched
    assert "Joe Reis" in patched
    assert "订单ID" not in patched
    assert "客户姓名" not in patched
    assert "乔·雷斯" not in patched
    assert "表后文本。" in patched


def test_patch_xhtml_alternating_inserts_translation_after_prose_div() -> None:
    import xml.etree.ElementTree as ET

    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<div class='prose'>\n  Leaf div prose. \n</div>"
        "</body></html>"
    )
    translation = "叶子 div 段落。"
    patched = patch_xhtml_alternating(source, [translation])

    ns = {"x": "http://www.w3.org/1999/xhtml"}
    root = ET.fromstring(patched)
    body = root.find(".//x:body", ns)
    assert body is not None
    children = list(body)
    assert len(children) == 2
    assert children[0].tag == "{http://www.w3.org/1999/xhtml}div"
    assert children[1].attrib["class"] == "bw-translation"
    assert children[1].text == translation


def test_patch_xhtml_alternating_preserves_ordered_list_item_count() -> None:
    """Translation injection must not double <li> count in ordered lists.

    Inserting a sibling <li> for each translation causes <ol> to re-number
    from 1–N to 1–2N. Translations must be nested inside the source <li>
    as a <p class="bw-translation"> child.
    """
    import xml.etree.ElementTree as ET

    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<ol>"
        "<li>Food value in calories.</li>"
        "<li>Flavor and aroma.</li>"
        "<li>Stimulus, as by sugar.</li>"
        "</ol>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["热量食物价值。", "风味和香气。", "刺激，如糖。"])

    ns = {"x": "http://www.w3.org/1999/xhtml"}
    root = ET.fromstring(patched)
    li_items = root.findall(".//x:li", ns)
    assert len(li_items) == 3, f"Expected 3 <li> items, got {len(li_items)}"

    # Each translation must be a <p class="bw-translation"> nested inside its <li>
    translations_in_li = [
        p.text for li in li_items for p in li.findall("x:p[@class='bw-translation']", ns)
    ]
    assert translations_in_li == ["热量食物价值。", "风味和香气。", "刺激，如糖。"]


def test_patch_xhtml_alternating_preserves_unordered_list_item_count() -> None:
    """Translation injection must not insert extra <li> siblings into <ul> lists.

    Same code path as <ol> — translations are nested inside source <li> as
    <p class="bw-translation"> children so list semantics are preserved.
    """
    import xml.etree.ElementTree as ET

    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<ul>"
        "<li>Apples.</li>"
        "<li>Oranges.</li>"
        "</ul>"
        "</body></html>"
    )
    patched = patch_xhtml_alternating(source, ["苹果。", "橙子。"])

    ns = {"x": "http://www.w3.org/1999/xhtml"}
    root = ET.fromstring(patched)
    li_items = root.findall(".//x:li", ns)
    assert len(li_items) == 2, f"Expected 2 <li> items, got {len(li_items)}"

    translations_in_li = [
        p.text for li in li_items for p in li.findall("x:p[@class='bw-translation']", ns)
    ]
    assert translations_in_li == ["苹果。", "橙子。"]


def test_patch_xhtml_alternating_adds_caption_horizontal_compat_css() -> None:
    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'>"
        "<head><title>Demo</title></head>"
        "<body><p>Body text.</p><table><caption><span class='label'>Table 1-1. </span>Demo</caption></table></body>"
        "</html>"
    )
    patched = patch_xhtml_alternating(source, ["正文文本。"])
    assert "#sbo-rt-content table caption" in patched
    assert "writing-mode: horizontal-tb" in patched
    assert "text-orientation: mixed" in patched
    assert "display: table-caption" in patched


# ── TDD: Index structure preservation (multiline segments with <br/>) ──────────


def test_patch_xhtml_alternating_preserves_br_linebreaks_in_translation() -> None:
    """Translation of <p> blocks containing <br/> tags must render with <br/>
    in the injected translation element.

    Root cause: _insert_translation_block() sets translated_block.text = translation
    (plain text). When the source has <p>...<br/>...<br/>...</p>, the extracted
    text has \\n characters. The translation also returns \\n-separated lines.
    But .text = "line1\\nline2" in HTML renders as whitespace — NOT as line breaks.
    The translated index therefore collapses into one dense paragraph.

    Correct behavior: \\n in translated text → <br/> element in the output.
    """
    import xml.etree.ElementTree as ET

    from ai.epub_package import patch_xhtml_alternating

    # Simulate a Kindle-style index block: <p><kbd><small>entries with <br/></small></kbd></p>
    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p class='calibre16'><kbd><small>"
        "<a href='#1'>AAA pattern</a><br/>\n"
        "    <a href='#2'>avoiding if statements</a><br/>\n"
        "    <a href='#3'>avoiding multiple AAA sections</a>"
        "</small></kbd></p>"
        "</body></html>"
    )

    # Translation preserves newline structure (what Gemini returns)
    translation = "AAA 模式\n    避免 if 语句\n    避免多个 AAA 节"

    patched = patch_xhtml_alternating(source, [translation])

    ns = {"x": "http://www.w3.org/1999/xhtml"}
    root = ET.fromstring(patched)

    # Find the injected translation element
    bw = root.find(".//*[@class='bw-translation']", ns)
    assert bw is not None, "Translation block not found"

    # The translation must contain <br/> elements — not just plain text with \n
    br_elements = list(bw.iter("{http://www.w3.org/1999/xhtml}br")) + list(bw.iter("br"))
    assert len(br_elements) > 0, (
        "Translation block must contain <br/> elements to preserve line structure. "
        "Plain text \\n chars render as whitespace in HTML and collapse the index hierarchy."
    )

    # The content must still contain the translated text
    full_text = "".join(bw.itertext())
    assert "AAA 模式" in full_text
    assert "避免 if 语句" in full_text
    assert "避免多个 AAA 节" in full_text


def test_patch_xhtml_alternating_no_br_in_simple_translation() -> None:
    """For normal paragraphs without \\n, translation is still injected as plain text
    (no spurious <br/> elements added)."""
    import xml.etree.ElementTree as ET

    from ai.epub_package import patch_xhtml_alternating

    source = (
        "<html xmlns='http://www.w3.org/1999/xhtml'><body>"
        "<p>This is a simple paragraph.</p>"
        "</body></html>"
    )
    translation = "这是一个简单的段落。"
    patched = patch_xhtml_alternating(source, [translation])

    ns = {"x": "http://www.w3.org/1999/xhtml"}
    root = ET.fromstring(patched)
    bw = root.find(".//*[@class='bw-translation']", ns)
    assert bw is not None

    # Simple translations should NOT have <br/> elements
    br_elements = list(bw.iter("{http://www.w3.org/1999/xhtml}br")) + list(bw.iter("br"))
    assert len(br_elements) == 0

    assert bw.text == translation
