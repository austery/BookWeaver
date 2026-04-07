"""Local glossary candidate extraction (FUTURE ARCHITECTURE — not used in current pipeline).

This module provides zero-dependency heuristics for extracting high-value terminology
from EPUB spine text using title-case entity detection and multiword phrase matching.

Status: Retained for future integration with NLP-based Tier 2 (e.g., spaCy NER,
TF-IDF). The current pipeline uses Tier 1 (index detection) → Tier 3 (whole-book
AI scan) without this module.

Limitation of current approach: ~90% of "entity" candidates are sentence-initial
capitalized words (false positives). Completely misses lowercase scientific terms
(mRNA, pseudouridine, in vitro). Suitable for future upgrade with proper NLP libs.

If you want to re-introduce a lightweight local pre-filter layer between Tier 1 and
Tier 3, this is the starting point. Pair with scikit-learn TfidfVectorizer or spaCy
en_core_web_sm for improved recall on scientific/fiction terminology.
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
    kind: str  # "entity" (title-case single/phrase) or "technical" (multiword)
    sources: tuple[str, ...]  # Contributing block labels ("front", "body", "back")


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

    # Track term occurrences, weights, kind, and source labels
    term_data: dict[str, dict[str, any]] = {}

    for block in blocks:
        # Extract candidates from this block with their kind
        technical_candidates = set()
        entity_candidates = set()

        # Extract multiword technical terms first (they're more specific)
        for match in _MULTIWORD_TECHNICAL.finditer(block.text):
            term = match.group()
            if _is_valid_term(term):
                technical_candidates.add(term)

        # Extract title-case words (single words or consecutive title-case words)
        # Single title-case words are entities (fiction names)
        # Consecutive title-case words are technical terms (e.g., "Hexagonal Architecture")
        words = block.text.split()
        for i, word in enumerate(words):
            # Clean punctuation from word
            cleaned = word.strip('.,;:!?"()[]{}')

            # Check for title-case single word
            if _TITLE_CASE_WORD.fullmatch(cleaned):
                if _is_valid_term(cleaned):
                    # Check for consecutive title-case words (e.g., "Hexagonal Architecture")
                    # Look ahead for potential multi-word terms
                    phrase_words = [cleaned]
                    j = i + 1
                    while j < len(words) and j <= i + 6:  # Max 6 words in a phrase
                        next_word = words[j].strip('.,;:!?"()[]{}')
                        if (
                            _TITLE_CASE_WORD.fullmatch(next_word)
                            and next_word.lower() not in _STOPWORDS
                        ):
                            # Title-case non-stopword: add it
                            phrase_words.append(next_word)
                            j += 1
                        elif (
                            next_word.lower()
                            in {
                                "and",
                                "or",
                                "of",
                                "the",
                                "a",
                                "an",
                                "for",
                                "in",
                                "on",
                                "at",
                                "to",
                                "with",
                            }
                            and next_word[0].islower()
                        ):
                            # Lowercase connector word: peek ahead to verify a title-case word follows
                            # This prevents ghost terms like "Ports and" or "History of"
                            if j + 1 < len(words):
                                peek_word = words[j + 1].strip('.,;:!?"()[]{}')
                                if (
                                    _TITLE_CASE_WORD.fullmatch(peek_word)
                                    and peek_word.lower() not in _STOPWORDS
                                ):
                                    # Valid connector with title-case word following: include it
                                    phrase_words.append(next_word)
                                    j += 1
                                else:
                                    # No valid title-case word follows: stop here
                                    break
                            else:
                                # Connector at end of text: stop here
                                break
                        else:
                            break

                    # If we have a multi-word phrase, it's a technical term
                    if len(phrase_words) > 1:
                        phrase = " ".join(phrase_words)
                        if _is_valid_term(phrase):
                            technical_candidates.add(phrase)
                    else:
                        # Single word is an entity
                        entity_candidates.add(cleaned)

        # Record weights, kind, and sources for technical candidates (takes precedence)
        for term in technical_candidates:
            if term not in term_data:
                term_data[term] = {"weights": [], "kind": "technical", "sources": set()}
            # Always keep technical kind even if it was previously entity
            elif term_data[term]["kind"] != "technical":
                term_data[term]["kind"] = "technical"
            term_data[term]["weights"].append(block.weight)
            term_data[term]["sources"].add(block.label)

        # Record weights, kind, and sources for entity candidates (only if not already technical)
        for term in entity_candidates:
            if term not in term_data:
                term_data[term] = {"weights": [], "kind": "entity", "sources": set()}
                term_data[term]["weights"].append(block.weight)
                term_data[term]["sources"].add(block.label)
            elif (
                term not in technical_candidates
            ):  # Don't duplicate if already recorded as technical
                term_data[term]["weights"].append(block.weight)
                term_data[term]["sources"].add(block.label)

    # Build candidates with frequency, weighted score, kind, and sources
    candidates_list = []
    for term, data in term_data.items():
        frequency = len(data["weights"])
        weighted_score = sum(data["weights"])
        kind = data["kind"]
        # Sort sources for deterministic ordering
        sources = tuple(sorted(data["sources"]))
        candidates_list.append(
            LocalGlossaryCandidate(
                term=term,
                frequency=frequency,
                weighted_score=weighted_score,
                kind=kind,
                sources=sources,
            )
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
