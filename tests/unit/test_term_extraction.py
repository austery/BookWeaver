"""Glossary choice for a run (ai/term_extraction.py): precedence, cache identity, reuse."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.model_profiles import resolve_profile
from ai.term_extraction import glossary_cache_path, glossary_mode, plan_glossary


@pytest.mark.parametrize(
    "path,requested,extract,expected",
    [
        (Path("g.json"), "deep-scan", True, "manual"),  # a supplied file wins
        (None, "deep-scan", True, "deep-scan"),
        (None, "auto", False, "auto"),
        (None, None, True, "auto"),  # --extract-glossary or configuration
        (None, None, False, "none"),
    ],
)
def test_glossary_mode_precedence(
    path: Path | None, requested: str | None, extract: bool, expected: str
) -> None:
    assert glossary_mode(glossary_path=path, requested_mode=requested, extract=extract) == expected


def test_the_cache_file_name_is_pinned() -> None:
    """Saved books find their glossary by this name; computed with the code before this module."""
    path = glossary_cache_path(
        Path("/books/x"),
        source_signature="sha256:abc",
        mode="auto",
        max_terms=20,
        model_id="gemini-4-argon-low",
        effort=None,
    )
    assert path == Path(
        "/books/x/.bookweaver_glossaries/"
        "bb4470653abac7843f366c39ed6dffea80d8536dea55e6c4f9e678424af669bc.json"
    )


def test_a_cached_glossary_is_reused_only_with_a_resume_store(tmp_path: Path) -> None:
    model = resolve_profile("flash")

    def plan(may_reuse: bool):  # noqa: ANN202
        return plan_glossary(
            glossary_path=None,
            requested_mode=None,
            extract=True,
            max_terms=None,
            extraction_model=None,
            config={},
            translation_model=model,
            book_dir=tmp_path,
            source_signature="sha256:abc",
            may_reuse=may_reuse,
        )

    first = plan(True)
    assert first.needs_extraction and first.extraction is not None
    first.extraction.cache_path.parent.mkdir(parents=True)
    first.extraction.cache_path.write_text("{}", encoding="utf-8")

    assert not plan(True).needs_extraction
    assert plan(False).needs_extraction  # without resume, extraction always runs again


def test_no_glossary_and_a_supplied_glossary_plan_no_extraction(tmp_path: Path) -> None:
    model = resolve_profile("flash")
    common = {
        "max_terms": None,
        "extraction_model": None,
        "config": {},
        "translation_model": model,
        "book_dir": tmp_path,
        "source_signature": None,
        "may_reuse": True,
    }

    none = plan_glossary(glossary_path=None, requested_mode=None, extract=False, **common)
    manual = plan_glossary(
        glossary_path=tmp_path / "g.json", requested_mode="auto", extract=True, **common
    )

    assert (none.path, none.extraction) == (None, None)
    assert (manual.path, manual.extraction) == (tmp_path / "g.json", None)


def test_a_non_positive_term_limit_fails_before_anything_else(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="glossary_max_terms must be positive"):
        plan_glossary(
            glossary_path=Path("g.json"),
            requested_mode=None,
            extract=False,
            max_terms=0,
            extraction_model=None,
            config={},
            translation_model=resolve_profile("flash"),
            book_dir=tmp_path,
            source_signature=None,
            may_reuse=True,
        )
