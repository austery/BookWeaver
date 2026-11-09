"""Invocation evidence through the declared factory Interface, without live calls."""

from collections.abc import Sequence
from pathlib import Path
import json

import pytest

from ai.checkpoint_store import CheckpointMismatchError
from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ModelSpec,
    ProviderSpec,
    ResumePolicy,
    TranslationOrchestrator,
)
from ai.ports.provider import ITranslationProvider, ProviderUnavailableError
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_orchestration import make_epub, make_indexed_epub


class AuditedFactory(RecordingFactory):
    def __init__(self, *, fail_protocol: str | None = None, fail_audit: bool = False) -> None:
        super().__init__()
        self.audits: list[dict[str, object]] = []
        self.fail_protocol = fail_protocol
        self.fail_audit = fail_audit

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        provider = super().create(
            model,
            protocol=protocol,
            config=config,
            allow_paid_api=allow_paid_api,
            remaining_chars=remaining_chars,
        )
        fail = self.fail_protocol == protocol

        class Runtime(ITranslationProvider):
            runtime_version = "offline-runtime-1"

            def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
                if fail:
                    raise ProviderUnavailableError("synthetic execution failure")
                return provider.translate_batch(segments, system_prompt=system_prompt)

        return Runtime()

    def usage_snapshot(self) -> tuple[str, dict[str, int | None]]:
        return "offline-run", {"request_count": len(self.requests), "input_tokens": None}

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        assert runtime is not None
        self.audits.append(runtime)
        if self.fail_audit:
            raise OSError("synthetic audit failure")


@pytest.mark.parametrize("failure", [None, "delimiter", "segment_tags"])
def test_factory_audit_finalizes_glossary_and_translation(
    tmp_path: Path, failure: str | None
) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory(fail_protocol=failure)
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={}, glossary=GlossarySpec(extract=True))
    if failure:
        with pytest.raises(ProviderUnavailableError):
            app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    else:
        app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert len(factory.audits) == 1
    assert factory.audits[0]["runtime_version"] == "offline-runtime-1"
    assert factory.audits[0]["profile"] == ("pro" if failure == "delimiter" else "flash")


@pytest.mark.parametrize("fail_execution", [False, True])
def test_audit_failure_is_visible_without_masking_execution(
    tmp_path: Path, fail_execution: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = AuditedFactory(
        fail_protocol="segment_tags" if fail_execution else None, fail_audit=True
    )
    with pytest.raises(ProviderUnavailableError if fail_execution else OSError) as caught:
        TranslationOrchestrator(provider_factory=factory).translate(
            source, tmp_path / "out.epub", EpubTranslationOptions(config={}), input_format="epub"
        )
    if fail_execution:
        assert "Invocation audit also failed: OSError" in caught.value.__notes__
    assert len(factory.audits) == 1
    assert "[progress:done]" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "provider,model", [("gemini", "gemini-2.5-flash"), ("anthropic", "claude-sonnet-5-5")]
)
def test_injected_usage_and_version_reach_checkpoint_and_full_resume(
    tmp_path: Path, provider: str, model: str
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={}, provider=ProviderSpec(name=provider))
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    before = checkpoint.read_bytes()
    data = json.loads(before)
    assert all(
        record["runtime_version"] == "offline-runtime-1" for record in data["segments"].values()
    )
    assert {
        (record["provider"], record["backend"], record["model"])
        for record in data["segments"].values()
    } == {(provider, "any_llm", model)}
    assert "offline-run" in data["paid_usage_by_run"]
    assert data["paid_usage_by_run"]["offline-run"]["input_tokens"] is None
    created = len(factory.created)
    result = app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert result.resumed_segments == 2
    assert len(factory.created) == created
    assert checkpoint.read_bytes() == before
    assert factory.audits[-1]["runtime_version"] is None


