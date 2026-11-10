"""Unified CLI entry point for BookWeaver translation.

This is the **composition root** — it wires ports, core, and adapters
together.  It lives outside the hexagonal boundary modules and is
allowed to import from all layers.

Usage:
    python -m ai.cli input.epub --output translated.epub [options]
    python -m ai.cli ./pages_dir/ --output translated.md [options]
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from contextlib import ExitStack
from datetime import datetime, timezone
from types import TracebackType
from ai.checkpoint_store import (
    CheckpointIdentity,
    CheckpointMismatchError,
    FileSystemCheckpointStoreFactory,
    ICheckpointStoreFactory,
    SegmentRecord,
)

# Preset, enabled_presets and find_preset are the named-preset surface for entry points (SPEC-026).
from ai.model_profiles import (
    TRIAL_CLI_RUNTIMES as TRIAL_CLI_RUNTIMES,
    ResolvedModel,
    Preset as Preset,
    enabled_presets as enabled_presets,
    find_preset as find_preset,
    is_metered,
    resolve_preset,
    resolve_profile,
)
from ai.runtime_factory import DefaultProviderFactory, IProviderFactory
from ai.runtime_config import load_runtime_config, validate_config
from ai.term_panel import PanelError, resolve_panel, run_panel
from ai.term_panel import ProviderFactory as PanelProviderFactory
from ai.prompt_preparation import PromptPreparation
from ai.term_extraction import (
    announce_extraction,
    configured_term_limit,
    extract_glossary,
    plan_glossary,
    report_reuse,
)
from ai.ports.source import IBookSource

from ai.adapters.providers._delimiter import SEPARATOR_OVERHEAD
from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.core.engine import EngineConfig, TranslationEngine
from ai.core.glossary import GlossaryManager, TermUsage, measure_term_usage

# TranslationError is re-exported for ai.cli, which may import only this module (tach).
from ai.ports.provider import ITranslationProvider, TranslationError as TranslationError
from ai.ports.source import TranslatedSegment


# The one error for any input that is not an EPUB file (ADR-0003).
EPUB_ONLY_MESSAGE = "BookWeaver translates EPUB only; the input must be an .epub file"


@dataclass(frozen=True)
class TranslationSpec:
    output_lang: str = "zh"
    custom_prompt: str | None = None


@dataclass(frozen=True)
class ModelSpec:
    requested: str = "flash"
    effort: str | None = None
    explicit: bool = False
    # A named preset fixes the exact model, which a tier and an effort alone cannot.
    preset: str | None = None


@dataclass(frozen=True)
class ProviderSpec:
    name: str = "cli"
    allow_paid_api: bool = False


@dataclass(frozen=True)
class QualityPolicy:
    sanity_probe: bool = True
    max_batch_chars: int | None = None
    max_batch_segments: int | None = None


@dataclass(frozen=True)
class ResumePolicy:
    enabled: bool = True
    force: bool = False
    checkpoint_dir: Path | None = None


@dataclass(frozen=True)
class GlossarySpec:
    path: Path | None = None
    mode: str | None = None
    extract: bool = False
    min_priority: str | None = None
    max_terms: int | None = None
    extraction_model: str | None = None


@dataclass(frozen=True)
class EpubTranslationOptions:
    spec: TranslationSpec = field(default_factory=TranslationSpec)
    model: ModelSpec = field(default_factory=ModelSpec)
    provider: ProviderSpec = field(default_factory=ProviderSpec)
    quality: QualityPolicy = field(default_factory=QualityPolicy)
    config: dict[str, object] | None = None
    glossary: GlossarySpec = field(default_factory=GlossarySpec)
    resume: ResumePolicy = field(default_factory=ResumePolicy)


@dataclass(frozen=True)
class TranslationSummary:
    output_path: Path
    total_segments: int
    translated_segments: int
    resumed_segments: int
    total_batches: int
    model_used: str
    glossary_used: Path | None


def _segment_backend(provider: ITranslationProvider | None, model: ResolvedModel) -> str:
    """Provenance backend reported by the provider, else the selected runtime."""
    reported = provider.backend if provider is not None else None
    if reported:
        return reported
    return (model.runtime or "antigravity") if model.provider == "cli" else "any_llm"


def _refuse_trial_model_change(records: dict[str, SegmentRecord], model: ResolvedModel) -> None:
    """Stop a resume that crosses a Codex or Claude Code model.

    The identity keys on tier and effort, which those models share with each other and with the
    default preset. Without the stop, a model test restores another model's segments, makes no
    translation call to the chosen model, and can still spend its quota on term extraction.
    Changes within Antigravity and between metered vendors keep their mixed-model warning
    (SPEC-024), and a retired or legacy model is not a test choice.
    """
    enabled = enabled_presets()
    others = {record.model for record in records.values()} - {model.model_id}
    others &= {preset.model_id for preset in enabled}
    trial = {preset.model_id for preset in enabled if preset.runtime in TRIAL_CLI_RUNTIMES}
    if others and (model.runtime in TRIAL_CLI_RUNTIMES or others & trial):
        raise CheckpointMismatchError(
            f"Checkpoint mismatch: model; it holds {sorted(others)}, not {model.model_id}. "
            "Use another output folder to compare models, or --force-resume to continue "
            "this book on the new model"
        )


class TranslationOrchestrator:
    """Own one invocation's provider construction and checkpoint lifetime."""

    def __init__(
        self,
        *,
        provider_factory: IProviderFactory | None = None,
        checkpoint_factory: ICheckpointStoreFactory | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._checkpoint_factory = checkpoint_factory or FileSystemCheckpointStoreFactory()

    def translate(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: EpubTranslationOptions,
        *,
        input_format: str,
    ) -> TranslationSummary:
        input_file, output_file = Path(input_path).resolve(), Path(output_path).resolve()
        if not input_file.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if input_format != "epub" or not input_file.is_file():
            raise ValueError(EPUB_ONLY_MESSAGE)
        if input_file == output_file:
            raise ValueError("Output must not overwrite the source publication")
        model = (
            resolve_preset(options.model.preset)
            if options.model.preset is not None
            else resolve_profile(
                options.model.requested,
                effort=options.model.effort,
                provider=options.provider.name,
            )
        )
        if options.provider.allow_paid_api and not is_metered(model.provider):
            raise ValueError("--allow-paid-api requires a metered --provider")
        config = (
            validate_config(options.config) if options.config is not None else load_runtime_config()
        )
        prompt_preparation = PromptPreparation.from_config(
            config,
            output_lang=options.spec.output_lang,
            custom_prompt=options.spec.custom_prompt,
            immersive=True,
        )
        extraction_config = config.get("terminology_extraction", {})
        extraction = extraction_config if isinstance(extraction_config, dict) else {}
        resilience_config = config.get("epub_resilience", {})
        resilience = resilience_config if isinstance(resilience_config, dict) else {}
        split_depth = resilience.get("max_split_depth", 10)
        if not isinstance(split_depth, int):
            raise ValueError("Invalid split depth")
        factory = self._provider_factory or DefaultProviderFactory(
            audit_directory=output_file.parent / ".bookweaver_runs"
        )
        source: IBookSource = EpubSourceAdapter(input_file)
        segments = source.get_segments()
        segment_ids = {segment.id for segment in segments}
        if len(segment_ids) != len(segments):
            raise ValueError("Source segment IDs must be unique")
        source_chars = sum(len(segment.text) for segment in segments)
        glossary = options.glossary
        resume = options.resume
        batch_chars = (
            options.quality.max_batch_chars
            if options.quality.max_batch_chars is not None
            else _resolve_default_batch_chars(is_pro=model.profile == "pro", config=config)
        )
        if batch_chars <= 0:
            raise ValueError("max_batch_chars must be positive")
        batch_segments = options.quality.max_batch_segments
        if batch_segments is None:
            batch_segments = resilience.get("max_batch_segments", 200)
        if batch_segments is not None and (type(batch_segments) is not int or batch_segments <= 0):
            raise ValueError("max_batch_segments must be a positive integer")
        content_signature = _compute_content_signature(input_file)
        legacy_signature = _compute_input_signature(input_file)
        identity = (
            CheckpointIdentity(
                content_signature,
                input_format,
                _ACTIVE_EPUB_SEGMENTER_SIGNATURE,
                options.spec.output_lang,
                model.profile,
                model.effort,
                "pending-prompt",
                "segment_tags",
                batch_chars,
                SEPARATOR_OVERHEAD,
                max_batch_segments=batch_segments,
            )
            if content_signature is not None
            else None
        )
        with ExitStack() as stack:
            active_provider: ITranslationProvider | None = None
            active_model = model
            active_requested_effort = options.model.effort
            # Extraction may run on another preset; keep it visible in the audit (SPEC-025 §3.8).
            extraction_used: ResolvedModel | None = None

            def finalize_audit(
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                traceback: TracebackType | None,
            ) -> None:
                try:
                    factory.persist_audit(
                        {
                            "runtime": active_model.runtime,
                            "model": active_model.model_id,
                            "profile": active_model.profile,
                            "requested_effort": active_requested_effort,
                            "effective_effort": active_model.effort,
                            "provider": active_model.provider,
                            "preset_status": active_model.status,
                            "extraction_model": extraction_used.model_id
                            if extraction_used is not None
                            else None,
                            "extraction_preset_status": extraction_used.status
                            if extraction_used is not None
                            else None,
                            "runtime_version": active_provider.runtime_version
                            if active_provider is not None
                            else None,
                        }
                    )
                except Exception as audit_error:
                    if exc is None:
                        raise
                    exc.add_note(f"Invocation audit also failed: {type(audit_error).__name__}")

            stack.push(finalize_audit)
            store = None
            checkpoint_directory: Path | None = None
            if resume.enabled or resume.force:
                directory = _resolve_checkpoint_dir(
                    checkpoint_dir=str(resume.checkpoint_dir) if resume.checkpoint_dir else None,
                    input_file=input_file,
                    output_file=output_file,
                    input_format="epub",
                )
                store = stack.enter_context(self._checkpoint_factory.create(directory))
                checkpoint_directory = directory
                if identity is not None:
                    # Validate the complete document and known hard fields before any external work.
                    saved = store.load(
                        identity,
                        segment_ids=segment_ids,
                        force=resume.force,
                        hard_only=True,
                        legacy_input_signature=legacy_signature,
                    )
                    if not resume.force:
                        _refuse_trial_model_change(saved, model)
            glossary_plan = plan_glossary(
                glossary_path=glossary.path,
                requested_mode=glossary.mode,
                extract=glossary.extract or extraction.get("enabled") is True,
                max_terms=glossary.max_terms,
                extraction_model=glossary.extraction_model,
                config=config,
                translation_model=model,
                book_dir=output_file.parent,
                source_signature=content_signature,
                may_reuse=store is not None,
            )
            planned = glossary_plan.extraction
            if planned is not None and planned.reused:
                report_reuse(planned)
            if planned is not None and not planned.reused:
                active_model = planned.model
                extraction_used = planned.model
                active_requested_effort = None
                active_provider = None
                announce_extraction(planned, model)
                extractor = factory.create(
                    planned.model,
                    protocol="delimiter",
                    config=config,
                    allow_paid_api=options.provider.allow_paid_api,
                    remaining_chars=source_chars,
                )
                active_provider = extractor
                extract_glossary(planned, epub_path=input_file, provider=extractor)
            glossary_path = glossary_plan.path
            effective_prompt = prompt_preparation.render(
                glossary_path, min_priority=glossary.min_priority
            )
            prompt = effective_prompt.text
            if identity is not None:
                identity = replace(identity, system_prompt_hash=effective_prompt.sha256)
            records = (
                store.load(
                    identity,
                    segment_ids=segment_ids,
                    force=resume.force,
                    legacy_input_signature=legacy_signature,
                )
                if store is not None and identity is not None
                else {}
            )
            previous_models = {record.model for record in records.values()}
            if previous_models - {model.model_id}:
                print(
                    f"[resume] Mixed-model continuation: {sorted(previous_models)} -> {model.model_id}; {len(records)} restored segments. Voice or terminology may change."
                )
            remaining_chars = sum(
                len(segment.text) for segment in segments if segment.id not in records
            )

            class DeferredProvider(ITranslationProvider):
                delegate: ITranslationProvider | None = None

                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    nonlocal active_model, active_provider, active_requested_effort
                    if self.delegate is None:
                        active_model = model
                        active_requested_effort = options.model.effort
                        active_provider = None
                        self.delegate = factory.create(
                            model,
                            protocol="segment_tags",
                            config=config,
                            allow_paid_api=options.provider.allow_paid_api,
                            remaining_chars=remaining_chars,
                        )
                    active_provider = self.delegate
                    return self.delegate.translate_batch(segments, system_prompt=system_prompt)

            probe = (
                _load_probe_config(config)
                if options.quality.sanity_probe
                else _SanityProbeConfig(enabled=False)
            )
            total_batches = 0
            deferred_provider = DeferredProvider()

            def loaded(total: int, restored: int, batches: int) -> None:
                nonlocal total_batches
                total_batches = batches
                _log_progress("source", segments=total, resumed=restored, batches=batches)

            warning_log = (
                _SanityWarningLog(
                    checkpoint_directory / "warnings.json"
                    if checkpoint_directory is not None
                    else output_file.with_name(output_file.name + ".warnings.json"),
                    restored=_sanity_check_segments(
                        [
                            TranslatedSegment(
                                segment.id, segment.text, records[segment.id].translated
                            )
                            for segment in segments
                            if segment.id in records
                        ],
                        options.spec.output_lang,
                        probe,
                        "restored",
                    ),
                )
                if probe.enabled
                else None
            )

            translated_text = {key: record.translated for key, record in records.items()}

            def persist(index: int, batch: list[TranslatedSegment]) -> None:
                translated_text.update((item.id, item.translated) for item in batch)
                batch_warnings: list[SanityWarning] = []
                if probe.enabled:
                    batch_warnings = _sanity_check_batch(
                        batch, options.spec.output_lang, probe, index, total_batches
                    )
                    _log_sanity_warnings(batch_warnings)
                    _emit_batch_sample(batch, probe, index, total_batches)
                if store is not None and identity is not None:
                    completed = datetime.now(timezone.utc).isoformat()
                    updated = dict(records)
                    for item in batch:
                        updated[item.id] = SegmentRecord(
                            item.translated,
                            model.profile,
                            model.provider,
                            _segment_backend(deferred_provider.delegate, model),
                            model.model_id,
                            model.effort,
                            completed,
                            deferred_provider.delegate.runtime_version
                            if deferred_provider.delegate is not None
                            else None,
                            options.model.effort,
                        )
                    usage = factory.usage_snapshot() if is_metered(model.provider) else None
                    store.save(identity, updated, usage=usage)
                    records.update(updated)
                    _log_progress(
                        "checkpoint",
                        bytes=store.last_save_bytes,
                        seconds=round(store.last_save_seconds, 4),
                        segments=len(records),
                    )
                if warning_log is not None:
                    # After the checkpoint save, so a warning never outlives lost work.
                    warning_log.record([item.id for item in batch], batch_warnings)

            engine = TranslationEngine(
                deferred_provider,
                EngineConfig(
                    system_prompt=prompt,
                    max_batch_chars=batch_chars,
                    max_batch_segments=batch_segments,
                    max_split_depth=0 if is_metered(model.provider) else split_depth,
                    resume_translations={key: record.translated for key, record in records.items()},
                    on_checkpoint_batch=persist,
                ),
            )
            result = engine.translate(source, str(output_file), on_source_loaded=loaded)
            if glossary_path is not None:
                _report_term_usage(
                    glossary_path,
                    [
                        (segment.text, translated_text[segment.id])
                        for segment in segments
                        if segment.id in translated_text
                    ],
                    checkpoint_directory / "term-consistency.json"
                    if checkpoint_directory is not None
                    else output_file.with_name(output_file.name + ".term-consistency.json"),
                )
            if warning_log is not None:
                _log_progress(
                    "sanity_summary",
                    flagged=warning_log.count,
                    warnings=warning_log.path if warning_log.path.exists() else None,
                )
        _log_progress(
            "done",
            output=output_file,
            model=model.model_id,
            effort=model.effort,
            resumed=result.resumed_segments,
        )
        return TranslationSummary(
            output_file,
            result.total_segments,
            result.translated_segments,
            result.resumed_segments,
            result.total_batches,
            model.model_id,
            glossary_path,
        )


def run_term_panel(
    input_path: str | Path,
    panel_name: str,
    *,
    output_dir: str | Path | None = None,
    mode: str = "auto",
    max_terms: int | None = None,
    allow_paid_api: bool = False,
    config: dict[str, object] | None = None,
    provider_factory: PanelProviderFactory | None = None,
) -> Path:
    """`bookweaver terms`: run a named Term Panel and return its tiered glossary (SPEC-028).

    No translation. The glossary is cached per book and panel, so a rerun makes no call.
    """
    if allow_paid_api:
        raise PanelError("Paid Term Panel members are not supported yet (SPEC-028 Phase 3)")
    source = Path(input_path)
    if source.suffix.lower() != ".epub" or not source.is_file():
        raise PanelError(f"A Term Panel needs an EPUB file: {source}")
    runtime_config = validate_config(config) if config is not None else load_runtime_config()
    panel = resolve_panel(panel_name, runtime_config)
    configured = configured_term_limit(runtime_config)
    limit = max_terms if max_terms is not None else configured
    if not isinstance(limit, int) or not isinstance(configured, int) or limit <= 0:
        raise PanelError("The term limit must be a positive integer")
    # SPEC-028 §3.4 rule 7: the limit caps the final glossary; nominators are asked for the
    # configured number, or more when the cap is larger.
    nominator_terms = max(configured, limit)
    book_dir = Path(output_dir) if output_dir is not None else source.parent
    # No audit directory: panels refuse paid members, and the audit records only metered usage.
    factory = provider_factory or DefaultProviderFactory()
    outcome = run_panel(
        source,
        panel,
        book_dir=book_dir,
        source_signature=_compute_content_signature(source),
        max_terms=limit,
        nominator_terms=nominator_terms,
        mode=mode,
        config=runtime_config,
        factory=factory,
    )
    return outcome.glossary_path


def translate_epub(
    input_path: str | Path,
    output_path: str | Path,
    options: EpubTranslationOptions | None = None,
) -> TranslationSummary:
    return TranslationOrchestrator().translate(
        input_path, output_path, options or EpubTranslationOptions(), input_format="epub"
    )


def count_epub_segments(input_path: Path) -> int:
    """Segments a run of this EPUB will plan, from the same segmenter the run uses."""
    return len(EpubSourceAdapter(input_path).get_segments())


def default_epub_checkpoint_dir(input_path: Path, output_path: Path) -> Path:
    """Where an EPUB run without ``--checkpoint-dir`` keeps its checkpoint."""
    return _resolve_checkpoint_dir(
        checkpoint_dir=None, input_file=input_path, output_file=output_path, input_format="epub"
    )


# ── Checkpoint and batch constants ────────────────────────────

_CHECKPOINT_ROOT = ".bookweaver_checkpoints"
_ACTIVE_EPUB_SEGMENTER_SIGNATURE = "epub-leaf-block-v4-source-only-bibliography"
_DEFAULT_BATCH_CHARS_PRO_EPUB = 60_000
_DEFAULT_BATCH_CHARS_STANDARD_EPUB = 60_000


# ── Sanity probe ──────────────────────────────────────────────


@dataclass(frozen=True)
class _SanityProbeConfig:
    enabled: bool = True
    max_length_ratio: float = 2.0
    min_length_ratio: float = 0.15
    min_source_length: int = 20
    min_cjk_density: float = 0.30
    min_cjk_source_length: int = 40
    heartbeat_chars: int = 60


def _load_probe_config(runtime_config: dict[str, object]) -> _SanityProbeConfig:
    raw = runtime_config.get("sanity_probe", {})
    if not isinstance(raw, dict):
        return _SanityProbeConfig()
    d = _SanityProbeConfig()
    try:
        return _SanityProbeConfig(
            enabled=bool(raw.get("enabled", d.enabled)),
            max_length_ratio=float(raw.get("max_length_ratio", d.max_length_ratio)),
            min_length_ratio=float(raw.get("min_length_ratio", d.min_length_ratio)),
            min_source_length=int(raw.get("min_source_length", d.min_source_length)),
            min_cjk_density=float(raw.get("min_cjk_density", d.min_cjk_density)),
            min_cjk_source_length=int(raw.get("min_cjk_source_length", d.min_cjk_source_length)),
            heartbeat_chars=int(raw.get("heartbeat_chars", d.heartbeat_chars)),
        )
    except (TypeError, ValueError):
        import sys

        print("Warning: invalid sanity_probe config value; using defaults.", file=sys.stderr)
        return _SanityProbeConfig()


def _count_cjk(text: str) -> int:
    """Count characters in the CJK Unified Ideographs block (U+4E00–U+9FFF).

    Covers ~99% of everyday Simplified/Traditional Chinese.
    Extension A and Compatibility Ideographs are excluded intentionally.
    """
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


# Matches source patterns that legitimately keep Latin characters in the
# translation, diluting CJK density.  Bypass the CJK density check when
# any of these are present in the source segment.
_URL_HINT_RE = re.compile(
    r"https?://|www\.|\.com\b|\.org\b|\.net\b|\.co\.\w{2}\b|@\w"  # URLs / handles
    r"|©|ISBN\b|First\s+published\b",  # copyright metadata
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SanityWarning:
    """One observational quality signal; never a reason to stop translation."""

    segment_id: str
    batch: str
    check: str
    detail: str
    source_excerpt: str
    translation_excerpt: str


_WARNING_EXCERPT_CHARS = 120


def _excerpt(text: str) -> str:
    return text[:_WARNING_EXCERPT_CHARS] + ("..." if len(text) > _WARNING_EXCERPT_CHARS else "")


def _sanity_check_batch(
    translated: list[TranslatedSegment],
    output_lang: str,
    probe_config: _SanityProbeConfig,
    batch_index: int,
    total_batches: int,
) -> list[SanityWarning]:
    """Return per-segment quality signals for later human review.

    Static thresholds produce frequent false positives (abbreviations, short
    dialogue, mixed-language passages), so the probe observes and never halts.
    """
    return _sanity_check_segments(
        translated, output_lang, probe_config, f"{batch_index + 1}/{total_batches}"
    )


def _sanity_check_segments(
    translated: Sequence[TranslatedSegment],
    output_lang: str,
    probe_config: _SanityProbeConfig,
    batch_label: str,
) -> list[SanityWarning]:
    check_cjk = output_lang.startswith("zh")
    warnings: list[SanityWarning] = []

    def flag(seg: TranslatedSegment, check: str, detail: str) -> None:
        warnings.append(
            SanityWarning(
                seg.id, batch_label, check, detail, _excerpt(seg.original), _excerpt(seg.translated)
            )
        )

    for seg in translated:
        tgt = seg.translated
        src = seg.original
        if not tgt.strip():
            flag(seg, "empty_output", "translation is empty")
            continue
        if len(src) >= probe_config.min_source_length:
            ratio = len(tgt) / len(src)
            if ratio < probe_config.min_length_ratio or ratio > probe_config.max_length_ratio:
                flag(
                    seg,
                    "length_ratio",
                    f"length_ratio={ratio:.2f} not in "
                    f"[{probe_config.min_length_ratio}, {probe_config.max_length_ratio}]",
                )
        if (
            check_cjk
            and len(src) >= probe_config.min_cjk_source_length
            and not _URL_HINT_RE.search(src)
        ):
            tgt_stripped = tgt.strip()
            cjk_count = _count_cjk(tgt_stripped)
            # Subtract ASCII letters (preserved proper nouns / company names) from the
            # denominator: they are untranslated *intentionally* and must not penalise
            # the density score.  Zero-CJK targets still yield density = 0.
            ascii_letters = sum(1 for c in tgt_stripped if c.isascii() and c.isalpha())
            effective_len = max(len(tgt_stripped) - ascii_letters, 1)
            density = cjk_count / effective_len
            if density < probe_config.min_cjk_density:
                flag(
                    seg,
                    "cjk_density",
                    f"cjk_density={density:.2f} < {probe_config.min_cjk_density}",
                )
    return warnings


def _log_sanity_warnings(warnings: Sequence[SanityWarning]) -> None:
    for item in warnings:
        _log_progress(
            "sanity_warning",
            batch=item.batch,
            segment=item.segment_id,
            check=item.check,
            detail=item.detail,
        )


class _SanityWarningLog:
    """Persist probe warnings beside the run so they survive interruption and resume.

    The checkpoint is the source of truth: warnings for restored segments are
    recomputed from their committed translations rather than read back from a
    previous file, so a crash or write failure between the checkpoint save and
    the warning write cannot hide a committed suspicious segment. A
    retranslated segment's entries are replaced by its newest result. Write
    and cleanup failures are reported but never stop translation.
    """

    def __init__(self, path: Path, *, restored: Sequence[SanityWarning] = ()) -> None:
        self.path = path
        self._by_segment: dict[str, list[SanityWarning]] = {}
        for item in restored:
            self._by_segment.setdefault(item.segment_id, []).append(item)
        if restored or path.exists():
            # Replace any stale, partial, or missing file with the recomputed state.
            self._write()

    @property
    def count(self) -> int:
        return sum(len(items) for items in self._by_segment.values())

    def record(self, segment_ids: Sequence[str], warnings: Sequence[SanityWarning]) -> None:
        for segment_id in segment_ids:
            self._by_segment.pop(segment_id, None)
        for item in warnings:
            self._by_segment.setdefault(item.segment_id, []).append(item)
        if warnings or self.path.exists():
            self._write()

    def _write(self) -> None:
        payload = {
            "schema_version": 1,
            "note": "Observational sanity-probe signals for manual review; translation was not halted.",
            "warning_count": self.count,
            "warnings": [asdict(item) for items in self._by_segment.values() for item in items],
        }
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".warnings-",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
            temporary = None
        except OSError as exc:
            _log_progress("sanity_warning_log", stderr=True, path=self.path, error=str(exc))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    _log_progress(
                        "sanity_warning_log",
                        stderr=True,
                        path=temporary,
                        error=f"temporary file not removed ({exc})",
                    )


def _emit_batch_sample(
    translated: list[TranslatedSegment],
    probe_config: _SanityProbeConfig,
    batch_index: int,
    total_batches: int,
) -> None:
    if not translated:
        return
    first = translated[0]
    doc_path = first.id.split("::")[0] if "::" in first.id else None
    n = probe_config.heartbeat_chars
    src = first.original
    tgt = first.translated
    src_snippet = src[:n] + ("..." if len(src) > n else "")
    tgt_snippet = tgt[:n] + ("..." if len(tgt) > n else "")
    _log_progress(
        "batch_sample",
        batch=f"{batch_index + 1}/{total_batches}",
        doc=doc_path,
        src=src_snippet,
        tgt=tgt_snippet,
    )


def _compute_content_signature(input_file: Path) -> str:
    with input_file.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def _compute_input_signature(input_file: Path) -> str:
    """Legacy metadata fingerprint; never use as a content digest."""
    stat = input_file.stat()
    payload = f"{input_file.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve_checkpoint_dir(
    *,
    checkpoint_dir: str | None,
    input_file: Path,
    output_file: Path,
    input_format: str,
) -> Path:
    if checkpoint_dir is not None:
        return Path(checkpoint_dir)
    return output_file.parent / _CHECKPOINT_ROOT / input_format / input_file.stem


# ── Wiring helpers ────────────────────────────────────────────


def _resolve_positive_int_config(
    scope: dict[str, object],
    *,
    key: str,
    default: int,
) -> int:
    raw = scope.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return raw


def _resolve_default_batch_chars(
    *,
    is_pro: bool,
    config: dict[str, object] | None,
) -> int:
    resilience = (config or {}).get("epub_resilience", {})
    if not isinstance(resilience, dict):
        resilience = {}
    if is_pro:
        return _resolve_positive_int_config(
            resilience,
            key="pro_epub_max_batch_chars",
            default=_DEFAULT_BATCH_CHARS_PRO_EPUB,
        )
    return _resolve_positive_int_config(
        resilience,
        key="standard_epub_max_batch_chars",
        default=_DEFAULT_BATCH_CHARS_STANDARD_EPUB,
    )


def _format_progress_value(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() for ch in text) or "=" in text or '"' in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _report_term_usage(
    glossary_path: Path, pairs: Sequence[tuple[str, str]], report_path: Path
) -> None:
    """Record how each term was translated. A finished book never fails for this report."""
    try:
        usage = measure_term_usage(GlossaryManager.from_json_file(glossary_path).terms, pairs)
        # SPEC-028 §3.5: only fixed drift is a problem. Without tiers the report keeps its shape.
        tiered = any(item.tier is not None for item in usage)
        drifted = sum(not item.consistent for item in usage if item.tier != "preferred")
        summary: dict[str, int] = {"terms": len(usage), "inconsistent": drifted}
        if tiered:
            summary["preferred_varied"] = sum(
                not item.consistent for item in usage if item.tier == "preferred"
            )

        def entry(item: TermUsage) -> dict[str, object]:
            fields = {**asdict(item), "consistent": item.consistent}
            if not tiered:
                fields.pop("tier")
            elif item.tier is None:
                fields["tier"] = "fixed"
            return fields

        report = {
            "summary": summary,
            "terms": [entry(item) for item in sorted(usage, key=lambda item: item.consistent)],
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError) as exc:
        _log_progress("term_usage_not_saved", error=type(exc).__name__)
        return
    _log_progress("term_usage", terms=len(usage), inconsistent=drifted, report=report_path)


def _log_progress(event: str, *, stderr: bool = False, **fields: object) -> None:
    parts = [
        f"{key}={_format_progress_value(value)}"
        for key, value in fields.items()
        if value is not None
    ]
    line = f"[progress:{event}]"
    if parts:
        line = f"{line} {' '.join(parts)}"
    if stderr:
        import sys

        print(line, file=sys.stderr)
        return
    print(line)
