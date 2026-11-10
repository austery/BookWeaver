"""Resume behaviour pinned before the SPEC-029 move (§4.2).

Each test goes through TranslationOrchestrator (or the local API) and must pass on the code
before the resume-session module exists, so the move can be checked against it unchanged.
"""

import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.checkpoint_store import CheckpointError, CheckpointStore
from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ProviderSpec,
    QualityPolicy,
    ResumePolicy,
    TranslationOrchestrator,
)
from ai.ports.provider import ITranslationProvider, ProviderUnavailableError
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_invocation_audit import AuditedFactory
from tests.unit.test_orchestration import make_epub, make_indexed_epub


def _translate(
    tmp_path: Path,
    factory: RecordingFactory,
    *,
    resume: ResumePolicy | None = None,
    glossary: GlossarySpec | None = None,
    quality: QualityPolicy | None = None,
    provider: ProviderSpec | None = None,
) -> object:
    options = EpubTranslationOptions(
        config={},
        resume=resume or ResumePolicy(),
        glossary=glossary or GlossarySpec(),
        quality=quality or QualityPolicy(),
        provider=provider or ProviderSpec(),
    )
    return TranslationOrchestrator(provider_factory=factory).translate(
        tmp_path / "book.epub", tmp_path / "out.epub", options, input_format="epub"
    )


def _checkpoint(tmp_path: Path) -> Path:
    return tmp_path / ".bookweaver_checkpoints" / "epub" / "book" / "checkpoint.json"


def _another_run_is_refused(directory: Path) -> bool:
    try:
        with CheckpointStore(directory):
            return False
    except CheckpointError as exc:
        return "Another run owns this checkpoint" in str(exc)


