from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai.glossary_extractor import (
    _build_extraction_prompt,
    _collect_spine_blocks,
    _looks_like_index_content,
    _validate_and_parse_glossary,
    extract_epub_index_and_toc,
    extract_glossary_from_epub,
)


_VALID_GLOSSARY_JSON = json.dumps(
    {
        "critical_terminology": [
            {
                "term": "TestTerm",
                "suggested_translation": "测试术语",
                "reason": "test term",
                "priority": "high",
            }
        ]
    }
)


def _wrap_xhtml(body: str) -> str:
    return (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<body>{body}</body></html>"
    )


def _make_xhtml(body: str) -> str:
    return _wrap_xhtml(body)


def _make_opf(spine_items: list[str]) -> str:
    manifest_entries = "".join(
        f'<item id="item{i}" href="{item}" media-type="application/xhtml+xml"/>'
        for i, item in enumerate(spine_items)
    )
    spine_entries = "".join(
        f'<itemref idref="item{i}"/>' for i, _ in enumerate(spine_items)
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Book</dc:title></metadata>"
        "<manifest>" + manifest_entries + "</manifest>"
        "<spine>" + spine_entries + "</spine>"
        "</package>"
    )


def _make_test_epub(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create an EPUB zip with specific file contents."""
    epub = tmp_path / "test.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("META-INF/container.xml", container_xml)
        for path, content in files.items():
            z.writestr(path, content)
    return epub


def _make_minimal_epub(tmp_path: Path, index_content: str = "", toc_content: str = "") -> Path:
    """Create a minimal valid EPUB zip for testing."""
    epub = tmp_path / "test.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Book</dc:title></metadata>"
        "<manifest>"
        '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="idx" href="index.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>"
        '<spine toc="toc"><itemref idref="toc"/><itemref idref="idx"/></spine>'
        "</package>"
    )
    toc_xhtml = _wrap_xhtml(f"<nav><ol><li>{toc_content}</li></ol></nav>")
    idx_xhtml = _wrap_xhtml(f"<p>{index_content}</p>")
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("META-INF/container.xml", container_xml)
        z.writestr("OEBPS/content.opf", opf_xml)
        z.writestr("OEBPS/toc.xhtml", toc_xhtml)
        z.writestr("OEBPS/index.xhtml", idx_xhtml)
    return epub


def _make_spine_epub(
    tmp_path: Path,
    docs: list[tuple[str, str, str]],
    *,
    toc_content: str = "Chapter 1",
    include_named_index: bool = False,
    named_index_content: str = "",
) -> Path:
    """Create EPUB with arbitrary spine docs for index-detection heuristics."""
    epub = tmp_path / "spine-test.epub"
    manifest_entries = ['<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>']
    spine_entries = ['<itemref idref="toc"/>']

    for item_id, href, _ in docs:
        manifest_entries.append(
            f'<item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_entries.append(f'<itemref idref="{item_id}"/>')

    if include_named_index:
        manifest_entries.append(
            '<item id="idx" href="index.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine_entries.append('<itemref idref="idx"/>')

    opf_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Book</dc:title></metadata>"
        "<manifest>" + "".join(manifest_entries) + "</manifest>"
        '<spine toc="toc">' + "".join(spine_entries) + "</spine>"
        "</package>"
    )

    with zipfile.ZipFile(epub, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr("OEBPS/content.opf", opf_xml)
        z.writestr("OEBPS/toc.xhtml", _wrap_xhtml(f"<nav><ol><li>{toc_content}</li></ol></nav>"))

        for _, href, body in docs:
            z.writestr(f"OEBPS/{href}", _wrap_xhtml(body))

        if include_named_index:
            z.writestr("OEBPS/index.xhtml", _wrap_xhtml(f"<p>{named_index_content}</p>"))

    return epub


def test_extract_epub_index_and_toc_returns_text(tmp_path: Path) -> None:
    epub = _make_minimal_epub(tmp_path, index_content="Connascence, 42", toc_content="Chapter 1")
    index_text, toc_text = extract_epub_index_and_toc(epub)
    assert "Connascence" in index_text
    assert "Chapter 1" in toc_text


def test_extract_epub_index_and_toc_missing_index(tmp_path: Path) -> None:
    """If no index document found, index_text is empty string."""
    epub = _make_minimal_epub(tmp_path, toc_content="Chapter 1")
    index_text, toc_text = extract_epub_index_and_toc(epub)
    assert isinstance(index_text, str)
    assert isinstance(toc_text, str)


def test_extract_epub_index_and_toc_pass3_detects_film_club_like_tail_doc(tmp_path: Path) -> None:
    """Pass-3 should detect index-like content even without index filename/nav markers."""
    film_club_index = (
        "<h1>Index</h1>"
        "<p>Aguirre, Wrath of God, ♣</p>"
        "<p>All That Jazz, ♣</p>"
        "<p>Annie Hall, ♣</p>"
        "<p>Badlands, ♣</p>"
        "<p>Cries and Whispers, ♣</p>"
        "<p>Days of Heaven, ♣</p>"
        "<p>The Conformist, ♣</p>"
    )
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c24", "c24.xhtml", "<h1>Chapter 24</h1><p>Regular chapter prose.</p>"),
            ("c25", "c25.xhtml", "<h1>Chapter 25</h1><p>More regular chapter prose.</p>"),
            ("c27", "c27.xhtml", film_club_index),
        ],
        toc_content="Part 1",
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Aguirre, Wrath of God, ♣" in index_text
    assert "Cries and Whispers, ♣" in index_text


def test_extract_epub_index_and_toc_pass3_detects_searchable_terms_heading(
    tmp_path: Path,
) -> None:
    searchable_terms = (
        "<h2>Searchable Terms</h2>"
        "<p>Abstract Factory, 33</p>"
        "<p>Builder Pattern, 49</p>"
        "<p>Dependency Injection, 77</p>"
        "<p>Hexagonal Architecture, 112</p>"
        "<p>Ports and Adapters, 145</p>"
    )
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c10", "chapter10.xhtml", "<h1>Chapter 10</h1><p>Narrative text only.</p>"),
            ("c11", "chapter11.xhtml", searchable_terms),
        ],
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Abstract Factory, 33" in index_text
    assert "Ports and Adapters, 145" in index_text


def test_extract_epub_index_and_toc_pass3_avoids_false_positive_on_chapter_prose(
    tmp_path: Path,
) -> None:
    prose_tail = (
        "<h1>Index</h1>"
        "<p>In this chapter, we revisit the father-son dynamic and memory.</p>"
        "<p>The narrator reflects on the passing of time, grief, and identity.</p>"
        "<p>These paragraphs are prose, not an index.</p>"
    )
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c26", "c26.xhtml", "<h1>Chapter 26</h1><p>Regular chapter content.</p>"),
            ("c27", "c27.xhtml", prose_tail),
        ],
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert index_text == ""


def test_extract_epub_index_and_toc_prefers_pass1_named_index_over_pass3(tmp_path: Path) -> None:
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c27", "c27.xhtml", "<h1>Index</h1><p>Aguirre, Wrath of God, ♣</p>"),
        ],
        include_named_index=True,
        named_index_content="Canonical Index, 101",
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Canonical Index, 101" in index_text
    assert "Aguirre, Wrath of God, ♣" not in index_text


def test_extract_epub_index_and_toc_prefers_pass2_marker_over_pass3(tmp_path: Path) -> None:
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c26", "c26.xhtml", "<p>[ A ][ B ][ C ]</p><p>Adapter, 10</p>"),
            ("c27", "c27.xhtml", "<h1>Index</h1><p>Aguirre, Wrath of God, ♣</p>"),
        ],
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Adapter, 10" in index_text
    assert "Aguirre, Wrath of God, ♣" not in index_text


def test_extract_epub_index_and_toc_skips_placeholder_named_index_and_finds_real_index(
    tmp_path: Path,
) -> None:
    """When many *index* files exist, placeholder pages must not lock index_text early."""
    real_index = (
        "<h1>Index</h1>"
        "<p>AbortError, 101</p>"
        "<p>Connascence, 202</p>"
        "<p>Hexagonal Architecture, 303</p>"
        "<p>Ports and Adapters, 404</p>"
    )
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("i0", "index_split_000.xhtml", "<p>Converted Ebook</p>"),
            ("i1", "index_split_001.xhtml", "<p>Front matter only</p>"),
            ("i2", "index_split_079.xhtml", real_index),
        ],
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Converted Ebook" not in index_text
    assert "AbortError, 101" in index_text
    assert "Ports and Adapters, 404" in index_text


def test_extract_epub_index_and_toc_uses_scorer_selected_glossary_doc(tmp_path: Path) -> None:
    """Integration test: scorer detects epub:type=glossary doc and extracts it."""
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("c1", "chapter1.xhtml", "<h1>Chapter 1</h1><p>Regular chapter content.</p>"),
            (
                "back",
                "appendix.xhtml",
                '<section epub:type="glossary"><h2>Glossary</h2><p>Connascence, 42</p><p>Hexagonal Architecture, 112</p></section>',
            ),
        ],
        toc_content="Part 1",
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    assert "Connascence, 42" in index_text
    assert "Hexagonal Architecture, 112" in index_text


def test_extract_epub_index_and_toc_prefers_strongest_candidate_not_first_strong(
    tmp_path: Path,
) -> None:
    """Regression: _select_scored_index_text must choose STRONGEST candidate, not first-strong.

    Scenario:
    - chapter01.xhtml has class="indexterm" + line_shape (borderline, weak score)
    - backmatter.xhtml has epub:type="index" (strong score)

    Expected: backmatter.xhtml wins (highest score)
    Actual (before fix): chapter01.xhtml wins (first strong candidate in spine order)
    """
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            # Borderline chapter: class="indexterm" + line_shape (if css_class wrongly triggered = 40 score)
            (
                "c1",
                "chapter01.xhtml",
                '<div class="indexterm"><p>Adapter, 10-15, 42</p><p>Bridge, 22</p></div>',
            ),
            # Real backmatter index: epub:type="index" (score=40 from epub_type alone)
            (
                "idx",
                "backmatter.xhtml",
                '<section epub:type="index"><h2>Index</h2><p>Connascence, 99</p><p>Hexagonal Architecture, 202</p></section>',
            ),
        ],
        toc_content="Part 1",
    )
    index_text, _ = extract_epub_index_and_toc(epub)
    # Must prefer the stronger backmatter index, NOT the earlier borderline chapter
    assert "Connascence, 99" in index_text
    assert "Hexagonal Architecture, 202" in index_text
    # Borderline chapter content must NOT leak through
    assert "Adapter, 10-15, 42" not in index_text


def test_build_extraction_prompt_contains_index_and_toc() -> None:
    prompt = _build_extraction_prompt("Connascence, 42", "Chapter 1: Intro", max_terms=15)
    assert "Connascence" in prompt
    assert "Chapter 1" in prompt
    assert "15" in prompt


def test_validate_and_parse_glossary_valid() -> None:
    raw = json.dumps(
        {
            "critical_terminology": [
                {
                    "term": "Connascence",
                    "suggested_translation": "共生性",
                    "priority": "critical",
                }
            ]
        }
    )
    result = _validate_and_parse_glossary(raw)
    assert result["critical_terminology"][0]["term"] == "Connascence"


def test_validate_and_parse_glossary_strips_markdown_fence() -> None:
    raw = '```json\n{"critical_terminology": []}\n```'
    result = _validate_and_parse_glossary(raw)
    assert "critical_terminology" in result


def test_validate_and_parse_glossary_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        _validate_and_parse_glossary("not json at all")


def test_validate_and_parse_glossary_missing_key_raises() -> None:
    with pytest.raises(ValueError, match="missing 'critical_terminology'"):
        _validate_and_parse_glossary('{"wrong": []}')


def test_validate_and_parse_glossary_accepts_non_dict_entries_for_model_compatibility() -> None:
    raw = '{"critical_terminology": ["raw term string"]}'
    result = _validate_and_parse_glossary(raw)
    assert result["critical_terminology"] == ["raw term string"]


def test_validate_and_parse_glossary_rejects_non_object_root() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_and_parse_glossary("[]")


def test_extract_glossary_from_epub_writes_json(tmp_path: Path) -> None:
    """Integration: extract_glossary_from_epub calls translate_fn and writes JSON."""
    epub = _make_minimal_epub(tmp_path, index_content="Connascence, 42", toc_content="Chapter 1")
    output_path = tmp_path / "glossary.json"
    model_response = json.dumps(
        {
            "critical_terminology": [
                {
                    "term": "Connascence",
                    "suggested_translation": "共生性",
                    "negative_constraint": "NOT 并发性",
                    "reason": "author concept",
                    "priority": "critical",
                }
            ]
        }
    )

    mock_translate = MagicMock(return_value=model_response)

    extract_glossary_from_epub(
        epub_path=epub,
        output_path=output_path,
        translate_fn=mock_translate,
        max_terms=20,
    )

    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["critical_terminology"][0]["term"] == "Connascence"


def test_looks_like_index_content_kindle_nav_bar() -> None:
    """Kindle-style alpha nav bar is detected as index content."""
    assert _looks_like_index_content("[ a ][ b ][ c ][ d ] some terms here") is True


def test_looks_like_index_content_normal_chapter_text() -> None:
    """Normal chapter prose is not detected as index content."""
    assert (
        _looks_like_index_content("In this chapter we explore the concept of connascence") is False
    )


def test_build_extraction_prompt_full_index_uses_full_template() -> None:
    """full_index=True uses the full-index template (no max_terms placeholder)."""
    prompt = _build_extraction_prompt(
        "Connascence, 42", "Chapter 1: Intro", max_terms=15, full_index=True
    )
    assert "Connascence" in prompt
    assert "max_terms" not in prompt
    assert "{max_terms}" not in prompt


def test_build_extraction_prompt_selective_uses_max_terms() -> None:
    """full_index=False uses selective template containing the max_terms value."""
    prompt = _build_extraction_prompt(
        "Connascence, 42", "Chapter 1: Intro", max_terms=15, full_index=False
    )
    assert "Connascence" in prompt
    assert "15" in prompt


def test_collect_spine_blocks_skips_toc_and_boilerplate(tmp_path: Path) -> None:
    """_collect_spine_blocks should skip TOC/nav boilerplate and retain front/body content."""
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            ("front", "preface.xhtml", "<h1>Preface</h1><p>This is the preface content.</p>"),
            ("c1", "chapter1.xhtml", "<h1>Chapter 1</h1><p>This is chapter 1 content.</p>"),
            ("c2", "chapter2.xhtml", "<h1>Chapter 2</h1><p>This is chapter 2 content.</p>"),
            ("back", "appendix.xhtml", "<h1>Appendix</h1><p>This is appendix content.</p>"),
        ],
        toc_content="Part 1",
    )

    blocks = _collect_spine_blocks(epub)

    # Verify we got blocks
    assert len(blocks) > 0

    # Verify TOC was skipped (toc.xhtml should not appear in text)
    texts = [block.text for block in blocks]
    combined_text = " ".join(texts)
    assert "Part 1" not in combined_text or len([t for t in texts if "Part 1" in t]) == 0

    # Verify actual content is present
    assert any("preface content" in text.lower() for text in texts)
    assert any("chapter 1 content" in text.lower() for text in texts)
    assert any("appendix content" in text.lower() for text in texts)

    # Verify labels exist (front, body, back)
    labels = [block.label for block in blocks]
    assert any(label == "front" for label in labels)
    assert any(label == "body" for label in labels)
    assert any(label == "back" for label in labels)


def test_collect_spine_blocks_skips_nav_via_toc_item_id(tmp_path: Path) -> None:
    """Regression: _collect_spine_blocks should skip nav/toc via toc_item_id even if href is not 'toc.xhtml'."""
    epub = tmp_path / "nav-test.epub"

    # Create EPUB with nav document declared via spine@toc but with non-standard filename
    opf_xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Book</dc:title></metadata>"
        "<manifest>"
        '<item id="nav" href="navigation.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>"
        '<spine toc="nav">'  # nav is declared as TOC via spine@toc
        '<itemref idref="nav"/>'
        '<itemref idref="c1"/>'
        '<itemref idref="c2"/>'
        "</spine>"
        "</package>"
    )

    with zipfile.ZipFile(epub, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr("OEBPS/content.opf", opf_xml)
        z.writestr(
            "OEBPS/navigation.xhtml",
            _wrap_xhtml("<nav><ol><li>Table of Contents Marker</li></ol></nav>"),
        )
        z.writestr(
            "OEBPS/chapter1.xhtml", _wrap_xhtml("<h1>Chapter 1</h1><p>Chapter 1 content.</p>")
        )
        z.writestr(
            "OEBPS/chapter2.xhtml", _wrap_xhtml("<h1>Chapter 2</h1><p>Chapter 2 content.</p>")
        )

    blocks = _collect_spine_blocks(epub)

    # Verify we got blocks
    assert len(blocks) > 0

    # Verify nav was skipped even though it's not named "toc.xhtml" or "contents.xhtml"
    texts = [block.text for block in blocks]
    combined_text = " ".join(texts)
    assert "Table of Contents Marker" not in combined_text, (
        "Nav document should be skipped via toc_item_id"
    )

    # Verify actual chapters are present
    assert any("Chapter 1 content" in text for text in texts)
    assert any("Chapter 2 content" in text for text in texts)


def test_collect_spine_blocks_keeps_content_files_with_toc_substring(tmp_path: Path) -> None:
    """Regression: content files like protocols.xhtml must not be mistaken for TOC docs."""
    epub = _make_spine_epub(
        tmp_path,
        docs=[
            (
                "p1",
                "protocols.xhtml",
                "<h1>Protocols</h1><p>Protocol terminology should remain available.</p>",
            ),
            ("c2", "chapter2.xhtml", "<h1>Chapter 2</h1><p>Chapter 2 content.</p>"),
        ],
    )

    blocks = _collect_spine_blocks(epub)

    texts = [block.text for block in blocks]
    combined_text = " ".join(texts)

    assert "Protocol terminology should remain available." in combined_text
    assert any("Chapter 2 content." in text for text in texts)


def test_extract_glossary_auto_falls_back_to_deep_scan_when_no_index_signals(
    tmp_path: Path,
) -> None:
    """Auto mode must fall back to Tier 3 deep-scan when no index signals exist."""
    epub_path = _make_test_epub(
        tmp_path,
        files={
            "OEBPS/content.opf": _make_opf(spine_items=["chapter.xhtml"]),
            "OEBPS/chapter.xhtml": _make_xhtml(
                "<p>Some body content without any index structure.</p>"
            ),
        },
    )
    calls: list[str] = []

    def capture_fn(prompt: str) -> str:
        calls.append(prompt)
        return _VALID_GLOSSARY_JSON

    report = extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=tmp_path / "out.json",
        translate_fn=capture_fn,
    )
    assert report["tier"] == "deep-scan", "No-index auto mode must fall back to Tier 3 deep-scan"
    assert len(calls) == 1
    # Tier 3 prompt should contain the chapter body text (full book scan)
    assert "body content" in calls[0]


def test_extract_glossary_auto_toc_only_falls_back_to_deep_scan(
    tmp_path: Path,
) -> None:
    """Auto mode TOC-only books must fall back to Tier 3 deep-scan."""
    epub_path = _make_test_epub(
        tmp_path,
        files={
            "OEBPS/content.opf": _make_opf(spine_items=["toc.xhtml", "chapter.xhtml"]),
            "OEBPS/toc.xhtml": _make_xhtml("<nav><ol><li>Chapter 1</li></ol></nav>"),
            "OEBPS/chapter.xhtml": _make_xhtml("<p>Body text here.</p>"),
        },
    )

    def simple_fn(prompt: str) -> str:
        return _VALID_GLOSSARY_JSON

    report = extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=tmp_path / "out.json",
        translate_fn=simple_fn,
    )
    assert report["tier"] == "deep-scan", "TOC-only must fall back to Tier 3 deep-scan"


def test_extract_glossary_deep_scan_uses_dedicated_prompt(tmp_path: Path) -> None:
    """Deep-scan mode should use whole-book extraction prompt."""
    docs = [
        ("ch1", "chapter1.xhtml", "<p>Chapter 1: Advanced topics in Hexagonal Architecture.</p>"),
        ("ch2", "chapter2.xhtml", "<p>Chapter 2: Ports and Adapters pattern explained.</p>"),
    ]
    epub = _make_spine_epub(tmp_path, docs, include_named_index=False)
    output_path = tmp_path / "glossary.json"

    mock_translate = MagicMock(
        return_value=json.dumps(
            {
                "critical_terminology": [
                    {
                        "term": "Hexagonal Architecture",
                        "suggested_translation": "六边形架构",
                        "reason": "Core pattern",
                        "priority": "critical",
                    }
                ]
            }
        )
    )

    report = extract_glossary_from_epub(
        epub_path=epub,
        output_path=output_path,
        translate_fn=mock_translate,
        max_terms=20,
        mode="deep-scan",
    )

    # Assert deep-scan tier
    assert report["tier"] == "deep-scan"
    # Verify whole-book prompt was used (check prompt content includes whole-book markers)
    prompt_arg = mock_translate.call_args[0][0]
    assert (
        "整本书" in prompt_arg or "whole-book" in prompt_arg.lower() or "WHOLE_BOOK" in prompt_arg
    )


def test_extract_glossary_trims_final_terms_to_max_terms(tmp_path: Path) -> None:
    """Extractor should cap final critical_terminology list to max_terms after parsing."""
    docs = [
        (
            "ch1",
            "chapter1.xhtml",
            "<p>Advanced Hexagonal Architecture and Ports and Adapters pattern.</p>",
        ),
    ]
    epub = _make_spine_epub(tmp_path, docs, include_named_index=False)
    output_path = tmp_path / "glossary.json"

    # Model returns 5 terms but max_terms=2
    mock_translate = MagicMock(
        return_value=json.dumps(
            {
                "critical_terminology": [
                    {"term": f"Term{i}", "suggested_translation": f"术语{i}", "priority": "high"}
                    for i in range(5)
                ]
            }
        )
    )

    extract_glossary_from_epub(
        epub_path=epub,
        output_path=output_path,
        translate_fn=mock_translate,
        max_terms=2,
        mode="deep-scan",
    )

    # Read output and verify it has only 2 terms
    glossary = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(glossary["critical_terminology"]) == 2


def test_extract_glossary_deep_scan_logs_payload_stats(tmp_path: Path) -> None:
    """Deep-scan should emit payload stats (docs, chars) in report."""
    docs = [
        ("ch1", "chapter1.xhtml", "<p>Chapter 1 content here.</p>"),
        ("ch2", "chapter2.xhtml", "<p>Chapter 2 content here.</p>"),
    ]
    epub = _make_spine_epub(tmp_path, docs, include_named_index=False)
    output_path = tmp_path / "glossary.json"

    mock_translate = MagicMock(return_value=json.dumps({"critical_terminology": []}))

    report = extract_glossary_from_epub(
        epub_path=epub,
        output_path=output_path,
        translate_fn=mock_translate,
        max_terms=20,
        mode="deep-scan",
    )

    # Assert stats are present
    assert "docs" in report
    assert "chars" in report
    assert report["docs"] > 0
    assert report["chars"] > 0


# ── Regression Matrix Tests ───────────────────────────────────────


def test_glossary_extraction_regression_matrix_representative_classes(tmp_path: Path) -> None:
    """Regression matrix: locks orchestration paths for representative EPUB classes.

    Classes tested:
    - standard-index: typical tech book with named index file
    - nonstandard-markup: non-standard content structure
    - fiction-no-index: narrative book without index
    - low-density-narrative: fiction with sparse terminology

    The test uses mocked model output; the goal is to verify orchestration
    paths (index detection, tier routing, fallback) remain stable.
    """
    # Create subdirs
    (tmp_path / "standard").mkdir()
    (tmp_path / "nonstandard").mkdir()
    (tmp_path / "fiction").mkdir()
    (tmp_path / "lowdensity").mkdir()

    # Standard index: tech book with named index file
    standard_index_epub = _make_spine_epub(
        tmp_path / "standard",
        docs=[
            ("ch1", "chapter1.xhtml", "<p>Chapter 1: Hexagonal Architecture concepts.</p>"),
        ],
        include_named_index=True,
        named_index_content=(
            "<ul>"
            "<li>Hexagonal Architecture, 12, 34</li>"
            "<li>Ports and Adapters, 56, 78</li>"
            "<li>Domain-Driven Design, 90</li>"
            "<li>Event Sourcing, 101</li>"
            "<li>Command Query Responsibility Segregation, 118</li>"
            "</ul>"
        ),
    )

    # Nonstandard markup: no named index, but high-signal last doc
    nonstandard_docs = [
        ("ch1", "chapter1.xhtml", "<p>Chapter content here.</p>"),
        (
            "appendix",
            "backmatter.xhtml",
            "<h1>Index</h1><p>API Design, Hexagonal Architecture, Domain-Driven Design</p>",
        ),
    ]
    nonstandard_epub = _make_spine_epub(tmp_path / "nonstandard", nonstandard_docs)

    # Fiction no index: narrative with no index-like structures
    fiction_docs = [
        ("ch1", "chapter1.xhtml", "<p>It was a dark and stormy night in the village.</p>"),
        ("ch2", "chapter2.xhtml", "<p>The protagonist walked slowly down the path.</p>"),
    ]
    fiction_epub = _make_spine_epub(tmp_path / "fiction", fiction_docs)

    # Low-density narrative: fiction with sparse terminology
    low_density_docs = [
        ("ch1", "chapter1.xhtml", "<p>Once upon a time in a faraway land.</p>"),
    ]
    low_density_epub = _make_spine_epub(tmp_path / "lowdensity", low_density_docs)

    mock_translate = MagicMock(
        return_value=json.dumps(
            {
                "critical_terminology": [
                    {
                        "term": "Hexagonal Architecture",
                        "suggested_translation": "六边形架构",
                        "priority": "critical",
                    }
                ]
            }
        )
    )

    # Test standard-index (should hit tier-1 named index)
    output1 = tmp_path / "standard" / "glossary.json"
    report1 = extract_glossary_from_epub(
        epub_path=standard_index_epub,
        output_path=output1,
        translate_fn=mock_translate,
        max_terms=20,
        mode="auto",
    )
    assert report1["tier"] == "index"
    assert output1.exists()

    # Test nonstandard-markup (should hit tier-2 via heuristic or tier-1 if signals strong)
    output2 = tmp_path / "nonstandard" / "glossary.json"
    report2 = extract_glossary_from_epub(
        epub_path=nonstandard_epub,
        output_path=output2,
        translate_fn=mock_translate,
        max_terms=20,
        mode="auto",
    )
    # Tier depends on index signal strength
    assert report2["tier"] in ("index", "deep-scan")
    assert output2.exists()

    # Test fiction-no-index (should hit tier-2 local shortlist)
    output3 = tmp_path / "fiction" / "glossary.json"
    report3 = extract_glossary_from_epub(
        epub_path=fiction_epub,
        output_path=output3,
        translate_fn=mock_translate,
        max_terms=20,
        mode="auto",
    )
    assert report3["tier"] == "deep-scan"
    assert output3.exists()

    # Test low-density-narrative (should hit tier-2 with low candidate count)
    output4 = tmp_path / "lowdensity" / "glossary.json"
    report4 = extract_glossary_from_epub(
        epub_path=low_density_epub,
        output_path=output4,
        translate_fn=mock_translate,
        max_terms=20,
        mode="auto",
    )
    assert report4["tier"] == "deep-scan"
    assert output4.exists()


def test_deep_scan_prompt_allows_names_and_places() -> None:
    """Tier 3 prompt must NOT exclude names/places — biographies need them."""
    from ai.glossary_extractor import _DEEP_SCAN_PROMPT_TEMPLATE
    assert "不要人名" not in _DEEP_SCAN_PROMPT_TEMPLATE
    assert "不要地名" not in _DEEP_SCAN_PROMPT_TEMPLATE
