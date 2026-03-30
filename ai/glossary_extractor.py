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

from ai.core.glossary import validate_model_output
from ai.epub_package import load_epub_package, resolve_opf_href


_INDEX_DOC_HINTS = ("index", "idx")

# Content-based heuristics for Kindle/generic EPUBs where the index file
# isn't named "index.xhtml" but starts with alphabetical navigation markers.
_INDEX_CONTENT_MARKERS = (
    "[ a ][ b ][ c ]",  # Kindle-style alpha nav bar
    "[ a ][ b ]",
)


def _looks_like_index_content(text: str) -> bool:
    """Return True if the plain-text content looks like a book index."""
    sample = text[:500].lower()
    return any(marker in sample for marker in _INDEX_CONTENT_MARKERS)


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

_FULL_INDEX_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。下面是一本书的Index（书后索引）和目录。

<INDEX>
{index_content}
</INDEX>

<TOC>
{toc_content}
</TOC>

任务：将Index中**所有顶级术语**翻译为中文，输出完整术语对照表。

规则：
1. 顶级条目（Index中非缩进的条目）= 必须全部翻译，一条不漏
2. 子条目（缩进的子项，如"  avoiding if statements"）= 跳过
3. 字母导航栏（如"[ A ][ B ][ C ]"）= 跳过
4. 页码引用（"2nd", "3rd" 等）= 忽略
5. 缩写/专有名词（如"AAA", "API", "SUT"）= term保留英文，suggested_translation填展开式译名
6. negative_constraint 仅在有易混淆错译时填写，否则省略此字段
7. priority: critical=本书核心概念, high=高频重要术语, medium=其他术语

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议中文翻译",
      "negative_constraint": "NOT 错误译法（可选）",
      "reason": "简短说明",
      "priority": "critical|high|medium"
    }}
  ]
}}
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


def _separate_mixed_index(text: str) -> tuple[str, str]:
    """Separate mixed English+Chinese index content into two parts.

    Detects lines that appear to be English terms followed by Chinese translations
    and returns (english_lines, chinese_lines) as separate texts.

    Example input:
        AAA (arrange, act, and assert) pattern
        arrange, act, and assert pattern.
        AAA（安排、执行和断言）模式
        安排、执行和断言模式。

    Returns:
        (english_text, chinese_text) — each is a block of lines
    """
    lines = text.split("\n")
    english_lines = []
    chinese_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Simple heuristic: if line has mostly CJK characters (>50% Chinese/Japanese/Korean)
        # it's likely Chinese translation
        cjk_count = sum(1 for c in stripped if ord(c) > 0x4E00)
        cjk_ratio = cjk_count / len(stripped) if stripped else 0

        if cjk_ratio > 0.3:  # >30% CJK chars → likely Chinese
            chinese_lines.append(line)
        else:
            english_lines.append(line)

    return "\n".join(english_lines), "\n".join(chinese_lines)