@pytest.mark.parametrize("construction_failure", [False, True])
def test_audit_never_borrows_identity_from_another_request(
    tmp_path: Path, construction_failure: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)

    class Factory(AuditedFactory):
        def create(
            self,
            model: ResolvedModel,
            *,
            protocol: str,
            config: dict[str, object],
            allow_paid_api: bool,
            remaining_chars: int,
        ) -> ITranslationProvider:
            if protocol == "segment_tags":
                raise ProviderUnavailableError("translation construction failed")
            return super().create(
                model,
                protocol=protocol,
                config=config,
                allow_paid_api=allow_paid_api,
                remaining_chars=remaining_chars,
            )

    factory = Factory(fail_protocol=None if construction_failure else "delimiter")
    with pytest.raises(ProviderUnavailableError):
        TranslationOrchestrator(provider_factory=factory).translate(
            source,
            tmp_path / "out.epub",
            EpubTranslationOptions(
                config={}, model=ModelSpec(effort="high"), glossary=GlossarySpec(extract=True)
            ),
            input_format="epub",
        )
    notice = capsys.readouterr().out
    assert "Term extraction uses gemini-4-argon-low" in notice
    assert "gemini-3.8-flash-high" in notice
    audit = factory.audits[-1]
    assert audit["profile"] == ("flash" if construction_failure else "pro")
    assert audit["runtime_version"] == (None if construction_failure else "offline-runtime-1")
    assert audit["requested_effort"] == ("high" if construction_failure else None)
    assert audit["effective_effort"] == ("high" if construction_failure else "low")
    assert (
        audit["preset_status"] == "experiment"
    )  # flash/high and pro/low are both experiment presets
    assert audit["extraction_model"] == "gemini-4-argon-low"
    assert audit["extraction_preset_status"] == "experiment"


def test_extraction_model_choice_overrides_the_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    options = EpubTranslationOptions(
        config={"terminology_extraction": {"enabled": True, "extraction_model": "pro"}},
        glossary=GlossarySpec(extract=True, extraction_model="flash"),
    )
    TranslationOrchestrator(provider_factory=factory).translate(
        source, tmp_path / "out.epub", options, input_format="epub"
    )
    assert factory.audits[-1]["extraction_model"] == "gemini-3.8-flash-low"
    assert "Term extraction uses gemini-3.8-flash-low" in capsys.readouterr().out


def test_run_reports_saved_terms_it_reuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={}, glossary=GlossarySpec(extract=True))
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    capsys.readouterr()
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert "Reusing saved terms extracted with gemini-4-argon-low" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extraction_model,expected", [("flash", "gpt-6-luna-low"), ("pro", "gpt-6.1-sol-low")]
)
def test_a_codex_run_extracts_terms_on_codex_and_records_its_runtime(
    tmp_path: Path, extraction_model: str, expected: str
) -> None:
    """Astra is the translation model here, yet a bare tier never spends Astra on extraction."""
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    TranslationOrchestrator(provider_factory=factory).translate(
        source,
        tmp_path / "out.epub",
        EpubTranslationOptions(
            config={},
            model=ModelSpec(preset="codex-gpt-6-astra-low"),
            glossary=GlossarySpec(extract=True, extraction_model=extraction_model),
        ),
        input_format="epub",
    )
    assert factory.audits[-1]["extraction_model"] == expected
    assert factory.audits[-1]["runtime"] == "codex"
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    records = json.loads(checkpoint.read_text())["segments"].values()
    assert {(r["provider"], r["backend"], r["model"]) for r in records} == {
        ("cli", "codex", "gpt-6-astra-low")
    }


