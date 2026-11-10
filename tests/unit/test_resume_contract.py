"""Resume behaviour pinned before the SPEC-029 move (§4.2).

Each test goes through TranslationOrchestrator (or the local API) and must pass on the code
before the resume-session module exists, so the move can be checked against it unchanged.
"""

import hashlib
import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai.adapters.sources.epub_adapter import EpubSourceAdapter
from ai.checkpoint_store import (
    CheckpointError,
    CheckpointMismatchError,
    CheckpointStore,
    ICheckpointStore,
)
from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ModelSpec,
    ProviderSpec,
    QualityPolicy,
    ResumePolicy,
    TranslationOrchestrator,
    TranslationSummary,
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
    model: ModelSpec | None = None,
    checkpoint_factory: object | None = None,
) -> TranslationSummary:
    options = EpubTranslationOptions(
        config={},
        resume=resume or ResumePolicy(),
        glossary=glossary or GlossarySpec(),
        quality=quality or QualityPolicy(),
        provider=provider or ProviderSpec(),
        model=model or ModelSpec(),
    )
    return TranslationOrchestrator(
        provider_factory=factory,
        checkpoint_factory=checkpoint_factory,  # type: ignore[arg-type]
    ).translate(tmp_path / "book.epub", tmp_path / "out.epub", options, input_format="epub")


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

    assert result.resumed_segments == 2
    assert again.requests == [] and again.created == []


def test_a_saved_record_keeps_every_provenance_field(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")

    class ReportingFactory(RecordingFactory):
        """A provider that reports its own backend and version, as real runtimes do."""

        def create(self, model: ResolvedModel, **kwargs: object) -> ITranslationProvider:
            inner = super().create(model, **kwargs)  # type: ignore[arg-type]

            class Reporting(ITranslationProvider):
                backend = "gemini_cli"
                runtime_version = "offline-runtime-1"

                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    return inner.translate_batch(segments, system_prompt=system_prompt)

            return Reporting()

    _translate(tmp_path, ReportingFactory(), model=ModelSpec(effort="low"))

    records = json.loads(_checkpoint(tmp_path).read_text())["segments"]
    record = next(iter(records.values()))
    completed = record.pop("completed_at")

    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00", completed)
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
        "backend": "gemini_cli",
        "model": "gemini-3.8-flash-low",
        "effort": "low",
        "runtime_version": "offline-runtime-1",
        "requested_effort": "low",
        "source_verification": None,
    }


def test_the_identity_for_default_options_is_unchanged(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    factory = RecordingFactory()
    _translate(tmp_path, factory)

    identity = json.loads(_checkpoint(tmp_path).read_text())["identity"]
    book = hashlib.sha256((tmp_path / "book.epub").read_bytes()).hexdigest()
    prompt = hashlib.sha256(factory.requests[0].prompt.encode()).hexdigest()

    assert list(identity) == [
        "input_signature",
        "input_format",
        "segmenter_signature",
        "output_lang",
        "profile",
        "effort",
        "system_prompt_hash",
        "protocol",
        "max_batch_chars",
        "separator_overhead",
        "max_batch_segments",
    ]
    assert identity == {
        "input_signature": "sha256:" + book,
        "input_format": "epub",
        "segmenter_signature": "epub-leaf-block-v4-source-only-bibliography",
        "output_lang": "zh",
        "profile": "flash",
        "effort": "low",
        "system_prompt_hash": prompt,
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
    assert usage == {
        "run-1": {"request_count": 1, "input_tokens": None},
        "run-2": {"request_count": 1, "input_tokens": None},
    }


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
    expected = (
        "unknown source segment IDs"
        if damage == "unknown segment id"
        else "segment count does not match"
    )
    with pytest.raises(CheckpointError, match=expected):
        _translate(tmp_path, again, glossary=glossary)
    assert again.requests == [] and again.created == []


def test_a_batch_whose_save_fails_leaves_no_warning(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")

    class SecondSaveFails(CheckpointStore):
        saves = 0

        def save(self, *args: object, **kwargs: object) -> None:
            SecondSaveFails.saves += 1
            if SecondSaveFails.saves == 2:
                raise OSError("synthetic save failure")
            super().save(*args, **kwargs)  # type: ignore[arg-type]

    class Stores:
        def create(self, directory: Path) -> ICheckpointStore:
            return SecondSaveFails(directory)

    with pytest.raises(OSError, match="synthetic save failure"):
        # Both fixture paragraphs are long enough that a 200-character reply trips length_ratio.
        _translate(
            tmp_path,
            RecordingFactory(translation="跑" * 200),
            quality=QualityPolicy(max_batch_chars=30),
            checkpoint_factory=Stores(),
        )

    warnings = json.loads((_checkpoint(tmp_path).parent / "warnings.json").read_text())
    assert [entry["segment_id"] for entry in warnings["warnings"]] == ["chapter.xhtml::0"]


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
    assert result.resumed_segments == 0
    assert again.requests != []
    assert _checkpoint(tmp_path).read_bytes() == before


def test_each_save_reports_its_size_time_and_segment_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, RecordingFactory(), quality=QualityPolicy(max_batch_chars=30))

    lines = [
        line for line in capsys.readouterr().out.splitlines() if "[progress:checkpoint]" in line
    ]
    pattern = r"\[progress:checkpoint\] bytes=(\d+) seconds=\d+(?:\.\d+)? segments=(\d+)"
    parsed = [re.fullmatch(pattern, line) for line in lines]
    assert all(parsed)
    assert [int(match.group(2)) for match in parsed if match] == [1, 2]
    last_bytes = int(parsed[-1].group(1))  # type: ignore[union-attr]
    assert last_bytes == len(_checkpoint(tmp_path).read_bytes())


def test_a_soft_mismatch_is_refused_before_term_extraction(tmp_path: Path) -> None:
    """SPEC-029 §2.1 (owner decision 2026-11-10): the same refusal, before any model call."""
    make_indexed_epub(tmp_path / "book.epub")
    glossary = GlossarySpec(extract=True)
    _translate(tmp_path, RecordingFactory(), glossary=glossary)
    shutil.rmtree(tmp_path / ".bookweaver_glossaries")

    again = RecordingFactory()
    with pytest.raises(CheckpointMismatchError, match="Checkpoint mismatch: effort$"):
        _translate(tmp_path, again, glossary=glossary, model=ModelSpec(effort="medium"))
    assert again.requests == [] and again.created == []


def test_force_still_accepts_a_soft_mismatch(tmp_path: Path) -> None:
    make_epub(tmp_path / "book.epub")
    _translate(tmp_path, RecordingFactory())

    result = _translate(
        tmp_path,
        RecordingFactory(),
        model=ModelSpec(effort="medium"),
        resume=ResumePolicy(force=True),
    )
    assert result.resumed_segments == 2


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
