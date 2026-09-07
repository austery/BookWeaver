"""Public-boundary regressions reproduced during PR 25 review; no live transports."""

import os
import zipfile
from pathlib import Path
from collections.abc import Sequence

import pytest

from ai.antigravity_provider import AntigravityProvider
from ai.checkpoint_store import CheckpointError, CheckpointMismatchError
from ai.model_profiles import ResolvedModel
from ai.orchestration import (
    TranslationOrchestrator,
    EpubTranslationOptions,
    MarkdownTranslationOptions,
    GlossarySpec,
    ResumePolicy,
    QualityPolicy,
)
from ai.ports.provider import ITranslationProvider, ProviderAuthenticationError
from tests.unit.test_orchestration import make_epub


class OfflineFactory:
    def __init__(self, executable: Path | None = None) -> None:
        self.calls: list[str] = []
        self.executable = executable

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        if self.executable:
            return AntigravityProvider(model, protocol=protocol, executable=str(self.executable))
        calls = self.calls

        class Provider(ITranslationProvider):
            def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
                calls.append(protocol)
                if protocol == "delimiter":
                    return ['{"critical_terminology": []}']
                return ["花园大门敞开着。" for _ in segments]

        return Provider()


def revise_source(source: Path) -> None:
    stat = source.stat()
    with zipfile.ZipFile(source) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(source, "w") as archive:
        for info, content in entries:
            archive.writestr(info, content.replace(b"was open.", b"was shut."))
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert source.stat().st_size == stat.st_size


@pytest.mark.parametrize("batch_chars", [30, 60000])
def test_authentication_status_stops_application_without_persisting(
    tmp_path: Path, batch_chars: int
) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    executable, calls = tmp_path / "agy", tmp_path / "calls"
    executable.write_text(
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        'if sys.argv[1:] == ["--version"]: print("1.1.27")\n'
        'elif sys.argv[1:] == ["models"]: print("gemini-3.8-flash-low")\n'
        "else:\n"
        f'    with Path({str(calls)!r}).open("a") as f: f.write("call\\n")\n'
        '    print("not logged in")\n'
    )
    executable.chmod(0o700)
    with pytest.raises(ProviderAuthenticationError):
        TranslationOrchestrator(provider_factory=OfflineFactory(executable)).translate(
            source,
            output,
            EpubTranslationOptions(config={}, quality=QualityPolicy(max_batch_chars=batch_chars)),
            input_format="epub",
        )
    assert calls.read_text() == "call\n"
    assert not output.exists()
    assert not list(tmp_path.rglob("checkpoint.json"))


def test_content_change_with_same_metadata_cannot_restore(tmp_path: Path) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    factory = OfflineFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(config={})
    app.translate(source, output, options, input_format="epub")
    before = output.read_bytes()
    revise_source(source)
    with pytest.raises(CheckpointMismatchError):
        app.translate(source, output, options, input_format="epub")
    assert output.read_bytes() == before
    assert factory.calls == ["segment_tags"]


def test_identical_content_moved_and_touched_can_restore(tmp_path: Path) -> None:
    source, moved, output = tmp_path / "book.epub", tmp_path / "moved.epub", tmp_path / "out.epub"
    make_epub(source)
    factory = OfflineFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    options = EpubTranslationOptions(
        config={}, resume=ResumePolicy(checkpoint_dir=tmp_path / "checkpoint")
    )
    app.translate(source, output, options, input_format="epub")
    moved.write_bytes(source.read_bytes())
    os.utime(moved, ns=(1, 1))
    assert app.translate(moved, output, options, input_format="epub").resumed_segments == 2
    assert factory.calls == ["segment_tags"]


@pytest.mark.parametrize("corrupt", [False, True])
def test_checkpoint_preflight_precedes_glossary_requests(tmp_path: Path, corrupt: bool) -> None:
    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    factory = OfflineFactory()
    app = TranslationOrchestrator(provider_factory=factory)
    app.translate(source, output, EpubTranslationOptions(config={}), input_format="epub")
    if corrupt:
        next(tmp_path.rglob("checkpoint.json")).write_text("{broken")
    else:
        revise_source(source)
    with pytest.raises(CheckpointError):
        app.translate(
            source,
            output,
            EpubTranslationOptions(config={}, glossary=GlossarySpec(extract=True)),
            input_format="epub",
        )
    assert factory.calls == ["segment_tags"]


@pytest.mark.parametrize("directory", [False, True])
def test_unsupported_markdown_preserves_destination(tmp_path: Path, directory: bool) -> None:
    source = tmp_path / ("pages" if directory else "notes.md")
    if directory:
        source.mkdir()
    else:
        source.write_text("Source content")
        (tmp_path / "page0001.md").write_text("Unrelated page must not be translated")
    output = tmp_path / "out.md"
    output.write_text("Existing destination")
    factory = OfflineFactory()
    with pytest.raises(ValueError):
        TranslationOrchestrator(provider_factory=factory).translate(
            source, output, MarkdownTranslationOptions(config={}), input_format="markdown"
        )
    assert output.read_text() == "Existing destination"
    assert not factory.calls


