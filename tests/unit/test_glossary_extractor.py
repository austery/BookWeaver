from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai.glossary_extractor import (
    _build_extraction_prompt,
    _looks_like_index_content,
    _validate_and_parse_glossary,
    extract_epub_index_and_toc,
    extract_glossary_from_epub,
)


def _wrap_xhtml(body: str) -> str:
    return (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<body>{body}</body></html>"
    )


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
