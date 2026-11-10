"""The resume session Interface (SPEC-029 §4.3): a real checkpoint store, no EPUB, no provider."""

from dataclasses import replace
from pathlib import Path

import pytest

from ai.checkpoint_store import CheckpointMismatchError, FileSystemCheckpointStoreFactory
from ai.model_profiles import resolve_preset
from ai.ports.model import ResolvedModel
from ai.ports.source import TranslatedSegment
from ai.resume import (
    BatchBounds,
    BookFingerprint,
    ResumeSession,
    checkpoint_directory,
    checkpoint_progress,
)

BOOK = BookFingerprint("sha256:" + "a" * 64, "legacy-fingerprint", frozenset({"s1", "s2"}))
BOUNDS = BatchBounds(max_chars=60_000, max_segments=200, separator_overhead=6)
SEGMENTER = "epub-leaf-block-v4-source-only-bibliography"


def _session(
    directory: Path | None,
    *,
    model: ResolvedModel | None = None,
    book: BookFingerprint = BOOK,
    force: bool = False,
) -> ResumeSession:
    return ResumeSession(
        store_factory=FileSystemCheckpointStoreFactory(),
        directory=directory,
        book=book,
        model=model or resolve_preset("agy-flash-low"),
        requested_effort=None,
        output_lang="zh",
        bounds=BOUNDS,
        segmenter_signature=SEGMENTER,
        force=force,
        usage_snapshot=lambda: None,
    )


def _save_one(directory: Path, *, model: ResolvedModel | None = None) -> None:
    with _session(directory, model=model) as session:
        verified = session.verify()
        session.restore(verified, "prompt-1")
        session.commit([TranslatedSegment("s1", "source", "译文")], None)


def test_restore_needs_this_sessions_verified_value(tmp_path: Path) -> None:
    with _session(tmp_path / "a") as first, _session(tmp_path / "b") as second:
        verified = first.verify()
        with pytest.raises(RuntimeError, match="verify"):
            second.restore(verified, "prompt-1")


def test_commit_needs_restore_first(tmp_path: Path) -> None:
    with _session(tmp_path) as session:
        session.verify()
        with pytest.raises(RuntimeError, match="restore"):
            session.commit([TranslatedSegment("s1", "source", "译文")], None)


def test_a_saved_batch_restores_and_reports_progress(tmp_path: Path) -> None:
    _save_one(tmp_path)
    assert checkpoint_progress(tmp_path) == 1

    with _session(tmp_path) as session:
        verified = session.verify()
        records = session.restore(verified, "prompt-1")
    assert verified.may_reuse is True
    assert records["s1"].translated == "译文"


def test_a_changed_book_is_refused_in_verify_even_with_force(tmp_path: Path) -> None:
    _save_one(tmp_path)
    changed = replace(BOOK, content_signature="sha256:" + "b" * 64)
    with _session(tmp_path, book=changed, force=True) as session:
        with pytest.raises(CheckpointMismatchError, match="input_signature"):
            session.verify()


def test_a_soft_mismatch_is_refused_in_verify_unless_forced(tmp_path: Path) -> None:
    _save_one(tmp_path)
    medium = resolve_preset("agy-flash-medium")
    with _session(tmp_path, model=medium) as session:
        with pytest.raises(CheckpointMismatchError, match="Checkpoint mismatch: effort$"):
            session.verify()
    with _session(tmp_path, model=medium, force=True) as session:
        records = session.restore(session.verify(), "prompt-1")
    assert set(records) == {"s1"}


def test_a_new_prompt_passes_verify_and_is_refused_in_restore(tmp_path: Path) -> None:
    _save_one(tmp_path)
    with _session(tmp_path) as session:
        verified = session.verify()
        with pytest.raises(CheckpointMismatchError, match="system_prompt_hash"):
            session.restore(verified, "prompt-2")


def test_a_resume_crossing_a_trial_model_stops_unless_forced(tmp_path: Path) -> None:
    _save_one(tmp_path)
    claude = resolve_preset("claude-sonnet-5-5-low")
    with _session(tmp_path, model=claude) as session:
        with pytest.raises(CheckpointMismatchError, match="model"):
            session.verify()
    with _session(tmp_path, model=claude, force=True) as session:
        assert set(session.restore(session.verify(), "prompt-1")) == {"s1"}


def test_a_same_profile_model_change_restores_with_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _save_one(tmp_path)
    other = replace(resolve_preset("agy-flash-low"), model_id="gemini-3.9-flash-low")
    with _session(tmp_path, model=other) as session:
        records = session.restore(session.verify(), "prompt-1")
    assert set(records) == {"s1"}
    assert "[resume] Mixed-model continuation" in capsys.readouterr().out


def test_no_resume_restores_nothing_and_never_opens_a_store() -> None:
    class NoStores:
        def create(self, directory: Path) -> object:
            raise AssertionError(f"a no-resume session must not open a store: {directory}")

    session = ResumeSession(
        store_factory=NoStores(),  # type: ignore[arg-type]
        directory=None,
        book=BOOK,
        model=resolve_preset("agy-flash-low"),
        requested_effort=None,
        output_lang="zh",
        bounds=BOUNDS,
        segmenter_signature=SEGMENTER,
        force=True,
        usage_snapshot=lambda: None,
    )
    with session:
        verified = session.verify()
        assert verified.may_reuse is False
        assert session.restore(verified, "prompt-1") == {}
        assert session.commit([TranslatedSegment("s1", "source", "译文")], None) is False
        assert session.directory is None


def test_checkpoint_progress_for_missing_and_unreadable_files(tmp_path: Path) -> None:
    assert checkpoint_progress(tmp_path / "missing") == 0
    (tmp_path / "checkpoint.json").write_text("{not json")
    assert checkpoint_progress(tmp_path) is None


def test_the_default_checkpoint_directory_layout(tmp_path: Path) -> None:
    book, output = tmp_path / "in" / "My Book.epub", tmp_path / "out" / "x.epub"
    assert checkpoint_directory(explicit=None, input_file=book, output_file=output) == (
        tmp_path / "out" / ".bookweaver_checkpoints" / "epub" / "My Book"
    )
    assert checkpoint_directory(explicit=tmp_path / "c", input_file=book, output_file=output) == (
        tmp_path / "c"
    )