def extract_epub_index_and_toc(epub_path: Path) -> tuple[str, str]:
    """Extract plain text from Index and TOC documents inside the EPUB.

    Detection is two-stage:
    1. Filename hints ("index", "idx") — fast, works for standard EPUB naming.
    2. Content heuristics — scans the last 10 spine docs in reverse for
       alphabetical nav markers (e.g. Kindle format uses "[ A ][ B ][ C ]").

    Also handles mixed English+Chinese index content by separating them
    and preferring English for terminology extraction.

    Returns:
        (index_text, toc_text) — either may be empty string if not found.
    """
    model = load_epub_package(epub_path)
    index_text = ""
    toc_text = ""

    with zipfile.ZipFile(epub_path, "r") as zf:
        # Pass 1: filename-based detection + TOC
        for item_id, item in model.manifest_items.items():
            resolved_path = resolve_opf_href(model.opf_path, item.href)

            if _is_index_document(item.href) and not index_text:
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    extracted = _xhtml_to_text(raw)
                    # Separate mixed English+Chinese if needed
                    english_part, chinese_part = _separate_mixed_index(extracted)
                    # Use English part if available (more valuable for terminology)
                    index_text = english_part if english_part.strip() else extracted
                except (KeyError, UnicodeDecodeError):
                    pass

            if model.toc_item_id and item_id == model.toc_item_id and not toc_text:
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    extracted = _xhtml_to_text(raw)
                    # Same separation for TOC
                    english_part, chinese_part = _separate_mixed_index(extracted)
                    toc_text = english_part if english_part.strip() else extracted
                except (KeyError, UnicodeDecodeError):
                    pass

        # Pass 2: content-based fallback for Kindle/non-standard EPUBs
        if not index_text and model.spine_itemrefs:
            spine_tail = list(model.spine_itemrefs)[-10:]
            for idref in reversed(spine_tail):
                item = model.manifest_items.get(idref)
                if not item:
                    continue
                resolved_path = resolve_opf_href(model.opf_path, item.href)
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    candidate = _xhtml_to_text(raw)
                    if _looks_like_index_content(candidate):
                        # Separate mixed content here too
                        english_part, chinese_part = _separate_mixed_index(candidate)
                        index_text = english_part if english_part.strip() else candidate
                        break
                except (KeyError, UnicodeDecodeError):
                    pass

    return index_text, toc_text


def _build_extraction_prompt(
    index_text: str, toc_text: str, max_terms: int, full_index: bool = False
) -> str:
    """Format the extraction prompt with index and TOC content."""
    if full_index:
        return _FULL_INDEX_PROMPT_TEMPLATE.format(
            index_content=index_text or "(no index found)",
            toc_content=toc_text or "(no TOC found)",
        )
    return _EXTRACTION_PROMPT_TEMPLATE.format(
        index_content=index_text or "(no index found)",
        toc_content=toc_text or "(no TOC found)",
        max_terms=max_terms,
    )


def _validate_and_parse_glossary(raw_output: str) -> dict[str, object]:
    """Parse and validate model output as glossary JSON.

    Strips markdown code fences if present, then validates schema.

    Raises:
        ValueError: If JSON is invalid or missing 'critical_terminology' key.
    """
    return validate_model_output(raw_output)


def extract_glossary_from_epub(
    epub_path: Path,
    output_path: Path,
    translate_fn: Callable[[str], str],
    max_terms: int = 20,
    full_index: bool = False,
) -> dict[str, object]:
    """Extract terminology from EPUB and write glossary JSON to output_path.

    Args:
        epub_path: Source EPUB file.
        output_path: Where to write the extracted glossary JSON.
        translate_fn: Callable(prompt: str) -> str. Takes the extraction prompt
                      and returns the model's raw text response.
        max_terms: Maximum number of terms to extract (ignored when full_index=True).
        full_index: When True, translate ALL top-level index entries instead of
                    selecting the most critical ones. More comprehensive but produces
                    a larger glossary.

    Returns:
        The parsed glossary dict.
    """
    print(f"[glossary] Extracting from: {epub_path.name}", flush=True)
    mode = "full-index" if full_index else f"selective (max {max_terms})"
    print(f"[glossary] Mode: {mode}", flush=True)
    index_text, toc_text = extract_epub_index_and_toc(epub_path)
    print(
        f"[glossary] Index: {len(index_text)} chars, TOC: {len(toc_text)} chars",
        flush=True,
    )

    if not index_text and not toc_text:
        raise ValueError(
            "Cannot extract glossary: no Index or TOC content found in EPUB. "
            "The EPUB may not have a standard index or table of contents."
        )

    prompt = _build_extraction_prompt(index_text, toc_text, max_terms, full_index=full_index)
    raw_output = translate_fn(prompt)

    glossary = _validate_and_parse_glossary(raw_output)
    terms_count = len(glossary.get("critical_terminology", []))
    print(f"[glossary] Extracted {terms_count} terms", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] Written to: {output_path}", flush=True)

    return glossary
