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
from ai.core.index_signal_scorer import IndexSignalScore, IndexSignalScorer
from ai.core.local_glossary_candidates import (
    TextBlock,
    build_local_glossary_candidates,
)
from ai.epub_package import load_epub_package, resolve_opf_href


_INDEX_DOC_HINTS = ("index", "idx", "glossary")

# Content-based heuristics for Kindle/generic EPUBs where the index file
# isn't named "index.xhtml" but starts with alphabetical navigation markers.
_INDEX_CONTENT_MARKERS = (
    "[ a ][ b ][ c ]",  # Kindle-style alpha nav bar
    "[ a ][ b ]",
)

_INDEX_HEADING_HINTS = ("index", "glossary", "searchable terms", "terminology")
_INDEX_LINE_TAGS = {"h1", "h2", "h3", "p", "li", "dd", "dt"}
_INDEX_PAGE_TOKEN_RE = re.compile(r"(?:\d{1,4}(?:[-–]\d{1,4})?|[♣♦•·*†‡§¶])$")
_INDEX_LIKE_LINE_RE = re.compile(
    r"^[A-Za-z0-9].{1,160},\s*(?:\d{1,4}(?:[-–]\d{1,4})?|[♣♦•·*†‡§¶])(?:\s*,\s*(?:\d{1,4}(?:[-–]\d{1,4})?|[♣♦•·*†‡§¶]))*$"
)
_TOC_FILENAME_HINT_RE = re.compile(r"(?<![a-z0-9])(?:toc|contents)(?![a-z0-9])", re.IGNORECASE)


def _looks_like_index_content(text: str) -> bool:
    """Return True if the plain-text content looks like a book index."""
    sample = text[:500].lower()
    return any(marker in sample for marker in _INDEX_CONTENT_MARKERS)


def _is_placeholder_index_text(text: str) -> bool:
    """Return True for known placeholder/conversion boilerplate index pages."""
    normalized = " ".join(text.split()).strip().lower()
    if not normalized:
        return True
    return normalized in {"converted ebook", "converted ebook dead simple python"}


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _extract_candidate_lines(xhtml: str) -> list[str]:
    """Extract candidate text lines from common index-like block tags."""
    try:
        root = ET.fromstring(xhtml)
    except ET.ParseError:
        stripped = re.sub(r"<[^>]+>", "\n", xhtml)
        return [line.strip() for line in stripped.splitlines() if line.strip()]

    lines: list[str] = []
    for node in root.iter():
        tag = _local_name(node.tag).lower()
        if tag not in _INDEX_LINE_TAGS:
            continue
        line = " ".join("".join(node.itertext()).split()).strip()
        if line:
            lines.append(line)

    return lines


def _is_index_like_line(line: str) -> bool:
    """Return True when line resembles an index entry with page markers."""
    normalized = " ".join(line.split()).strip()
    if len(normalized) < 4 or len(normalized) > 180:
        return False
    if len(normalized.split()) > 16:
        return False
    if not _INDEX_LIKE_LINE_RE.match(normalized):
        return False

    tail = normalized.rsplit(",", 1)[-1].strip()
    return _INDEX_PAGE_TOKEN_RE.match(tail) is not None


def _looks_like_index_by_line_pattern(xhtml: str) -> bool:
    """Pass-3 heuristic for non-standard index documents."""
    lines = _extract_candidate_lines(xhtml)
    if len(lines) < 3:
        return False

    normalized_lines = [" ".join(line.split()).strip() for line in lines if line.strip()]
    if len(normalized_lines) < 3:
        return False

    heading_hint = any(
        any(hint in line.lower() for hint in _INDEX_HEADING_HINTS) for line in normalized_lines[:3]
    )
    index_like_lines = sum(1 for line in normalized_lines if _is_index_like_line(line))
    ratio = index_like_lines / len(normalized_lines)

    min_ratio = 0.45 if heading_hint else 0.6
    min_lines = 3 if heading_hint else 4
    return index_like_lines >= min_lines and ratio >= min_ratio


_EXTRACTION_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。从以下EPUB的Index和目录中提取**容易翻译错误**的关键术语。

