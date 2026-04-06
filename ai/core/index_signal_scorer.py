# ai/core/index_signal_scorer.py
"""Scored signal detection for EPUB index and glossary candidates.

Supports four variance classes:
1. Standards-compliant semantics (epub:type, role="doc-index", glossary semantics)
2. CSS/class-based faux index/glossary pages
3. Filename / ID-anchor clues (ix01.xhtml, index_term_102)
4. Visual-only formatting (line-shape patterns)

The scorer combines multiple weak signals into a confidence score, allowing
adaptive detection across diverse EPUB structures without hard-coding genre rules.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexSignalScore:
    """Result of scoring a document for index/glossary signals."""

    href: str
    total: int
    reasons: Sequence[str]


class IndexSignalScorer:
    """Score EPUB documents for index/glossary signals using multi-signal detection."""

    # Filename patterns: index.xhtml, glossary.xhtml, idx.xhtml, ix01.xhtml, ix99.xhtml
    _HREF_HINT_RE = re.compile(r"(?:^|/)(?:index|glossary|idx|ix\d+)", re.IGNORECASE)

    # Standards-compliant markup: epub:type="index", epub:type="glossary"
    _EPUB_TYPE_RE = re.compile(r'epub:type="(?:index|glossary)"', re.IGNORECASE)

    # O'Reilly and other data-type markers
    _DATA_TYPE_RE = re.compile(r'data-type="(?:index|glossary)"', re.IGNORECASE)

    # ARIA role for index navigation
    _ROLE_RE = re.compile(r'role="doc-index"', re.IGNORECASE)

    # CSS class hints: class="index", class="glossary", class="searchable-terms"
    _CLASS_RE = re.compile(
        r'class="[^"]*(?:index|glossary|idx|searchable-terms)[^"]*"', re.IGNORECASE
    )

    # Anchor/ID hints: id="index_term_102", id="glossary-entry"
    _ANCHOR_RE = re.compile(r'id="(?:index|glossary)[-_a-z0-9]*"', re.IGNORECASE)

    # Heading hints: <h2>Index</h2>, <h2>Glossary</h2>, <h2>Searchable Terms</h2>
    _HEADING_RE = re.compile(
        r"<h[1-6][^>]*>\s*(?:index|glossary|searchable terms|terminology)\s*</h[1-6]>",
        re.IGNORECASE,
    )

    # Line-shape pattern: "Adapter, 10-15, 42" or "Connascence, ♣"
    # Matches term + page markers (numbers, ranges, symbols)
    _LINE_SHAPE_RE = re.compile(
        r"[A-Za-z0-9].{1,160},\s*(?:\d{1,4}(?:[-–]\d{1,4})?|[♣♦•·*†‡§¶])(?:\s*,\s*(?:\d{1,4}(?:[-–]\d{1,4})?|[♣♦•·*†‡§¶]))*",
        re.IGNORECASE,
    )

    # Score weights for each signal type
    _SCORE_HREF_HINT = 25
    _SCORE_EPUB_TYPE = 40  # Strongest signal (standards-compliant)
    _SCORE_CSS_CLASS = 20
    _SCORE_ANCHOR_ID = 10
    _SCORE_HEADING = 10
    _SCORE_LINE_SHAPE = 20  # Visual pattern (weakest standalone)

    # Threshold for strong candidate (prevents visual-only false positives)
    _STRONG_CANDIDATE_THRESHOLD = 35

    def score_document(self, *, href: str, xhtml: str) -> IndexSignalScore:
        """Score a document for index/glossary signals.

        Args:
            href: Document href from EPUB manifest (e.g., "backmatter/index.xhtml")
            xhtml: Raw XHTML content of the document

        Returns:
            IndexSignalScore with total score and list of triggered signal reasons
        """
        score = 0
        reasons: list[str] = []
        lowered_href = href.lower()

        # Signal 1: Filename hints
        if self._HREF_HINT_RE.search(lowered_href):
            score += self._SCORE_HREF_HINT
            reasons.append("href_hint")

        # Signal 2: Standards-compliant markup (highest weight)
        if (
            self._EPUB_TYPE_RE.search(xhtml)
            or self._DATA_TYPE_RE.search(xhtml)
            or self._ROLE_RE.search(xhtml)
        ):
            score += self._SCORE_EPUB_TYPE
            reasons.append("epub_type")

        # Signal 3: CSS class hints
        if self._CLASS_RE.search(xhtml):
            score += self._SCORE_CSS_CLASS
            reasons.append("css_class")

        # Signal 4: Anchor/ID hints
        if self._ANCHOR_RE.search(xhtml):
            score += self._SCORE_ANCHOR_ID
            reasons.append("anchor_id")

        # Signal 5: Heading hints
        if self._HEADING_RE.search(xhtml):
            score += self._SCORE_HEADING
            reasons.append("heading")

        # Signal 6: Line-shape pattern (visual formatting)
        # Strip tags and normalize whitespace before pattern matching
        plain_text = " ".join(re.sub(r"<[^>]+>", " ", xhtml).split())
        if self._LINE_SHAPE_RE.search(plain_text):
            score += self._SCORE_LINE_SHAPE
            reasons.append("line_shape")

        return IndexSignalScore(href=href, total=score, reasons=tuple(reasons))

    @staticmethod
    def is_strong_candidate(score: IndexSignalScore) -> bool:
        """Return True if the score exceeds the strong candidate threshold.

        Visual-only formatting (line_shape alone = 20) stays below threshold (35),
        preventing false positives from bold lines without semantic signals.
        """
        return score.total >= IndexSignalScorer._STRONG_CANDIDATE_THRESHOLD
