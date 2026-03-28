from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai.glossary_extractor import (
    _build_extraction_prompt,
    _validate_and_parse_glossary,
    extract_epub_index_and_toc,
    extract_glossary_from_epub,
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
    toc_xhtml = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<body><nav><ol><li>{toc_content}</li></ol></nav></body></html>"
    )
    idx_xhtml = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        f"<body><p>{index_content}</p></body></html>"
    )
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("META-INF/container.xml", container_xml)
        z.writestr("OEBPS/content.opf", opf_xml)
        z.writestr("OEBPS/toc.xhtml", toc_xhtml)
        z.writestr("OEBPS/index.xhtml", idx_xhtml)
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
