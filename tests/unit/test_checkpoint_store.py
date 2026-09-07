"""Durable checkpoint behavior through the filesystem store interface."""

from pathlib import Path
from dataclasses import replace
import os
import json

import pytest

from ai.checkpoint_store import (
    CheckpointError,
    CheckpointIdentity,
    CheckpointMismatchError,
    CheckpointStore,
    SegmentRecord,
)


def identity() -> CheckpointIdentity:
    return CheckpointIdentity(
        input_signature="sha256:book",
        input_format="epub",
        segmenter_signature="v3",
        output_lang="zh",
        profile="flash",
        effort="low",
        system_prompt_hash="sha256:prompt",
        protocol="segment_tags",
        max_batch_chars=60000,
        separator_overhead=6,
    )


def test_committed_segments_restore_with_their_provenance(tmp_path: Path) -> None:
    record = SegmentRecord(
        "译文", "flash", "cli", "antigravity", "gemini-3.8-flash-low", "low", "2026-09-07T00:00:00Z"
    )
    with CheckpointStore(tmp_path) as store:
        assert store.load(identity(), segment_ids={"chapter::0"}) == {}
        store.save(identity(), {"chapter::0": record})
    with CheckpointStore(tmp_path) as store:
        assert store.load(identity(), segment_ids={"chapter::0"}) == {"chapter::0": record}


def test_second_writer_is_rejected(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path):
        with pytest.raises(CheckpointError, match="Another run"):
            with CheckpointStore(tmp_path):
                pass


def test_failed_replacement_preserves_previous_committed_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = SegmentRecord("译文", "flash", "cli", "antigravity", "model", "low", None)
    with CheckpointStore(tmp_path) as store:
        store.save(identity(), {"a": record})

        def failed_replace(source: object, destination: object) -> None:
            raise OSError("simulated disk failure")

        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", failed_replace)
            with pytest.raises(CheckpointError):
                store.save(identity(), {"a": record, "b": record})
        assert store.load(identity(), segment_ids={"a", "b"}) == {"a": record}
    assert not list(tmp_path.glob(".checkpoint-*"))


def test_hard_mismatch_cannot_be_forced_but_effort_can(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path) as store:
        store.save(identity(), {})
        with pytest.raises(CheckpointMismatchError):
            store.load(
                replace(identity(), input_signature="different"), segment_ids=set(), force=True
            )
        with pytest.raises(CheckpointMismatchError):
            store.load(replace(identity(), effort="high"), segment_ids=set())
        assert store.load(replace(identity(), effort="high"), segment_ids=set(), force=True) == {}


def test_corrupt_canonical_document_does_not_fall_back(tmp_path: Path) -> None:
    (tmp_path / "checkpoint.json").write_text("{broken")
    (tmp_path / "state.json").write_text("{}")
    with CheckpointStore(tmp_path) as store:
        with pytest.raises(CheckpointError, match="Cannot read"):
            store.load(identity(), segment_ids=set())


def test_legacy_import_preserves_files_until_new_batch(tmp_path: Path) -> None:
    state = {
        "schema_version": 1,
        "input_signature": "sha256:book",
        "input_format": "epub",
        "segmenter_signature": "epub-leaf-block-v3",
        "output_lang": "zh",
        "model": "gemini-2.5-flash",
        "provider": "cli",
        "max_batch_chars": 60000,
        "separator_overhead": 6,
        "system_prompt_hash": "sha256:prompt",
        "translated_segment_count": 1,
    }
    state_text = json.dumps(state)
    (tmp_path / "state.json").write_text(state_text)
    (tmp_path / "translations.json").write_text(
        json.dumps({"schema_version": 1, "segments": {"a": "译文"}})
    )
    selected = replace(identity(), segmenter_signature="epub-leaf-block-v3", effort=None)
    with CheckpointStore(tmp_path) as store:
        loaded = store.load(selected, segment_ids={"a"})
        assert loaded["a"].model == "gemini-2.5-flash"
        assert loaded["a"].backend == "gemini_cli"
        assert not (tmp_path / "checkpoint.json").exists()
        store.save(selected, loaded)
    assert (tmp_path / "state.json").read_text() == state_text


def test_force_does_not_accept_malformed_identity(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path) as store:
        store.save(identity(), {})
        path = tmp_path / "checkpoint.json"
        data = json.loads(path.read_text())
        data["identity"]["max_batch_chars"] = "broken"
        path.write_text(json.dumps(data))
        with pytest.raises(CheckpointError, match="Invalid"):
            store.load(identity(), segment_ids=set(), force=True)


def test_blank_restored_translation_is_rejected(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path) as store:
        store.save(
            identity(),
            {"a": SegmentRecord(" ", "flash", "cli", "antigravity", "model", "low", None)},
        )
        with pytest.raises(CheckpointError, match="empty"):
            store.load(identity(), segment_ids={"a"})