def test_an_antigravity_checkpoint_does_not_silently_resume_on_codex(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    app = TranslationOrchestrator(provider_factory=AuditedFactory())
    output = tmp_path / "out.epub"
    app.translate(source, output, EpubTranslationOptions(config={}), input_format="epub")
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    before = checkpoint.read_bytes()
    assert {r["backend"] for r in json.loads(before)["segments"].values()} == {"antigravity"}

    with pytest.raises(CheckpointMismatchError, match="model"):
        app.translate(
            source,
            output,
            EpubTranslationOptions(config={}, model=ModelSpec(preset="codex-gpt-6-luna-low")),
            input_format="epub",
        )
    assert checkpoint.read_bytes() == before
    continued = app.translate(
        source,
        output,
        EpubTranslationOptions(
            config={},
            model=ModelSpec(preset="codex-gpt-6-luna-low"),
            resume=ResumePolicy(force=True),
        ),
        input_format="epub",
    )
    assert continued.resumed_segments > 0


def test_a_codex_model_change_stops_before_extraction_spends_quota(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    output = tmp_path / "out.epub"
    app.translate(source, output, EpubTranslationOptions(config={}), input_format="epub")
    calls = len(factory.requests)

    with pytest.raises(CheckpointMismatchError, match="gemini-3.8-flash-low"):
        app.translate(
            source,
            output,
            EpubTranslationOptions(
                config={},
                model=ModelSpec(preset="codex-gpt-6-luna-low"),
                glossary=GlossarySpec(extract=True),
            ),
            input_format="epub",
        )
    assert len(factory.requests) == calls


def test_a_metered_vendor_switch_keeps_its_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    app = TranslationOrchestrator(provider_factory=AuditedFactory())
    output = tmp_path / "out.epub"
    for preset in ("gemini-flash", "anthropic-flash"):
        app.translate(
            source,
            output,
            EpubTranslationOptions(config={}, model=ModelSpec(preset=preset)),
            input_format="epub",
        )
    assert "Mixed-model continuation" in capsys.readouterr().out


@pytest.mark.parametrize(
    "next_preset", ["agy-flash-low", "codex-gpt-6.1-terra-low", "anthropic-flash"]
)
def test_a_resume_leaving_a_codex_model_stops(tmp_path: Path, next_preset: str) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    app = TranslationOrchestrator(provider_factory=AuditedFactory())
    output = tmp_path / "out.epub"
    first = EpubTranslationOptions(config={}, model=ModelSpec(preset="codex-gpt-6-luna-low"))
    app.translate(source, output, first, input_format="epub")
    with pytest.raises(CheckpointMismatchError, match="gpt-6-luna-low"):
        app.translate(
            source,
            output,
            EpubTranslationOptions(config={}, model=ModelSpec(preset=next_preset)),
            input_format="epub",
        )


def test_a_retired_model_keeps_its_warning_when_resuming_on_codex(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    app = TranslationOrchestrator(provider_factory=AuditedFactory())
    output = tmp_path / "out.epub"
    app.translate(source, output, EpubTranslationOptions(config={}), input_format="epub")
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    data = json.loads(checkpoint.read_text())
    for record in data["segments"].values():
        record["model"] = "gemini-3.1-pro-low"
    checkpoint.write_text(json.dumps(data))
    app.translate(
        source,
        output,
        EpubTranslationOptions(config={}, model=ModelSpec(preset="codex-gpt-6-luna-low")),
        input_format="epub",
    )
    assert "Mixed-model continuation" in capsys.readouterr().out


@pytest.mark.parametrize(
    "first,second",
    [
        ("agy-flash-low", "claude-sonnet-5-5-low"),
        ("claude-sonnet-5-5-low", "agy-flash-low"),
        ("claude-sonnet-5-5-low", "codex-gpt-6-luna-low"),
    ],
)
def test_a_resume_crossing_a_claude_code_model_stops_before_any_request(
    tmp_path: Path, first: str, second: str
) -> None:
    """These presets share the flash/low identity; a restore would hide that no call was made."""
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    output = tmp_path / "out.epub"
    app.translate(
        source,
        output,
        EpubTranslationOptions(config={}, model=ModelSpec(preset=first)),
        input_format="epub",
    )
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    before = checkpoint.read_bytes()
    calls = len(factory.requests)

    with pytest.raises(CheckpointMismatchError, match="model"):
        app.translate(
            source,
            output,
            EpubTranslationOptions(
                config={}, model=ModelSpec(preset=second), glossary=GlossarySpec(extract=True)
            ),
            input_format="epub",
        )
    assert len(factory.requests) == calls  # term extraction spent nothing either
    assert checkpoint.read_bytes() == before


def test_a_claude_code_checkpoint_resumes_on_the_same_preset(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_indexed_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={}, model=ModelSpec(preset="claude-sonnet-5-5-low"))
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    records = json.loads(next(tmp_path.rglob("checkpoint.json")).read_text())["segments"].values()
    assert {(r["provider"], r["backend"], r["model"]) for r in records} == {
        ("cli", "claude-code", "claude-sonnet-5-5-low")
    }
    calls = len(factory.requests)

    restored = app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert restored.resumed_segments == len(records)
    assert len(factory.requests) == calls