<INDEX>
{index_content}
</INDEX>

<TOC>
{toc_content}
</TOC>

提取要求：
1. 优先选择专业术语、科学概念、作者原创新词
2. 包含重要人名、机构名、地名（如对翻译一致性有影响）
3. 优先识别"易混淆"的术语对（拼写相似但含义不同）
4. 标注作者原创的新概念（本书首次提出的术语）
5. 最多{max_terms}条术语（聚焦最关键的术语）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选，仅在有易混淆对时填写）",
      "reason": "为什么这个术语容易翻译错误或需要统一翻译",
      "priority": "critical"
    }}
  ]
}}

priority分级：critical（作者原创/核心概念）, high（高频技术术语）, medium（重要但非核心）
"""

_LOCAL_REFINEMENT_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。以下是一本书的元数据和高频术语候选列表。

<BOOK_CONTEXT>
标题: {book_title}
总文档数: {doc_count}
总字符数: {char_count}
</BOOK_CONTEXT>

<SHORTLIST>
以下是从全书正文中自动识别的高频术语候选（已按重要性排序）：

{candidate_list}
</SHORTLIST>

任务：从上述候选中精炼出最容易翻译错误或需要统一翻译的**关键词汇**（最多{max_terms}条）。

提取要求：
1. 优先选择技术概念、专有名词、作者原创术语
2. 包含重要人名、机构名、地名（如对翻译一致性有影响）
3. 标注易混淆的术语对
4. 按重要性分级：critical（核心概念）, high（高频术语）, medium（次要）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选）",
      "reason": "为什么这个术语容易翻译错误或需要统一翻译",
      "priority": "critical|high|medium"
    }}
  ]
}}
"""

