"""Resume session: the one owner of checkpoint verify, restore and commit (SPEC-029).

A run opens one session and holds its checkpoint lock until the session closes. The session
enforces the order the resume rules need: ``verify`` before any external work, ``restore``
once the prompt hash is known, then ``commit`` after each translated batch. Without a
checkpoint directory (``--no-resume``) the same interface restores nothing and writes nothing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Self

from ai.checkpoint_store import (
    CheckpointIdentity,
    CheckpointMismatchError,
    ICheckpointStore,
    ICheckpointStoreFactory,
    SegmentRecord,
)
from ai.model_profiles import TRIAL_CLI_RUNTIMES, enabled_presets, is_metered, model_runtime
from ai.ports.model import ResolvedModel
from ai.ports.provider import ITranslationProvider
from ai.ports.source import TranslatedSegment

_CHECKPOINT_ROOT = ".bookweaver_checkpoints"
# Unknown until the glossary is chosen; restore() replaces it before any record is read or written.
_PENDING_PROMPT = "pending-prompt"

UsageSnapshot = Callable[[], tuple[str, dict[str, int | None]] | None]


@dataclass(frozen=True)
class BatchBounds:
    """Batch limits that both the checkpoint identity and the engine read."""

    max_chars: int
    max_segments: int | None
    separator_overhead: int


@dataclass(frozen=True)
class BookFingerprint:
    content_signature: str
    legacy_signature: str
    segment_ids: frozenset[str]


@dataclass(frozen=True)
class Verified:
    """Proof that ``verify`` ran: the glossary step reads ``may_reuse`` from it."""

    may_reuse: bool
    session: ResumeSession


def checkpoint_directory(*, explicit: Path | None, input_file: Path, output_file: Path) -> Path:
    """``--checkpoint-dir``, else ``<output dir>/.bookweaver_checkpoints/epub/<book stem>``."""
    if explicit is not None:
        return Path(explicit)
    return output_file.parent / _CHECKPOINT_ROOT / "epub" / input_file.stem


def checkpoint_progress(directory: Path) -> int | None:
    """Saved segment count for progress display: no lock and no validation.

    A missing checkpoint is 0; an unreadable one is ``None``.
    """
    path = directory / "checkpoint.json"
    try:
        count = json.loads(path.read_text(encoding="utf-8")).get("translated_segment_count")
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, AttributeError):
        return None
    return count if isinstance(count, int) else None


def _segment_backend(provider: ITranslationProvider | None, model: ResolvedModel) -> str:
    """Provenance backend reported by the provider, else the selected runtime."""
    reported = provider.backend if provider is not None else None
    if reported:
        return reported
    return model_runtime(model) if model.provider == "cli" else "any_llm"


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


class ResumeSession:
    """One run's checkpoint: verify, restore and commit, under one lock."""

    def __init__(
        self,
        *,
        store_factory: ICheckpointStoreFactory,
        directory: Path | None,
        book: BookFingerprint,
        model: ResolvedModel,
        requested_effort: str | None,
        output_lang: str,
        bounds: BatchBounds,
        segmenter_signature: str,
        force: bool,
        usage_snapshot: UsageSnapshot,
    ) -> None:
        self.directory = directory
        self._store_factory = store_factory
        self._store: ICheckpointStore | None = None
        self._book = book
        self._model = model
        self._requested_effort = requested_effort
        self._force = force
        self._usage_snapshot = usage_snapshot
        self._identity = CheckpointIdentity(
            book.content_signature,
            "epub",
            segmenter_signature,
            output_lang,
            model.profile,
            model.effort,
            _PENDING_PROMPT,
            "segment_tags",
            bounds.max_chars,
            bounds.separator_overhead,
            max_batch_segments=bounds.max_segments,
        )
        self._verified = False
        self._records: dict[str, SegmentRecord] | None = None

    def __enter__(self) -> Self:
        if self.directory is not None:
            self._store = self._store_factory.create(self.directory)
            self._store.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._store is not None:
            self._store.__exit__(exc_type, exc, traceback)
            self._store = None

    @property
    def last_save_bytes(self) -> int:
        return self._store.last_save_bytes if self._store is not None else 0

    @property
    def last_save_seconds(self) -> float:
        return self._store.last_save_seconds if self._store is not None else 0.0

    def verify(self) -> Verified:
        """Check the whole saved document before any external work.

        Hard fields always refuse. Unless forced, a resume that crosses a trial model refuses,
        then every soft field except the prompt hash refuses (the prompt is not known yet).
        """
        if self._store is None:
            self._verified = True
            return Verified(may_reuse=False, session=self)
        saved = self._store.load(
            self._identity,
            segment_ids=set(self._book.segment_ids),
            force=self._force,
            hard_only=True,
            legacy_input_signature=self._book.legacy_signature,
        )
        if not self._force:
            _refuse_trial_model_change(saved, self._model)
            self._store.load(
                self._identity,
                segment_ids=set(self._book.segment_ids),
                deferred=frozenset({"system_prompt_hash"}),
                legacy_input_signature=self._book.legacy_signature,
            )
        self._verified = True
        return Verified(may_reuse=True, session=self)

    def restore(self, verified: Verified, prompt_sha256: str) -> dict[str, SegmentRecord]:
        """Load the saved records under the run's real prompt hash."""
        if verified.session is not self or not self._verified:
            raise RuntimeError("restore() needs the Verified value from this session's verify()")
        self._identity = replace(self._identity, system_prompt_hash=prompt_sha256)
        if self._store is None:
            self._records = {}
            return {}
        records = self._store.load(
            self._identity,
            segment_ids=set(self._book.segment_ids),
            force=self._force,
            legacy_input_signature=self._book.legacy_signature,
        )
        previous_models = {record.model for record in records.values()}
        if previous_models - {self._model.model_id}:
            print(
                f"[resume] Mixed-model continuation: {sorted(previous_models)} -> {self._model.model_id}; {len(records)} restored segments. Voice or terminology may change."
            )
        self._records = records
        return dict(records)

    def commit(self, batch: list[TranslatedSegment], provider: ITranslationProvider | None) -> bool:
        """Save the batch with its provenance; return whether anything was written.

        ``provider`` is the runtime that translated the batch, not a wrapper around it.
        """
        if self._records is None:
            raise RuntimeError("commit() needs restore() first")
        if self._store is None:
            return False
        completed = datetime.now(timezone.utc).isoformat()
        updated = dict(self._records)
        for item in batch:
            updated[item.id] = SegmentRecord(
                translated=item.translated,
                profile=self._model.profile,
                provider=self._model.provider,
                backend=_segment_backend(provider, self._model),
                model=self._model.model_id,
                effort=self._model.effort,
                completed_at=completed,
                runtime_version=provider.runtime_version if provider is not None else None,
                requested_effort=self._requested_effort,
            )
        usage = self._usage_snapshot() if is_metered(self._model.provider) else None
        self._store.save(self._identity, updated, usage=usage)
        self._records = updated
        return True

    @property
    def saved_segments(self) -> int:
        return len(self._records or {})