def test_the_lock_is_held_while_translating_and_while_writing_the_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_epub(tmp_path / "book.epub")
    directory = _checkpoint(tmp_path).parent
    seen: dict[str, bool] = {}

    class LockProbeFactory(RecordingFactory):
        def create(self, model: ResolvedModel, **kwargs: object) -> ITranslationProvider:
            inner = super().create(model, **kwargs)  # type: ignore[arg-type]

            class Probe(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    seen["translating"] = _another_run_is_refused(directory)
                    return inner.translate_batch(segments, system_prompt=system_prompt)

            return Probe()

    real_save = EpubSourceAdapter.save

    def probing_save(self: EpubSourceAdapter, output_path: str) -> None:
        seen["writing output"] = _another_run_is_refused(directory)
        real_save(self, output_path)

    monkeypatch.setattr(EpubSourceAdapter, "save", probing_save)
    _translate(tmp_path, LockProbeFactory())

    assert seen == {"translating": True, "writing output": True}
    assert not _another_run_is_refused(directory)


def test_a_held_lock_stops_the_run_and_still_writes_one_audit(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    factory = AuditedFactory()
    with CheckpointStore(_checkpoint(tmp_path).parent):
        with pytest.raises(CheckpointError, match="Another run owns this checkpoint"):
            _translate(tmp_path, factory)
    assert len(factory.audits) == 1
    assert factory.created == []


def test_force_alone_restores_a_finished_book_and_reuses_its_glossary(tmp_path: Path) -> None:
    make_indexed_epub(tmp_path / "book.epub")
    glossary = GlossarySpec(extract=True)
    _translate(tmp_path, RecordingFactory(), glossary=glossary)

    again = RecordingFactory()
    result = _translate(
        tmp_path, again, glossary=glossary, resume=ResumePolicy(enabled=False, force=True)
    )

    assert result.resumed_segments == 2  # type: ignore[attr-defined]
    assert again.requests == [] and again.created == []


def test_a_saved_record_keeps_every_provenance_field(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, AuditedFactory())

    records = json.loads(_checkpoint(tmp_path).read_text())["segments"]
    record = next(iter(records.values()))
    completed = record.pop("completed_at")

    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00", completed)
    assert list(record) == [
        "translated",
        "profile",
        "provider",
        "backend",
        "model",
        "effort",
        "runtime_version",
        "requested_effort",
        "source_verification",
    ]
    assert record == {
        "translated": "花园大门敞开着。",
        "profile": "flash",
        "provider": "cli",
        "backend": "antigravity",
        "model": "gemini-3.8-flash-low",
        "effort": "low",
        "runtime_version": "offline-runtime-1",
        "requested_effort": None,
        "source_verification": None,
    }


def test_the_identity_for_default_options_is_unchanged(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, RecordingFactory())

    identity = json.loads(_checkpoint(tmp_path).read_text())["identity"]
    prompt_hash = identity.pop("system_prompt_hash")
    signature = identity.pop("input_signature")

    assert re.fullmatch(r"[0-9a-f]{64}", prompt_hash)
    assert signature.startswith("sha256:")
    assert identity == {
        "input_format": "epub",
        "segmenter_signature": "epub-leaf-block-v4-source-only-bibliography",
        "output_lang": "zh",
        "profile": "flash",
        "effort": "low",
        "protocol": "segment_tags",
        "max_batch_chars": 60000,
        "separator_overhead": 6,
        "max_batch_segments": 200,
    }


def test_paid_usage_from_an_interrupted_run_survives_the_next_run(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    one_segment_batches = QualityPolicy(max_batch_chars=30)

    class MeteredFactory(AuditedFactory):
        def __init__(self, run_id: str, *, fail_second_batch: bool) -> None:
            super().__init__()
            self.run_id = run_id
            self.fail_second_batch = fail_second_batch
            self.batches = 0

        def create(self, model: ResolvedModel, **kwargs: object) -> ITranslationProvider:
            inner = super().create(model, **kwargs)  # type: ignore[arg-type]
            factory = self

            class Interrupting(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    factory.batches += 1
                    if factory.fail_second_batch and factory.batches == 2:
                        raise ProviderUnavailableError("synthetic interruption")
                    return inner.translate_batch(segments, system_prompt=system_prompt)

            return Interrupting()

        def usage_snapshot(self) -> tuple[str, dict[str, int | None]]:
            return self.run_id, {"request_count": self.batches, "input_tokens": None}

    with pytest.raises(ProviderUnavailableError):
        _translate(
            tmp_path,
            MeteredFactory("run-1", fail_second_batch=True),
            quality=one_segment_batches,
            provider=ProviderSpec(name="gemini"),
        )
    _translate(
        tmp_path,
        MeteredFactory("run-2", fail_second_batch=False),
        quality=one_segment_batches,
        provider=ProviderSpec(name="gemini"),
    )

    usage = json.loads(_checkpoint(tmp_path).read_text())["paid_usage_by_run"]
    assert set(usage) == {"run-1", "run-2"}


@pytest.mark.parametrize("damage", ["unknown segment id", "wrong segment count"])
def test_a_damaged_checkpoint_stops_before_any_provider_request(
    tmp_path: Path, damage: str
) -> None:
    make_indexed_epub(tmp_path / "book.epub")
    glossary = GlossarySpec(extract=True)
    _translate(tmp_path, RecordingFactory(), glossary=glossary)
    # Without its cached glossary the next run would extract terms, so a late check would call.
    shutil.rmtree(tmp_path / ".bookweaver_glossaries")
    path = _checkpoint(tmp_path)
    data = json.loads(path.read_text())
    if damage == "unknown segment id":
        data["segments"]["no-such-segment"] = next(iter(data["segments"].values()))
        data["translated_segment_count"] += 1
    else:
        data["translated_segment_count"] += 1
    path.write_text(json.dumps(data))

    again = RecordingFactory()
    with pytest.raises(CheckpointError):
        _translate(tmp_path, again, glossary=glossary)
    assert again.requests == [] and again.created == []


def test_a_batch_whose_save_fails_leaves_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_epub(tmp_path / "book.epub")
    real_save = CheckpointStore.save
    saves = {"count": 0}

    def fail_second_save(self: CheckpointStore, *args: object, **kwargs: object) -> None:
        saves["count"] += 1
        if saves["count"] == 2:
            raise OSError("synthetic save failure")
        real_save(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(CheckpointStore, "save", fail_second_save)
    with pytest.raises(OSError, match="synthetic save failure"):
        # Both fixture paragraphs are long enough that a 200-character reply trips length_ratio.
        _translate(
            tmp_path,
            RecordingFactory(translation="跑" * 200),
            quality=QualityPolicy(max_batch_chars=30),
        )

    warnings = json.loads((_checkpoint(tmp_path).parent / "warnings.json").read_text())
    assert len(warnings["warnings"]) == 1


def test_no_resume_writes_no_checkpoint_and_leaves_an_existing_one_alone(
    tmp_path: Path,
) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    make_epub(fresh / "book.epub")
    _translate(fresh, RecordingFactory(), resume=ResumePolicy(enabled=False))
    assert not (fresh / ".bookweaver_checkpoints").exists()

    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, RecordingFactory())
    before = _checkpoint(tmp_path).read_bytes()
    again = RecordingFactory()
    result = _translate(tmp_path, again, resume=ResumePolicy(enabled=False))
    assert result.resumed_segments == 0  # type: ignore[attr-defined]
    assert again.requests != []
    assert _checkpoint(tmp_path).read_bytes() == before


def test_each_save_reports_its_size_time_and_segment_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, RecordingFactory())

    lines = [
        line for line in capsys.readouterr().out.splitlines() if "[progress:checkpoint]" in line
    ]
    assert len(lines) == 1
    assert re.fullmatch(
        r"\[progress:checkpoint\] bytes=\d+ seconds=\d+(\.\d+)? segments=2", lines[0]
    )


def test_local_api_reports_unknown_progress_for_an_unreadable_checkpoint(tmp_path: Path) -> None:
    from tests.unit.test_local_api import restarted, write_record

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "checkpoint.json").write_text("{not json")
    state = tmp_path / "state"
    write_record(
        state,
        pid=2**22 + 12345,
        process_start="Thu Jan  1 00:00:00 2026",
        checkpoint_dir=str(checkpoint_dir),
    )

    status = restarted(state).get("/runs/current").json()

    assert status["done_segments"] is None
