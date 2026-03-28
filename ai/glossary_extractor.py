# ai/glossary_extractor.py
"""Extract critical terminology from an EPUB's Index and TOC documents.

Uses a model call (via translate_fn) to identify error-prone technical terms
and output them as a structured JSON glossary (Strategy A — minimal intervention).
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable

from ai.epub_package import load_epub_package, resolve_opf_href


_INDEX_DOC_HINTS = ("index", "idx")

_EXTRACTION_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。从以下EPUB的Index和目录中提取**容易翻译错误**的关键术语。

<INDEX>
{index_content}
</INDEX>

<TOC>
{toc_content}
</TOC>

提取要求：
1. 只提取专业术语和概念（不要人名、地名、机构名）
2. 优先识别"易混淆"的术语对（拼写相似但含义不同）
3. 标注作者原创的新概念（本书首次提出的术语）
4. 最多{max_terms}条术语（聚焦最关键的术语）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选，仅在有易混淆对时填写）",
      "reason": "为什么这个术语容易翻译错误",
      "priority": "critical"
    }}
  ]
}}

priority分级：critical（作者原创/核心概念）, high（高频技术术语）, medium（重要但非核心）
"""


def _is_index_document(document_path: str | None) -> bool:
    if not document_path:
        return False
    lowered = document_path.lower()
    return any(hint in lowered for hint in _INDEX_DOC_HINTS)


def _xhtml_to_text(xhtml: str) -> str:
    """Extract plain text from XHTML, stripping all tags."""
    try:
        root = ET.fromstring(xhtml)
        return " ".join(root.itertext()).strip()
    except ET.ParseError:
        return re.sub(r"<[^>]+>", " ", xhtml).strip()


def extract_epub_index_and_toc(epub_path: Path) -> tuple[str, str]:
    """Extract plain text from Index and TOC documents inside the EPUB.

    Returns:
        (index_text, toc_text) — either may be empty string if not found.
    """
    model = load_epub_package(epub_path)
    index_text = ""
    toc_text = ""

    with zipfile.ZipFile(epub_path, "r") as zf:
        for item_id, item in model.manifest_items.items():
            # Resolve the item path relative to the OPF file location
            resolved_path = resolve_opf_href(model.opf_path, item.href)

            if _is_index_document(item.href) and not index_text:
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    index_text = _xhtml_to_text(raw)
                except (KeyError, UnicodeDecodeError):
                    pass

            if model.toc_item_id and item_id == model.toc_item_id and not toc_text:
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    toc_text = _xhtml_to_text(raw)
                except (KeyError, UnicodeDecodeError):
                    pass

    return index_text, toc_text


def _build_extraction_prompt(index_text: str, toc_text: str, max_terms: int) -> str:
    """Format the extraction prompt with index and TOC content."""
    return _EXTRACTION_PROMPT_TEMPLATE.format(
        index_content=index_text or "(no index found)",
        toc_content=toc_text or "(no TOC found)",
        max_terms=max_terms,
    )


def _validate_and_parse_glossary(raw_output: str) -> dict:
    """Parse and validate model output as glossary JSON.

    Strips markdown code fences if present, then validates schema.

    Raises:
        ValueError: If JSON is invalid or missing 'critical_terminology' key.
    """
    cleaned = raw_output.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Model output is not valid JSON: {exc}\nRaw output:\n{raw_output[:200]}"
        ) from exc

    if "critical_terminology" not in data:
        raise ValueError(
            f"Model output missing 'critical_terminology' key. Got keys: {list(data.keys())}"
        )

    return data


def extract_glossary_from_epub(
    epub_path: Path,
    output_path: Path,
    translate_fn: Callable[[str], str],
    max_terms: int = 20,
) -> dict:
    """Extract terminology from EPUB and write glossary JSON to output_path.

    Args:
        epub_path: Source EPUB file.
        output_path: Where to write the extracted glossary JSON.
        translate_fn: Callable(prompt: str) -> str. Takes the extraction prompt
                      and returns the model's raw text response.
        max_terms: Maximum number of terms to extract (Strategy A default: 20).

    Returns:
        The parsed glossary dict.
    """
    print(f"[glossary] Extracting from: {epub_path.name}", flush=True)
    index_text, toc_text = extract_epub_index_and_toc(epub_path)
    print(
        f"[glossary] Index: {len(index_text)} chars, TOC: {len(toc_text)} chars",
        flush=True,
    )

    prompt = _build_extraction_prompt(index_text, toc_text, max_terms)
    raw_output = translate_fn(prompt)

    glossary = _validate_and_parse_glossary(raw_output)
    terms_count = len(glossary.get("critical_terminology", []))
    print(f"[glossary] Extracted {terms_count} terms", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] Written to: {output_path}", flush=True)

    return glossary
