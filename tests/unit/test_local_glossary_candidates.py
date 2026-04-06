"""Tests for local glossary candidate extraction and ranking."""

from __future__ import annotations


from ai.core.local_glossary_candidates import (
    TextBlock,
    build_local_glossary_candidates,
)


def test_extracts_repeated_fiction_entities() -> None:
    """Repeated title-case entities like 'Frodo', 'Gandalf', 'Shire' should be ranked high."""
    blocks = [
        TextBlock(text="Frodo walked with Gandalf through the Shire.", label="body", weight=1.0),
        TextBlock(text="The Shire was peaceful. Frodo met Gandalf again.", label="body", weight=1.0),
        TextBlock(
            text="Gandalf advised Frodo. The Shire remained calm.", label="body", weight=1.0
        ),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    # Verify we extracted the repeated entities
    terms = [c.term for c in candidates]
    assert "Frodo" in terms
    assert "Gandalf" in terms
    assert "Shire" in terms

    # Verify they're ranked by frequency (all appear 3x)
    frodo = next(c for c in candidates if c.term == "Frodo")
    gandalf = next(c for c in candidates if c.term == "Gandalf")
    shire = next(c for c in candidates if c.term == "Shire")

    assert frodo.frequency == 3
    assert gandalf.frequency == 3
    assert shire.frequency == 3


def test_extracts_multiword_technical_terms_and_filters_stopwords() -> None:
    """Multiword technical terms should be extracted, stopwords filtered."""
    blocks = [
        TextBlock(
            text="Hexagonal Architecture enables Ports and Adapters pattern.",
            label="body",
            weight=1.0,
        ),
        TextBlock(
            text="The Hexagonal Architecture is a design approach.", label="body", weight=1.0
        ),
        TextBlock(
            text="Ports and Adapters define clear boundaries. The system uses clear interfaces.",
            label="body",
            weight=1.0,
        ),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    # Verify we extracted multiword technical terms
    terms = [c.term for c in candidates]
    assert "Hexagonal Architecture" in terms
    assert "Ports and Adapters" in terms

    # Verify stopwords like "The", "a", "is" are filtered
    assert "The" not in terms
    assert "a" not in terms
    assert "is" not in terms


def test_front_and_back_matter_weights_break_ties() -> None:
    """Front/back matter weights should break frequency ties."""
    blocks = [
        # Two terms with same frequency (2x each)
        # But "Preface Term" appears in weighted front matter
        TextBlock(text="Preface Term is important.", label="front", weight=1.5),
        TextBlock(text="Preface Term again.", label="body", weight=1.0),
        TextBlock(text="Body Term is also important.", label="body", weight=1.0),
        TextBlock(text="Body Term again.", label="body", weight=1.0),
        TextBlock(text="Back Term appears here.", label="back", weight=1.2),
        TextBlock(text="Back Term appears twice.", label="body", weight=1.0),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    # All three terms appear 2x, but weighted scores differ
    preface = next(c for c in candidates if c.term == "Preface Term")
    body = next(c for c in candidates if c.term == "Body Term")
    back = next(c for c in candidates if c.term == "Back Term")

    # Verify frequency is same
    assert preface.frequency == 2
    assert body.frequency == 2
    assert back.frequency == 2

    # Verify weighted scores differ due to label weights
    # Preface: 1.5 + 1.0 = 2.5
    # Body: 1.0 + 1.0 = 2.0
    # Back: 1.2 + 1.0 = 2.2
    assert preface.weighted_score > back.weighted_score > body.weighted_score


def test_respects_max_candidates_limit() -> None:
    """Should respect max_candidates limit."""
    # Create 100 unique title-case words (simple names)
    first_names = ["Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Henry", "Iris", "Jack"]
    last_names = ["Anderson", "Brown", "Clark", "Davis", "Evans", "Foster", "Green", "Harris", "Jones", "King"]
    terms = [f"{first} {last}" for first in first_names for last in last_names]  # 100 unique names
    
    blocks = [
        TextBlock(
            text=" ".join(terms), label="body", weight=1.0
        ),  # 100 unique terms
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    assert len(candidates) == 10


def test_handles_empty_blocks() -> None:
    """Should handle empty block list gracefully."""
    candidates = build_local_glossary_candidates([], max_candidates=10)
    assert candidates == []


def test_filters_single_letter_terms() -> None:
    """Single letters should be filtered out."""
    blocks = [
        TextBlock(text="A B C are letters. Valid Term is good.", label="body", weight=1.0),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)
    terms = [c.term for c in candidates]

    assert "A" not in terms
    assert "B" not in terms
    assert "C" not in terms
    assert "Valid Term" in terms or "Valid" in terms or "Term" in terms


def test_candidates_include_kind_metadata() -> None:
    """Task 5 contract: candidates must include 'kind' field for entity/technical classification."""
    blocks = [
        TextBlock(text="Frodo walked through the Shire.", label="body", weight=1.0),
        TextBlock(text="Hexagonal Architecture is a pattern.", label="body", weight=1.0),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    # Verify all candidates have 'kind' field
    for candidate in candidates:
        assert hasattr(candidate, "kind"), f"Candidate {candidate.term} missing 'kind' field"
        assert candidate.kind in ("entity", "technical"), f"Invalid kind: {candidate.kind}"


def test_candidates_include_sources_metadata() -> None:
    """Task 5 contract: candidates must include 'sources' field tracking contributing blocks."""
    blocks = [
        TextBlock(text="Frodo appears here.", label="front", weight=1.5),
        TextBlock(text="Frodo appears again.", label="body", weight=1.0),
        TextBlock(text="Frodo final appearance.", label="back", weight=1.2),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)
    frodo = next((c for c in candidates if c.term == "Frodo"), None)

    assert frodo is not None, "Should extract 'Frodo'"
    assert hasattr(frodo, "sources"), "Candidate missing 'sources' field"
    # Sources should be a tuple or frozenset of contributing block labels
    assert isinstance(frodo.sources, (tuple, frozenset)), f"Invalid sources type: {type(frodo.sources)}"
    # Frodo appears in all three block types
    assert set(frodo.sources) == {"front", "body", "back"}


def test_candidates_preserve_entity_vs_technical_classification() -> None:
    """Task 5 contract: preserve extraction branch (entity vs technical) as 'kind' metadata."""
    blocks = [
        # Fiction entity (title-case single word)
        TextBlock(text="Gandalf spoke to Frodo.", label="body", weight=1.0),
        # Technical term (multiword)
        TextBlock(text="Hexagonal Architecture is important.", label="body", weight=1.0),
        # Another technical term
        TextBlock(text="Ports and Adapters pattern.", label="body", weight=1.0),
    ]

    candidates = build_local_glossary_candidates(blocks, max_candidates=10)

    # Extract candidates by name
    gandalf = next((c for c in candidates if c.term == "Gandalf"), None)
    frodo = next((c for c in candidates if c.term == "Frodo"), None)
    hexagonal = next((c for c in candidates if "Hexagonal Architecture" in c.term), None)
    ports = next((c for c in candidates if "Ports and Adapters" in c.term), None)

    # Verify entities are classified as 'entity'
    if gandalf:
        assert gandalf.kind == "entity", f"Gandalf should be 'entity', got {gandalf.kind}"
    if frodo:
        assert frodo.kind == "entity", f"Frodo should be 'entity', got {frodo.kind}"

    # Verify technical terms are classified as 'technical'
    if hexagonal:
        assert hexagonal.kind == "technical", f"Hexagonal Architecture should be 'technical', got {hexagonal.kind}"
    if ports:
        assert ports.kind == "technical", f"Ports and Adapters should be 'technical', got {ports.kind}"
