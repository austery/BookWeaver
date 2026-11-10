"""Which glossary a translation run uses, and which model extracts it.

One place for the glossary decision that used to be spread over the translation method, the
prompt module and a request helper. Done before SPEC-028 Phase 2b, so the Term Panel can become
one more source behind the same plan. It works in two steps so the
caller can record the extraction model for the audit before it constructs the extractor:

1. ``plan_glossary`` decides, with no model call: no glossary, the user's file, a cached
   extraction, or a new extraction (which model, which term limit, which cache file).
2. ``extract_glossary`` runs a planned extraction with a provider the caller constructed.

Rules kept exactly as before this module existed:

- The cache key and file name (``glossary_cache_path``) are unchanged; they feed the prompt hash.
- A cached glossary is reused only when the run keeps a resume store. A run without resume
  extracts again and overwrites the cached file, so a later resume of an older checkpoint made
  with other terms can stop on a prompt mismatch.
- ``auto`` stops before any model call when the book has no usable index (ADR-0005).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai.glossary_extractor import extract_glossary_from_epub
from ai.model_profiles import resolve_profile
from ai.ports.model import ResolvedModel
from ai.ports.provider import ITranslationProvider

GlossaryMode = Literal["none", "manual", "auto", "deep-scan"]
ExtractionMode = Literal["auto", "deep-scan"]
DEFAULT_TERM_LIMIT = 20


def _glossary_mode(
    *, glossary_path: Path | None, requested_mode: str | None, extract: bool
) -> GlossaryMode:
    """Precedence: a supplied file, then Deep Scan, then ``auto`` (by flag or request)."""
    if glossary_path is not None:
        return "manual"
    if requested_mode == "deep-scan":
        return "deep-scan"
    if requested_mode == "auto" or extract:
        return "auto"
    return "none"


def configured_term_limit(config: dict[str, object]) -> object:
    """``terminology_extraction.max_terms``, default 20; the caller checks the type."""
    extraction = config.get("terminology_extraction", {})
    if isinstance(extraction, dict):
        return extraction.get("max_terms", DEFAULT_TERM_LIMIT)
    return DEFAULT_TERM_LIMIT


def glossary_cache_path(
    directory: Path,
    *,
    source_signature: str | None,
    mode: str,
    max_terms: int,
    model_id: str,
    effort: str | None,
) -> Path:
    """Preserve the version-1 extraction identity independently of output names."""
    identity = json.dumps(
        {
            "source": source_signature,
            "mode": mode,
            "max_terms": max_terms,
            "model": model_id,
            "effort": effort,
            "extractor_version": 1,
        },
        sort_keys=True,
    )
    return (
        directory
        / ".bookweaver_glossaries"
        / f"{hashlib.sha256(identity.encode()).hexdigest()}.json"
    )


@dataclass(frozen=True)
class ExtractionPlan:
    """An extraction this run reuses or performs."""

    model: ResolvedModel
    mode: ExtractionMode
    term_limit: int
    cache_path: Path
    reused: bool


@dataclass(frozen=True)
class GlossaryPlan:
    """The glossary the prompt will carry, and the extraction behind it, if any."""

    path: Path | None
    extraction: ExtractionPlan | None

    @property
    def needs_extraction(self) -> bool:
        return self.extraction is not None and not self.extraction.reused


def plan_glossary(
    *,
    glossary_path: Path | None,
    requested_mode: str | None,
    extract: bool,
    max_terms: int | None,
    extraction_model: str | None,
    config: dict[str, object],
    translation_model: ResolvedModel,
    book_dir: Path,
    source_signature: str | None,
    may_reuse: bool,
) -> GlossaryPlan:
    """Decide the run's glossary without any model call.

    ``extract`` is an explicit request (``--extract-glossary`` or ``--extraction-model``);
    ``terminology_extraction.enabled`` in ``config`` requests extraction as well.
    ``may_reuse`` is true when the run keeps a resume store.
    """
    extraction = config.get("terminology_extraction", {})
    enabled = isinstance(extraction, dict) and extraction.get("enabled") is True
    mode = _glossary_mode(
        glossary_path=glossary_path, requested_mode=requested_mode, extract=extract or enabled
    )
    if max_terms is not None and max_terms <= 0:
        raise ValueError("glossary_max_terms must be positive")
    if mode not in ("auto", "deep-scan"):
        return GlossaryPlan(glossary_path, None)
    profile = extraction_model or (
        extraction.get("extraction_model", "pro") if isinstance(extraction, dict) else "pro"
    )
    term_limit = max_terms if max_terms is not None else configured_term_limit(config)
    if not isinstance(profile, str) or not isinstance(term_limit, int):
        raise ValueError("Invalid terminology extraction configuration")
    selection = resolve_profile(
        profile, provider=translation_model.provider, runtime=translation_model.runtime
    )
    cache = glossary_cache_path(
        book_dir,
        source_signature=source_signature,
        mode=mode,
        max_terms=term_limit,
        model_id=selection.model_id,
        effort=selection.effort,
    )
    # Cache identity includes the input and extraction request, not the output basename.
    reused = may_reuse and cache.exists()
    return GlossaryPlan(cache, ExtractionPlan(selection, mode, term_limit, cache, reused))


def report_reuse(plan: ExtractionPlan) -> None:
    print(f"[glossary] Reusing saved terms extracted with {plan.model.model_id}.", flush=True)


def announce_extraction(plan: ExtractionPlan, translation_model: ResolvedModel) -> None:
    """Printed before the extractor exists, so a refused construction still names the model."""
    difference = (
        f", not the translation model {translation_model.model_id}; this draws on its quota"
        if plan.model.model_id != translation_model.model_id
        else ""
    )
    print(f"[glossary] Term extraction uses {plan.model.model_id}{difference}.", flush=True)


def extract_glossary(
    plan: ExtractionPlan, *, epub_path: Path, provider: ITranslationProvider
) -> dict[str, object]:
    """Run the planned extraction and write the cache file.

    Returns the extraction report (tier, docs, chars, candidate_count, term_count).
    """

    def translate(prompt: str) -> str:
        translated = provider.translate_batch([prompt], system_prompt="")
        if not translated:
            raise RuntimeError("Glossary extraction returned empty response")
        return translated[0]

    plan.cache_path.parent.mkdir(parents=True, exist_ok=True)
    return extract_glossary_from_epub(
        epub_path=epub_path,
        output_path=plan.cache_path,
        translate_fn=translate,
        max_terms=plan.term_limit,
        full_index=False,
        mode=plan.mode,
    )
