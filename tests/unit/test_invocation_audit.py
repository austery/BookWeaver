"""Invocation evidence through the declared factory Interface, without live calls."""

from collections.abc import Sequence
from pathlib import Path
import json

import pytest

from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ProviderSpec,
    TranslationOrchestrator,
)
from ai.ports.provider import ITranslationProvider, ProviderUnavailableError
from tests.unit.test_application_contract import RecordingFactory
from tests.unit.test_orchestration import make_epub


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
    make_epub(source)
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
    tmp_path: Path, fail_execution: bool
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


def test_injected_usage_and_version_reach_checkpoint_and_full_resume(tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    make_epub(source)
    factory = AuditedFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={}, provider=ProviderSpec(name="api"))
    app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    before = checkpoint.read_bytes()
    data = json.loads(before)
    assert all(
        record["runtime_version"] == "offline-runtime-1" for record in data["segments"].values()
    )
    assert "offline-run" in data["paid_usage_by_run"]
    assert data["paid_usage_by_run"]["offline-run"]["input_tokens"] is None
    created = len(factory.created)
    result = app.translate(source, tmp_path / "out.epub", options, input_format="epub")
    assert result.resumed_segments == 2
    assert len(factory.created) == created
    assert checkpoint.read_bytes() == before
    assert factory.audits[-1]["runtime_version"] is None
