"""Which glossary a run uses (ai/term_extraction.py), through its plan and the application."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.model_profiles import resolve_profile
from ai.orchestration import EpubTranslationOptions, GlossarySpec, ResumePolicy
from ai.orchestration import TranslationOrchestrator
from ai.term_extraction import GlossaryPlan, glossary_cache_path, plan_glossary
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_orchestration import make_indexed_epub


def _plan(
    tmp_path: Path,
    *,
    glossary_path: Path | None = None,
    requested_mode: str | None = None,
    extract: bool = False,
    max_terms: int | None = None,
    config: dict[str, object] | None = None,
    may_reuse: bool = True,
) -> GlossaryPlan:
    return plan_glossary(
        glossary_path=glossary_path,
        requested_mode=requested_mode,
        extract=extract,
        max_terms=max_terms,
        extraction_model=None,
        config=config if config is not None else {},
        translation_model=resolve_profile("flash"),
        book_dir=tmp_path,
        source_signature="sha256:abc",
        may_reuse=may_reuse,
    )


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


def test_a_supplied_glossary_wins_and_plans_no_extraction(tmp_path: Path) -> None:
    supplied = tmp_path / "g.json"

    plan = _plan(tmp_path, glossary_path=supplied, requested_mode="deep-scan", extract=True)

    assert (plan.path, plan.extraction) == (supplied, None)


@pytest.mark.parametrize(
    "requested,extract,config,expected",
    [
        ("deep-scan", True, {}, "deep-scan"),
        ("auto", False, {}, "auto"),
        (None, True, {}, "auto"),  # --extract-glossary or --extraction-model
        (None, False, {"terminology_extraction": {"enabled": True}}, "auto"),
    ],
)
def test_extraction_is_planned_by_request_or_configuration(
    tmp_path: Path,
    requested: str | None,
    extract: bool,
    config: dict[str, object],
    expected: str,
) -> None:
    plan = _plan(tmp_path, requested_mode=requested, extract=extract, config=config)

    assert plan.extraction is not None and plan.extraction.mode == expected
    assert plan.path == plan.extraction.cache_path


def test_nothing_requested_means_no_glossary(tmp_path: Path) -> None:
    plan = _plan(tmp_path)

    assert (plan.path, plan.extraction, plan.needs_extraction) == (None, None, False)


def test_a_non_positive_term_limit_fails_before_anything_else(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="glossary_max_terms must be positive"):
        _plan(tmp_path, glossary_path=Path("g.json"), max_terms=0)


def test_without_resume_a_run_extracts_terms_again(tmp_path: Path) -> None:
    """The reuse rule: a cached glossary is reused only when the run keeps a resume store."""
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    glossary = GlossarySpec(extract=True)
    factory = RecordingFactory()
    app = TranslationOrchestrator(provider_factory=factory)

    app.translate(
        source,
        tmp_path / "a.epub",
        EpubTranslationOptions(config={}, glossary=glossary),
        input_format="epub",
    )
    app.translate(
        source,
        tmp_path / "a.epub",
        EpubTranslationOptions(config={}, glossary=glossary),
        input_format="epub",
    )
    resumed = [r for r in factory.requests if r.protocol == "delimiter"]
    app.translate(
        source,
        tmp_path / "a.epub",
        EpubTranslationOptions(
            config={}, glossary=glossary, resume=ResumePolicy(False, False, None)
        ),
        input_format="epub",
    )

    assert len(resumed) == 1  # the resumed run reused the saved terms
    assert len([r for r in factory.requests if r.protocol == "delimiter"]) == 2
