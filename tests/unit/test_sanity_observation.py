"""Sanity probe is observational: it records warnings for review and never halts a run."""

import json
from pathlib import Path

import pytest

import ai.orchestration as orchestration
from ai.orchestration import (
    EpubTranslationOptions,
    QualityPolicy,
    ResumePolicy,
    SanityWarning,
    TranslationOrchestrator,
    _SanityWarningLog,
)
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_orchestration import make_epub

# Both fixture paragraphs are >= 20 chars, so a 200-char output trips length_ratio.
_RUNAWAY = "跑" * 200


def _translate(
    tmp_path: Path,
    factory: RecordingFactory,
    *,
    sanity_probe: bool = True,
    resume: ResumePolicy | None = None,
) -> Path:
    source = tmp_path / "book.epub"
    if not source.exists():
        make_epub(source)
    output = tmp_path / "out.epub"
    TranslationOrchestrator(provider_factory=factory).translate(
        source,
        output,
        EpubTranslationOptions(
            config={},
            quality=QualityPolicy(sanity_probe=sanity_probe),
            resume=resume or ResumePolicy(checkpoint_dir=tmp_path / "ckpt"),
        ),
        input_format="epub",
    )
    return output


def _warnings(path: Path) -> list[dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))["warnings"]


def test_suspicious_batch_completes_and_records_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = _translate(tmp_path, RecordingFactory(translation=_RUNAWAY))

    assert output.exists()
    checkpoint = json.loads((tmp_path / "ckpt" / "checkpoint.json").read_text())
    assert checkpoint["translated_segment_count"] == 2
    entries = _warnings(tmp_path / "ckpt" / "warnings.json")
    assert {entry["check"] for entry in entries} == {"length_ratio"}
    assert {entry["segment_id"] for entry in entries} == set(checkpoint["segments"])
    out = capsys.readouterr().out
    assert out.count("[progress:sanity_warning]") == 2
    assert "[progress:sanity_summary] flagged=2" in out


def test_full_resume_keeps_prior_warnings_without_provider_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _translate(tmp_path, RecordingFactory(translation=_RUNAWAY))
    capsys.readouterr()

    resumed = RecordingFactory()
    _translate(tmp_path, resumed)

    assert resumed.requests == []
    assert len(_warnings(tmp_path / "ckpt" / "warnings.json")) == 2
    assert "[progress:sanity_summary] flagged=2" in capsys.readouterr().out


def test_clean_run_writes_no_warning_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _translate(tmp_path, RecordingFactory())

    assert not (tmp_path / "ckpt" / "warnings.json").exists()
    out = capsys.readouterr().out
    assert "[progress:sanity_summary] flagged=0" in out
    assert "sanity_warning]" not in out


def test_without_checkpoint_warnings_sit_beside_output(tmp_path: Path) -> None:
    output = _translate(
        tmp_path, RecordingFactory(translation=_RUNAWAY), resume=ResumePolicy(enabled=False)
    )

    assert len(_warnings(output.with_name("out.epub.warnings.json"))) == 2
    assert not (tmp_path / "ckpt").exists()


def test_disabled_probe_records_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _translate(tmp_path, RecordingFactory(translation=_RUNAWAY), sanity_probe=False)

    assert not (tmp_path / "ckpt" / "warnings.json").exists()
    assert "sanity_" not in capsys.readouterr().out


def _warning(segment_id: str, check: str = "length_ratio") -> SanityWarning:
    return SanityWarning(segment_id, "1/1", check, "detail", "src", "tgt")


def test_log_seeds_restored_and_replaces_retranslated_ones(tmp_path: Path) -> None:
    path = tmp_path / "warnings.json"
    log = _SanityWarningLog(path, restored=[_warning("a"), _warning("b")])
    assert log.count == 2
    log.record(["b"], [])  # "b" retranslated cleanly
    log.record(["d"], [_warning("d", "cjk_density")])

    assert sorted((e["segment_id"], e["check"]) for e in _warnings(path)) == [
        ("a", "length_ratio"),
        ("d", "cjk_density"),
    ]


def test_log_replaces_stale_or_unreadable_file_on_open(tmp_path: Path) -> None:
    path = tmp_path / "warnings.json"
    path.write_text("{not json")

    log = _SanityWarningLog(path, restored=[_warning("a")])

    assert log.count == 1
    assert [entry["segment_id"] for entry in _warnings(path)] == ["a"]

    clean = _SanityWarningLog(path)
    assert clean.count == 0
    assert _warnings(path) == []


def test_log_write_failure_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    log = _SanityWarningLog(blocker / "warnings.json")

    log.record(["a"], [_warning("a")])

    assert "[progress:sanity_warning_log]" in capsys.readouterr().err


def test_log_replace_and_cleanup_failure_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(orchestration.os, "replace", deny)
    monkeypatch.setattr(Path, "unlink", deny)
    log = _SanityWarningLog(tmp_path / "warnings.json")

    log.record(["a"], [_warning("a")])

    err = capsys.readouterr().err
    assert err.count("[progress:sanity_warning_log]") == 2
    assert "temporary file not removed" in err


def test_resume_recovers_warnings_lost_after_checkpoint_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_replace = orchestration.os.replace

    def fail_warning_replace(src: object, dst: object) -> None:
        if Path(str(dst)).name == "warnings.json":
            raise PermissionError("denied")
        real_replace(src, dst)

    monkeypatch.setattr(orchestration.os, "replace", fail_warning_replace)
    _translate(tmp_path, RecordingFactory(translation=_RUNAWAY))
    assert not (tmp_path / "ckpt" / "warnings.json").exists()
    monkeypatch.setattr(orchestration.os, "replace", real_replace)
    capsys.readouterr()

    resumed = RecordingFactory()
    _translate(tmp_path, resumed)

    assert resumed.requests == []
    entries = _warnings(tmp_path / "ckpt" / "warnings.json")
    assert {(entry["batch"], entry["check"]) for entry in entries} == {("restored", "length_ratio")}
    assert len(entries) == 2
    assert "[progress:sanity_summary] flagged=2" in capsys.readouterr().out


def test_cleanup_failure_still_produces_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace, real_unlink = orchestration.os.replace, Path.unlink

    def fail_warning_replace(src: object, dst: object) -> None:
        if Path(str(dst)).name == "warnings.json":
            raise PermissionError("denied")
        real_replace(src, dst)

    def fail_warning_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.startswith(".warnings-"):
            raise PermissionError("denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(orchestration.os, "replace", fail_warning_replace)
    monkeypatch.setattr(Path, "unlink", fail_warning_unlink)

    output = _translate(tmp_path, RecordingFactory(translation=_RUNAWAY))

    assert output.exists()
