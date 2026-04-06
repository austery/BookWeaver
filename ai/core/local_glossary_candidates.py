"""Local glossary candidate extraction and ranking (Tier 2 building blocks).

Zero-dependency heuristics for extracting high-value terminology from EPUB spine blocks.
Surfaces repeated title-case entities (fiction) and multiword technical terms (non-fiction)
while filtering stopwords and noise.

This module provides the local ranking primitives for future Tier 2 integration.
It does NOT implement Tier 2 orchestration/prompting/deep-scan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextBlock:
    """A text block extracted from the EPUB spine with metadata."""

    text: str
    label: str  # "front", "body", "back"
    weight: float  # Weight bias for ranking (e.g., front=1.5, body=1.0, back=1.2)


@dataclass(frozen=True, slots=True)
class LocalGlossaryCandidate:
    """A candidate glossary term with ranking metadata."""

    term: str
    frequency: int  # Raw occurrence count
    weighted_score: float  # Frequency * average block weight


# Common English stopwords to filter from candidates
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}

# Regex patterns for term extraction
# Match title-case single words or phrases (handles "the Shire" by extracting "Shire")
_TITLE_CASE_WORD = re.compile(r"\b[A-Z][a-z]+\b")
_MULTIWORD_TECHNICAL = re.compile(
    r"\b[A-Z][a-z]+(?:\s+(?:and|or|of|the|a|an|for|in|on|at|to|with)\s+[A-Z][a-z]+)+\b"
)


def build_local_glossary_candidates(
    blocks: list[TextBlock], max_candidates: int = 300
) -> list[LocalGlossaryCandidate]:
    """Build ranked local glossary candidates from EPUB spine blocks.

    Args:
        blocks: Text blocks extracted from EPUB spine with labels and weights
        max_candidates: Maximum number of candidates to return (default: 300)

    Returns:
        Sorted list of candidates by weighted_score (descending), limited to max_candidates

    Extraction strategy:
        1. Extract title-case entities (e.g., "Frodo", "Gandalf", "Shire")
        2. Extract multiword technical terms (e.g., "Hexagonal Architecture", "Ports and Adapters")
        3. Filter single-letter terms and common stopwords
        4. Rank by weighted frequency (frequency * average block weight)
        5. Break ties using front/back matter weight bias
    """
    if not blocks:
        return []

    # Track term occurrences and their block weights
    term_weights: dict[str, list[float]] = {}

    for block in blocks:
        # Extract candidates from this block
        candidates = set()

        # Extract multiword technical terms first (they're more specific)
        for match in _MULTIWORD_TECHNICAL.finditer(block.text):
            term = match.group()
            if _is_valid_term(term):
                candidates.add(term)

        # Extract title-case words (single words or consecutive title-case words)
        # This extracts individual title-case words and consecutive sequences
        words = block.text.split()
        for i, word in enumerate(words):
            # Clean punctuation from word
            cleaned = word.strip('.,;:!?"()[]{}')
            
            # Check for title-case single word
            if _TITLE_CASE_WORD.fullmatch(cleaned):
                if _is_valid_term(cleaned):
                    candidates.add(cleaned)
                
                # Check for consecutive title-case words (e.g., "Ports and Adapters")
                # Look ahead for potential multi-word terms
                phrase_words = [cleaned]
                j = i + 1
                while j < len(words) and j <= i + 6:  # Max 6 words in a phrase
                    next_word = words[j].strip('.,;:!?"()[]{}')
                    if _TITLE_CASE_WORD.fullmatch(next_word):
                        phrase_words.append(next_word)
                        j += 1
                    elif next_word.lower() in {"and", "or", "of", "the", "a", "an", "for", "in", "on", "at", "to", "with"}:
                        phrase_words.append(next_word)
                        j += 1
                    else:
                        break
                
                # If we have a multi-word phrase, add it
                if len(phrase_words) > 1:
                    phrase = " ".join(phrase_words)
                    if _is_valid_term(phrase):
                        candidates.add(phrase)

        # Record weights for each candidate in this block
        for term in candidates:
            if term not in term_weights:
                term_weights[term] = []
            term_weights[term].append(block.weight)

    # Build candidates with frequency and weighted score
    candidates_list = []
    for term, weights in term_weights.items():
        frequency = len(weights)
        weighted_score = sum(weights)
        candidates_list.append(
            LocalGlossaryCandidate(term=term, frequency=frequency, weighted_score=weighted_score)
        )

    # Sort by weighted_score descending, then by term alphabetically for stability
    candidates_list.sort(key=lambda c: (-c.weighted_score, c.term))

    return candidates_list[:max_candidates]


def _is_valid_term(term: str) -> bool:
    """Check if a term is valid for glossary extraction.

    Filters:
        - Single letters (A, B, C)
        - Common stopwords (the, a, an, etc.)
        - Terms that are only stopwords when split
    """
    # Filter single letters
    if len(term) == 1:
        return False

    # Filter pure stopwords
    normalized = term.lower()
    if normalized in _STOPWORDS:
        return False

    # Filter terms that are only stopwords when split
    words = term.split()
    if all(word.lower() in _STOPWORDS for word in words):
        return False

    return True