_DEEP_SCAN_PROMPT_TEMPLATE = """\
你是技术书籍翻译专家。以下是一本书的完整正文内容（整本书 / whole-book）。

<BOOK_CONTEXT>
标题: {book_title}
总文档数: {doc_count}
总字符数: {char_count}
</BOOK_CONTEXT>

<WHOLE_BOOK>
{full_text}
</WHOLE_BOOK>

任务：通读整本书，提取**所有容易翻译错误**的关键术语（最多{max_terms}条）。

提取要求：
1. 优先选择专业术语、科学概念、作者原创新词
2. 包含重要人名、机构名、地名（如对翻译一致性有影响）
3. 优先识别"易混淆"的术语对（拼写相似但含义不同）
4. 标注作者原创的新概念（本书首次提出的术语）
5. 按重要性分级：critical（核心概念）, high（高频术语）, medium（次要）

严格输出以下JSON格式，不要包含任何其他文字：
{{
  "critical_terminology": [
    {{
      "term": "原文术语",
      "suggested_translation": "建议的中文翻译",
      "negative_constraint": "NOT 容易混淆的错误翻译（可选）",
      "reason": "为什么这个术语容易翻译错误或需要统一翻译",
      "priority": "critical|high|medium"
    }}
  ]
}}
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


def _select_scored_index_text(epub_path: Path) -> str:
    """Select index/glossary text using signal-based scoring.

    Scans all spine documents and scores them for index/glossary signals
    (epub:type, CSS classes, filename hints, heading markers, line patterns).
    Returns text from the strongest candidate (highest score), not the first strong.

    This is the Tier 1 detector that handles non-standard EPUB structures
    (e.g., epub:type="glossary", ix01.xhtml, class="index").

    Returns:
        Extracted index text from the highest-scoring document, or empty string.
    """
    scorer = IndexSignalScorer()
    model = load_epub_package(epub_path)

    best_score: IndexSignalScore | None = None
    best_text = ""

    with zipfile.ZipFile(epub_path, "r") as zf:
        for idref in model.spine_itemrefs:
            item = model.manifest_items.get(idref)
            if item is None:
                continue

            resolved_path = resolve_opf_href(model.opf_path, item.href)
            try:
                raw = zf.read(resolved_path).decode("utf-8")
            except (KeyError, UnicodeDecodeError):
                continue

            score = scorer.score_document(href=item.href, xhtml=raw)
            if not scorer.is_strong_candidate(score):
                continue

            extracted = _xhtml_to_text(raw)
            if _is_placeholder_index_text(extracted):
                continue

            # Keep the candidate with the highest score
            if best_score is None or score.total > best_score.total:
                best_score = score
                # Separate mixed English+Chinese if needed
                english_part, _ = _separate_mixed_index(extracted)
                best_text = english_part if english_part.strip() else extracted

    return best_text


def extract_epub_index_and_toc(epub_path: Path) -> tuple[str, str]:
    """Extract plain text from Index and TOC documents inside the EPUB.

    Detection is four-stage (Tier 1):
    0. Signal-scored detection — scans all spine docs for strong index/glossary
       signals (epub:type, CSS classes, filename hints, heading markers).
       Handles non-standard structures (ix01.xhtml, class="glossary", etc.).
    1. Filename hints ("index", "idx") — fast, works for standard EPUB naming.
    2. Content heuristics — scans the last 10 spine docs in reverse for
       alphabetical nav markers (e.g. Kindle format uses "[ A ][ B ][ C ]").
    3. Line-pattern heuristics — scans tail spine docs for index-like entry lines
       with page-marker tokens and heading hints ("Index", "Searchable Terms").

    Also handles mixed English+Chinese index content by separating them
    and preferring English for terminology extraction.

    Returns:
        (index_text, toc_text) — either may be empty string if not found.
    """
    model = load_epub_package(epub_path)
    index_text = ""
    toc_text = ""

    # Pass 0: Signal-scored detection (Tier 1 enhancement)
    # Checks ALL spine docs for strong index/glossary signals before fallback passes
    index_text = _select_scored_index_text(epub_path)

    with zipfile.ZipFile(epub_path, "r") as zf:
        # Pass 1: filename-based detection + TOC
        weak_index_candidate = ""
        for item_id, item in model.manifest_items.items():
            resolved_path = resolve_opf_href(model.opf_path, item.href)

            if _is_index_document(item.href) and not index_text:
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    extracted = _xhtml_to_text(raw)
                    if _is_placeholder_index_text(extracted):
                        continue
                    if _looks_like_index_content(extracted) or _looks_like_index_by_line_pattern(
                        raw
                    ):
                        english_part, chinese_part = _separate_mixed_index(extracted)
                        index_text = english_part if english_part.strip() else extracted
                        continue
                    if not weak_index_candidate:
                        weak_index_candidate = extracted
                        continue
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
        if not index_text and weak_index_candidate:
            english_part, chinese_part = _separate_mixed_index(weak_index_candidate)
            index_text = english_part if english_part.strip() else weak_index_candidate

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

        # Pass 3: content-pattern fallback for non-standard index docs
        if not index_text and model.spine_itemrefs:
            spine_tail = list(model.spine_itemrefs)[-10:]
            for idref in reversed(spine_tail):
                item = model.manifest_items.get(idref)
                if not item:
                    continue
                resolved_path = resolve_opf_href(model.opf_path, item.href)
                try:
                    raw = zf.read(resolved_path).decode("utf-8")
                    if _looks_like_index_by_line_pattern(raw):
                        extracted = _xhtml_to_text(raw)
                        english_part, chinese_part = _separate_mixed_index(extracted)
                        index_text = english_part if english_part.strip() else extracted
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
    max_terms: int = 50,
    full_index: bool = False,
    mode: str = "auto",
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
        mode: Extraction mode - "auto" (Tier 1 with Tier 2 fallback), "deep-scan" (Tier 3), or legacy.

    Returns:
        A report dict with keys: tier, docs, chars, candidate_count, term_count, skip_reason (optional).
    """
    print(f"[glossary] Extracting from: {epub_path.name}", flush=True)
    display_mode = "full-index" if full_index else mode
    print(f"[glossary] Mode: {display_mode} (max {max_terms} terms)", flush=True)

    # Tier 1: Try index/TOC extraction for auto mode
    if mode == "auto":
        index_text, toc_text = extract_epub_index_and_toc(epub_path)
        print(
            f"[glossary] Index: {len(index_text)} chars, TOC: {len(toc_text)} chars",
            flush=True,
        )

        # Check if we have strong index signals (not just TOC)
        has_strong_index = len(index_text) > 100  # Minimum threshold for meaningful index

        if has_strong_index:
            # Tier 1: Use index-based extraction
            print("[glossary] Using Tier 1 (index-based extraction)", flush=True)
            prompt = _build_extraction_prompt(
                index_text, toc_text, max_terms, full_index=full_index
            )
            raw_output = translate_fn(prompt)
            glossary = _validate_and_parse_glossary(raw_output)

            # Trim to max_terms if needed
            terms = glossary.get("critical_terminology", [])
            if len(terms) > max_terms:
                glossary["critical_terminology"] = terms[:max_terms]

            terms_count = len(glossary.get("critical_terminology", []))
            print(f"[glossary] Extracted {terms_count} terms (Tier 1)", flush=True)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"[glossary] Written to: {output_path}", flush=True)

            return {
                "tier": "index",
                "docs": 0,
                "chars": len(index_text) + len(toc_text),
                "candidate_count": 0,
                "term_count": terms_count,
            }

        # Tier 2 fallback: Local refinement when no strong index signals
        print(
            "[glossary] No strong index signals, falling back to Tier 2 (local refinement)",
            flush=True,
        )

    # Tier 2: Local refinement (auto fallback or explicit)
    if mode == "auto":
        blocks = _collect_spine_blocks(epub_path)
        if not blocks:
            raise ValueError("Cannot extract glossary: EPUB has no readable content blocks.")

        # Build local glossary candidates
        candidates = build_local_glossary_candidates(blocks, max_candidates=300)
        print(f"[glossary] Built {len(candidates)} local candidates", flush=True)

        # Format candidate list for prompt — send at least 3× max_terms so the model has
        # enough material to fill the requested quota, capped at 300 (the full build budget).
        prompt_candidate_limit = min(max(max_terms * 3, 50), len(candidates))
        candidate_lines = []
        for i, cand in enumerate(candidates[:prompt_candidate_limit], 1):
            sources_str = ", ".join(sorted(set(cand.sources)))
            candidate_lines.append(
                f"{i}. {cand.term} — {cand.kind} | score: {cand.weighted_score:.1f} | sources: {sources_str}"
            )
        candidate_list_text = "\n".join(candidate_lines)

        # Calculate book context stats
        total_chars = sum(len(block.text) for block in blocks)
        doc_count = len(blocks)

        # Build local refinement prompt
        book_title = "Unknown"  # We can extract from OPF metadata if needed

        prompt = _LOCAL_REFINEMENT_PROMPT_TEMPLATE.format(
            book_title=book_title,
            doc_count=doc_count,
            char_count=total_chars,
            candidate_list=candidate_list_text,
            max_terms=max_terms,
        )

        raw_output = translate_fn(prompt)
        glossary = _validate_and_parse_glossary(raw_output)

        # Trim to max_terms if needed
        terms = glossary.get("critical_terminology", [])
        if len(terms) > max_terms:
            glossary["critical_terminology"] = terms[:max_terms]

        terms_count = len(glossary.get("critical_terminology", []))
        print(f"[glossary] Extracted {terms_count} terms (Tier 2)", flush=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[glossary] Written to: {output_path}", flush=True)

        return {
            "tier": "local-refinement",
            "docs": doc_count,
            "chars": total_chars,
            "candidate_count": len(candidates),
            "term_count": terms_count,
        }

    # Tier 3: Deep-scan (whole-book extraction)
    if mode == "deep-scan":
        print("[glossary] Using Tier 3 (deep-scan whole-book extraction)", flush=True)
        blocks = _collect_spine_blocks(epub_path)
        if not blocks:
            raise ValueError("Cannot extract glossary: EPUB has no readable content blocks.")

        # Collect full text
        full_text_parts = [block.text for block in blocks]
        full_text = "\n\n".join(full_text_parts)
        total_chars = len(full_text)
        doc_count = len(blocks)

        print(f"[glossary] Payload: docs={doc_count}, chars={total_chars}", flush=True)

        # Build deep-scan prompt
        book_title = "Unknown"

        prompt = _DEEP_SCAN_PROMPT_TEMPLATE.format(
            book_title=book_title,
            doc_count=doc_count,
            char_count=total_chars,
            full_text=full_text,
            max_terms=max_terms,
        )

        raw_output = translate_fn(prompt)
        glossary = _validate_and_parse_glossary(raw_output)

        # Trim to max_terms if needed
        terms = glossary.get("critical_terminology", [])
        if len(terms) > max_terms:
            glossary["critical_terminology"] = terms[:max_terms]

        terms_count = len(glossary.get("critical_terminology", []))
        print(f"[glossary] Extracted {terms_count} terms (Tier 3)", flush=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[glossary] Written to: {output_path}", flush=True)

        return {
            "tier": "deep-scan",
            "docs": doc_count,
            "chars": total_chars,
            "candidate_count": 0,
            "term_count": terms_count,
        }

    # Legacy path (backward compatibility when mode is not specified or old behavior)
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

    # Trim to max_terms if needed
    terms = glossary.get("critical_terminology", [])
    if len(terms) > max_terms:
        glossary["critical_terminology"] = terms[:max_terms]

    terms_count = len(glossary.get("critical_terminology", []))
    print(f"[glossary] Extracted {terms_count} terms", flush=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] Written to: {output_path}", flush=True)

    return {
        "tier": "legacy",
        "docs": 0,
        "chars": len(index_text) + len(toc_text),
        "candidate_count": 0,
        "term_count": terms_count,
    }


def _looks_like_toc_href(href: str) -> bool:
    """Return True when the basename stem looks like a TOC/navigation filename."""
    return bool(_TOC_FILENAME_HINT_RE.search(Path(href).stem))


def _collect_spine_blocks(epub_path: Path) -> list[TextBlock]:
    """Collect text blocks from EPUB spine with labels and weights for local candidate ranking.

    Skips TOC/navigation boilerplate and retains front/body/back matter with appropriate
    weight bias for tie-breaking in candidate ranking.

    Args:
        epub_path: Path to the EPUB file

    Returns:
        List of TextBlock instances with text, label, and weight metadata

    Block labeling strategy:
        - "front": First ~10% of spine (preface, foreword, etc.) — weight 1.5
        - "back": Last ~10% of spine (appendix, index, etc.) — weight 1.2
        - "body": Middle ~80% of spine (main chapters) — weight 1.0

    Filtering:
        - Skips TOC documents (identified by filename hints: "toc", "contents")
        - Skips nav document declared via spine@toc (model.toc_item_id)
        - Skips empty or whitespace-only blocks
    """
    model = load_epub_package(epub_path)
    blocks: list[TextBlock] = []

    # Filter out TOC (both by filename hints and by spine@toc declaration)
    content_items = [
        (idx, idref)
        for idx, idref in enumerate(model.spine_itemrefs)
        if idref in model.manifest_items
        and idref != model.toc_item_id  # Skip nav/toc declared via spine@toc
        and not _looks_like_toc_href(model.manifest_items[idref].href)
    ]

    if not content_items:
        return blocks

    total_content_items = len(content_items)

    # Define front/back matter thresholds (10% on each end, min 1 item)
    # For small EPUBs (< 10 items), only mark first and last items
    front_threshold = max(1, total_content_items // 10)
    back_start = total_content_items - max(1, total_content_items // 10)

    with zipfile.ZipFile(epub_path, "r") as zf:
        for content_idx, (_, idref) in enumerate(content_items):
            item = model.manifest_items[idref]

            # Determine label and weight based on position in content spine
            if content_idx < front_threshold:
                label = "front"
                weight = 1.5
            elif content_idx >= back_start:
                label = "back"
                weight = 1.2
            else:
                label = "body"
                weight = 1.0

            # Extract text from document
            resolved_path = resolve_opf_href(model.opf_path, item.href)
            try:
                raw = zf.read(resolved_path).decode("utf-8")
                text = _xhtml_to_text(raw)

                # Skip empty or whitespace-only blocks
                if not text or not text.strip():
                    continue

                blocks.append(TextBlock(text=text, label=label, weight=weight))

            except (KeyError, UnicodeDecodeError):
                continue

    return blocks
