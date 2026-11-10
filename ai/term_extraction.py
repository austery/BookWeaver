"""Which glossary a translation run uses, and which model extracts it.

One place for the glossary decision that used to be spread over the translation method, the
prompt module and a request helper. The Term Panel (SPEC-028 Phase 2b, ``--term-panel``) is one
more source behind the same plan. It works in two steps so the caller can record the extraction
model or the panel for the audit before it constructs any provider:

1. ``plan_glossary`` decides, with no model call: no glossary, the user's file, a Term Panel
   glossary (cached or to run), a cached extraction, or a new extraction (which model, which
   term limit, which cache file).
2. ``extract_glossary`` runs a planned extraction with a provider the caller constructed;
   ``ai.term_panel.run_panel`` runs a planned panel.

Rules kept exactly as before this module existed:

- The cache key and file name (``glossary_cache_path``) are unchanged; they feed the prompt hash.
- A cached glossary is reused only when the run keeps a resume store. A run without resume
  extracts again and overwrites the cached file, so a later resume of an older checkpoint made
  with other terms can stop on a prompt mismatch.
- ``auto`` stops before any model call when the book has no usable index (ADR-0005).

The panel keeps its own rules (SPEC-028 §3.7): its cache lives beside the EPUB, shared by every
output folder, and a cached panel glossary is reused whether or not the run keeps a resume store.
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
from ai.term_panel import PanelError, PanelPlan, plan_panel, resolve_panel

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


def panel_term_limits(config: dict[str, object], max_terms: int | None) -> tuple[int, int]:
    """The panel's glossary cap and per-nominator request (SPEC-028 §3.4 rule 7).

    The cap is ``max_terms`` or the configured limit; nominators are asked for the configured
    number, or more when the cap is larger. ``bookweaver terms`` and ``--term-panel`` share this,
    so both find the same cached glossary.
    """
    configured = configured_term_limit(config)
    limit = max_terms if max_terms is not None else configured
    if (
        not isinstance(limit, int)
        or not isinstance(configured, int)
        or isinstance(limit, bool)
        or limit <= 0
    ):
        raise PanelError("The term limit must be a positive integer")
    return limit, max(configured, limit)


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
    panel: PanelPlan | None = None

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
    term_panel: str | None = None,
    panel_dir: Path | None = None,
) -> GlossaryPlan:
    """Decide the run's glossary without any model call.

    ``extract`` is an explicit request (``--extract-glossary`` or ``--extraction-model``);
    ``terminology_extraction.enabled`` in ``config`` requests extraction as well.
    ``may_reuse`` is true when the run keeps a resume store.
    ``term_panel`` names a panel from ``terminology_panels``; it replaces single-model
    extraction, including extraction the configuration turns on, and keeps its cache in
    ``panel_dir`` (the EPUB's folder).
    """
    if term_panel is not None:
        return _plan_panel_glossary(
            term_panel,
            glossary_path=glossary_path,
            requested_mode=requested_mode,
            extract=extract,
            max_terms=max_terms,
            extraction_model=extraction_model,
            config=config,
            panel_dir=panel_dir if panel_dir is not None else book_dir,
            source_signature=source_signature,
        )
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


def _plan_panel_glossary(
    name: str,
    *,
    glossary_path: Path | None,
    requested_mode: str | None,
    extract: bool,
    max_terms: int | None,
    extraction_model: str | None,
    config: dict[str, object],
    panel_dir: Path,
    source_signature: str | None,
) -> GlossaryPlan:
    """SPEC-028 §3.10: the conflicts, then the panel's plan; all before any call."""
    conflicts = [
        flag
        for flag, given in (
            ("--glossary", glossary_path is not None),
            ("--extraction-model", extraction_model is not None),
            # The CLI sets `extract` for --extraction-model too; name only what was passed.
            ("--extract-glossary", extract and extraction_model is None),
        )
        if given
    ]
    if conflicts:
        raise PanelError(f"--term-panel chooses the terms; drop {', '.join(conflicts)}")
    if max_terms is not None and max_terms <= 0:
        raise ValueError("glossary_max_terms must be positive")
    panel = resolve_panel(name, config)
    limit, nominator_terms = panel_term_limits(config, max_terms)
    plan = plan_panel(
        panel,
        book_dir=panel_dir,
        source_signature=source_signature,
        max_terms=limit,
        nominator_terms=nominator_terms,
        mode=requested_mode or "auto",
    )
    return GlossaryPlan(plan.glossary_path, None, plan)


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