def test_cross_provider_resume_preserves_provenance_and_paid_noop(tmp_path: Path) -> None:
    import json
    from dataclasses import replace
    from ai.orchestration import ProviderSpec
    from ai.ports.provider import ProviderUnavailableError

    source, output = tmp_path / "book.epub", tmp_path / "out.epub"
    make_epub(source)
    options = EpubTranslationOptions(config={}, quality=QualityPolicy(max_batch_chars=30))

    class InterruptFactory(OfflineFactory):
        def create(
            self,
            model: ResolvedModel,
            *,
            protocol: str,
            config: dict[str, object],
            allow_paid_api: bool,
            remaining_chars: int,
        ) -> ITranslationProvider:
            calls = self.calls

            class Provider(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    calls.append(protocol)
                    if len(calls) == 2:
                        raise ProviderUnavailableError("interrupted")
                    return ["花园大门敞开着。"]

            return Provider()

    with pytest.raises(ProviderUnavailableError):
        TranslationOrchestrator(provider_factory=InterruptFactory()).translate(
            source, output, options, input_format="epub"
        )
    api = replace(
        options,
        provider=ProviderSpec(name="api", allow_paid_api=True),
        resume=ResumePolicy(force=True),
    )
    factory = OfflineFactory()
    result = TranslationOrchestrator(provider_factory=factory).translate(
        source, output, api, input_format="epub"
    )
    assert result.resumed_segments == 1
    checkpoint = next(tmp_path.rglob("checkpoint.json"))
    before = checkpoint.read_bytes()
    records = json.loads(before)["segments"].values()
    assert {record["provider"] for record in records} == {"cli", "api"}
    assert {record["model"] for record in records} == {"gemini-3.8-flash-low", "gemini-2.5-flash"}
    # The production paid factory must not ask permission or construct a client on full restore.
    result = TranslationOrchestrator().translate(
        source, output, replace(api, provider=ProviderSpec(name="api")), input_format="epub"
    )
    assert result.resumed_segments == 2
    assert checkpoint.read_bytes() == before
    assert factory.calls == ["segment_tags"]


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("outcome", ["denied", "failed", "success"])
def test_paid_glossary_path_is_authorized_and_single_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, standalone: bool, outcome: str
) -> None:
    import sys
    import json
    import importlib.util
    from google import genai
    from google.genai import types
    from ai.orchestration import ProviderSpec
    from ai.runtime_factory import PaidAuthorizationError
    from ai.ports.provider import ProviderUnavailableError

    source, output = (
        tmp_path / "book.epub",
        tmp_path / ("glossary.json" if standalone else "out.epub"),
    )
    make_epub(source)
    calls: list[str] = []
    constructed: list[bool] = []

    class Models:
        def generate_content(
            self, *, model: str, contents: str, config: types.GenerateContentConfig
        ) -> types.GenerateContentResponse:
            calls.append(model)
            assert config.http_options is not None
            assert config.http_options.retry_options is not None
            assert config.http_options.retry_options.attempts == 1
            if outcome == "failed":
                raise RuntimeError("synthetic transport failure")
            text = (
                '{"critical_terminology": []}'
                if model == "gemini-2.5-pro"
                else '<segment id="1">花园大门敞开着。</segment><segment id="2">月亮从山丘上升起。</segment>'
            )
            return types.GenerateContentResponse(
                candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=text)]))],
                usage_metadata=types.GenerateContentResponseUsageMetadata(
                    prompt_token_count=10, candidates_token_count=5
                ),
            )

    class Client:
        def __init__(self, *, api_key: str | None, http_options: types.HttpOptions) -> None:
            constructed.append(True)
            assert http_options.retry_options is not None
            assert http_options.retry_options.attempts == 1
            self.models = Models()

    monkeypatch.setattr(genai, "Client", Client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-secret")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    def run() -> None:
        if standalone:
            spec = importlib.util.spec_from_file_location(
                "standalone_glossary",
                Path(__file__).resolve().parents[2] / "00_extract_glossary.py",
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            monkeypatch.setattr(module, "load_runtime_config", lambda: {})
            args = ["glossary", str(source), "--output", str(output), "--provider", "api"]
            if outcome != "denied":
                args.append("--allow-paid-api")
            monkeypatch.setattr(sys, "argv", args)
            module.main()
        else:
            TranslationOrchestrator().translate(
                source,
                output,
                EpubTranslationOptions(
                    config={},
                    provider=ProviderSpec(name="api", allow_paid_api=outcome != "denied"),
                    glossary=GlossarySpec(extract=True),
                ),
                input_format="epub",
            )

    if outcome == "denied":
        with pytest.raises(PaidAuthorizationError):
            run()
        assert not constructed and not calls
    elif outcome == "failed":
        with pytest.raises(ProviderUnavailableError):
            run()
        assert calls == ["gemini-2.5-pro"]
        assert not output.exists()
        audit = json.loads(next((tmp_path / ".bookweaver_runs").glob("*.json")).read_text())
        assert audit["requests"][0]["state"] == "failed"
    else:
        run()
        assert calls == (
            ["gemini-2.5-pro"] if standalone else ["gemini-2.5-pro", "gemini-2.5-flash"]
        )
        assert output.exists()
        audit = json.loads(next((tmp_path / ".bookweaver_runs").glob("*.json")).read_text())
        assert audit["summary"]["input_tokens"] == 10 * len(calls)
