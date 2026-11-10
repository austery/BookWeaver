"""SPEC-028 Phase 2b: ``--term-panel`` on the translate command and ``runtimes.disabled``.

Through the application (``TranslationOrchestrator``), the CLI and the local API, with fake
panel members and a fake translator; no model is called.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from ai import cli, local_api, orchestration
from ai.model_profiles import CliRuntime, MeteredProvider, ResolvedModel
from ai.orchestration import (
    EpubTranslationOptions,
    GlossarySpec,
    ModelSpec,
    PanelError,
    ResumePolicy,
    TranslationOrchestrator,
    run_term_panel,
)
from ai.ports.provider import ITranslationProvider
from tests.unit.test_term_panel_runner import _PANEL, FakeMembers, _book

_EXTRACTION_REPLY = (
    '{"critical_terminology": [{"term": "garden", "suggested_translation": "园圃", '
    '"priority": "high"}]}'
)


class PanelAndTranslator(FakeMembers):
    """Panel members as in the runner tests, plus a translator and the invocation audit."""

    def __init__(self) -> None:
        super().__init__()
        self.created: list[tuple[str, str]] = []
        self.system_prompts: list[str] = []
        self.audits: list[dict[str, object]] = []

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        self.created.append((model.model_id, protocol))
        factory = self
        if protocol == "segment_tags":

            class Translator(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    factory.system_prompts.append(system_prompt)
                    return ["花园译文。" for _ in segments]

            return Translator()
        if model.model_id == "gemini-4-argon-low":  # single-model extraction (Pro)

            class Extractor(ITranslationProvider):
                def translate_batch(
                    self, segments: Sequence[str], *, system_prompt: str
                ) -> list[str]:
                    factory.calls.append(("pro", "extract"))
                    return [_EXTRACTION_REPLY]

            return Extractor()
        return super().create(
            model,
            protocol=protocol,
            config=config,
            allow_paid_api=allow_paid_api,
            remaining_chars=remaining_chars,
        )

    def usage_snapshot(self) -> tuple[str, dict[str, int | None]] | None:
        return None

    def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
        if runtime is not None:
            self.audits.append(runtime)


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "library" / "book.epub"
    path.parent.mkdir()
    _book(path)
    return path


def _translate(
    book: Path,
    output: Path,
    factory: PanelAndTranslator,
    *,
    glossary: GlossarySpec | None = None,
    config: dict[str, object] | None = None,
    resume: bool = True,
    preset: str | None = None,
) -> orchestration.TranslationSummary:
    return TranslationOrchestrator(provider_factory=factory).translate(
        book,
        output,
        EpubTranslationOptions(
            config=config if config is not None else _PANEL,
            model=ModelSpec(preset=preset),
            glossary=glossary if glossary is not None else GlossarySpec(term_panel="three-vendor"),
            resume=ResumePolicy(enabled=resume),
        ),
        input_format="epub",
    )


def test_term_panel_chooses_terms_and_translates_in_one_command(book: Path, tmp_path: Path) -> None:
    factory = PanelAndTranslator()

    summary = _translate(book, tmp_path / "out" / "book.zh.epub", factory)

    assert [kind for _, kind in factory.calls] == ["nominate"] * 3 + ["judge"] * 2
    assert summary.glossary_used is not None
    # SPEC-028 §3.7: the panel cache lives beside the EPUB, shared by every output folder.
    assert summary.glossary_used.is_relative_to(book.parent / ".bookweaver_glossaries" / "panel")
    assert "山冈" in factory.system_prompts[0]  # the judges' correction reaches the prompt
    audit = factory.audits[-1]
    assert audit["extraction_model"] is None
    panel = audit["term_panel"]
    assert isinstance(panel, dict)
    assert (panel["name"], panel["reused"]) == ("three-vendor", False)
    assert summary.glossary_used.parent.name == panel["identity"]
    assert panel["members"] == [
        {"role": "nominator", "preset": "agy-flash-low", "model": "gemini-3.8-flash-low"},
        {"role": "nominator", "preset": "codex-gpt-6.1-sol-low", "model": "gpt-6.1-sol-low"},
        {"role": "nominator", "preset": "claude-opus-5-5-low", "model": "claude-opus-5-5-low"},
        {"role": "judge", "preset": "codex-gpt-6.1-sol-low", "model": "gpt-6.1-sol-low"},
        {"role": "judge", "preset": "claude-opus-5-5-low", "model": "claude-opus-5-5-low"},
    ]


def test_a_glossary_from_the_terms_command_is_reused_without_any_member_call(
    book: Path, tmp_path: Path
) -> None:
    written = run_term_panel(book, "three-vendor", config=_PANEL, provider_factory=FakeMembers())
    factory = PanelAndTranslator()
    factory.logged_out = {"gpt", "claude"}  # a cached glossary needs no member

    summary = _translate(book, tmp_path / "out" / "book.zh.epub", factory, resume=False)

    assert summary.glossary_used == written
    assert factory.calls == [] and factory.checked == []
    assert {protocol for _, protocol in factory.created} == {"segment_tags"}
    panel = factory.audits[-1]["term_panel"]
    assert isinstance(panel, dict) and panel["reused"] is True


def test_resume_with_the_panel_restores_every_segment_with_no_call(
    book: Path, tmp_path: Path
) -> None:
    output = tmp_path / "out" / "book.zh.epub"
    _translate(book, output, PanelAndTranslator())
    factory = PanelAndTranslator()

    summary = _translate(book, output, factory)

    assert summary.translated_segments == summary.resumed_segments == summary.total_segments
    assert factory.calls == [] and factory.created == []


def test_a_panel_glossary_resumes_a_run_that_named_it_with_glossary(
    book: Path, tmp_path: Path
) -> None:
    """Same file, same prompt: `--glossary PATH` and `--term-panel NAME` share a checkpoint."""
    written = run_term_panel(book, "three-vendor", config=_PANEL, provider_factory=FakeMembers())
    output = tmp_path / "out" / "book.zh.epub"
    _translate(book, output, PanelAndTranslator(), glossary=GlossarySpec(path=written))
    factory = PanelAndTranslator()

    summary = _translate(book, output, factory)

    assert summary.resumed_segments == summary.total_segments
    assert factory.created == []


@pytest.mark.parametrize(
    "glossary,flag",
    [
        (GlossarySpec(path=Path("g.json"), term_panel="three-vendor"), "--glossary"),
        (
            GlossarySpec(extract=True, extraction_model="flash", term_panel="three-vendor"),
            "--extraction-model",
        ),
        (GlossarySpec(extract=True, term_panel="three-vendor"), "--extract-glossary"),
        (GlossarySpec(mode="deep-scan", term_panel="three-vendor"), "Deep Scan"),
        (GlossarySpec(term_panel="missing"), "Unknown Term Panel 'missing'"),
    ],
)
def test_conflicts_and_unsupported_panels_fail_before_any_call(
    book: Path, tmp_path: Path, glossary: GlossarySpec, flag: str
) -> None:
    factory = PanelAndTranslator()

    with pytest.raises(PanelError, match=flag):
        _translate(book, tmp_path / "out.epub", factory, glossary=glossary)
    assert factory.created == []


def test_the_panel_replaces_extraction_the_configuration_turns_on(
    book: Path, tmp_path: Path
) -> None:
    factory = PanelAndTranslator()
    config = {**_PANEL, "terminology_extraction": {"enabled": True, "extraction_model": "pro"}}

    _translate(book, tmp_path / "out.epub", factory, config=config)

    assert ("pro", "extract") not in factory.calls
    assert "gemini-4-argon-low" not in {model for model, _ in factory.created}


def test_a_disabled_member_stops_the_panel_and_the_audit_names_the_panel(
    book: Path, tmp_path: Path
) -> None:
    factory = PanelAndTranslator()
    config = {**_PANEL, "runtimes": {"disabled": ["codex"]}}

    with pytest.raises(
        PanelError, match=r"member codex-gpt-6.1-sol-low \(gpt-6.1-sol-low\) runs on codex"
    ):
        _translate(book, tmp_path / "out.epub", factory, config=config)
    # Members are constructed (no side effect) but none is checked or called.
    assert factory.calls == [] and factory.checked == []
    assert "segment_tags" not in {protocol for _, protocol in factory.created}
    panel = factory.audits[-1]["term_panel"]
    assert isinstance(panel, dict) and panel["name"] == "three-vendor"


def test_a_cached_panel_glossary_resumes_after_a_member_runtime_is_disabled(
    book: Path, tmp_path: Path
) -> None:
    """SPEC-028 §3.12: availability is checked only when a member must be called."""
    run_term_panel(book, "three-vendor", config=_PANEL, provider_factory=FakeMembers())
    factory = PanelAndTranslator()
    config = {**_PANEL, "runtimes": {"disabled": ["codex", "claude-code"]}}

    summary = _translate(book, tmp_path / "out.epub", factory, config=config)

    assert summary.translated_segments == summary.total_segments
    assert factory.calls == []


def test_a_member_whose_replies_are_saved_may_be_disabled_on_a_rerun(
    book: Path, tmp_path: Path
) -> None:
    """SPEC-028 §3.7 and §3.12: a stopped panel reruns only the missing members."""
    broken = PanelAndTranslator()
    broken.broken_judge = "claude"
    with pytest.raises(PanelError, match="judge reply 1 is unusable"):
        _translate(book, tmp_path / "out.epub", broken)
    factory = PanelAndTranslator()
    config = {**_PANEL, "runtimes": {"disabled": ["codex"]}}  # its replies are all saved

    summary = _translate(book, tmp_path / "out.epub", factory, config=config)

    assert factory.calls == [("claude", "judge")]
    assert factory.checked == ["claude-opus-5-5-low"]
    assert summary.translated_segments == summary.total_segments


def test_a_disabled_translation_runtime_fails_before_any_call(book: Path, tmp_path: Path) -> None:
    factory = PanelAndTranslator()
    config = {"runtimes": {"disabled": ["antigravity"]}}

    with pytest.raises(
        ValueError, match=r"translation model \(gemini-3.8-flash-low\) runs on antigravity"
    ):
        _translate(book, tmp_path / "out.epub", factory, config=config, glossary=GlossarySpec())
    assert factory.created == []


def test_the_schema_names_every_runtime_and_nothing_else() -> None:
    schema = json.loads((Path(orchestration.__file__).parent / "config_schema.json").read_text())
    names = schema["properties"]["runtimes"]["properties"]["disabled"]["items"]["enum"]
    assert set(names) == set(get_args(CliRuntime)) | set(get_args(MeteredProvider))
    with pytest.raises(ValueError, match="Unsupported value"):
        orchestration.validate_config({"runtimes": {"disabled": ["copilot"]}})


# ── CLI and local API ─────────────────────────────────────────


def test_cli_passes_the_panel_and_reports_a_conflict_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: list[EpubTranslationOptions] = []
    source = tmp_path / "book.epub"
    source.write_bytes(b"epub")

    def fake_translate(path: Path, output: Path, options: EpubTranslationOptions) -> None:
        captured.append(options)
        raise PanelError("--term-panel chooses the terms; drop --glossary")

    monkeypatch.setattr(cli.orchestration, "translate_epub", fake_translate)
    with pytest.raises(SystemExit) as exit_info:
        cli.main([str(source), "--output", "o.epub", "--term-panel", "three-vendor"])

    assert exit_info.value.code == 2
    assert captured[0].glossary.term_panel == "three-vendor"
    assert "bookweaver: --term-panel chooses the terms" in capsys.readouterr().err


def test_presets_listing_marks_a_disabled_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(orchestration, "configured_disabled_runtimes", lambda: frozenset({"codex"}))
    cli.main(["presets", "--json"])
    listed = {p["name"]: p["status"] for p in json.loads(capsys.readouterr().out)}
    assert listed["codex-gpt-6.1-sol-low"] == "disabled"
    assert listed["agy-flash-low"] == "default"
    cli.main(["presets"])
    row = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("codex-gpt-6.1-sol-low ")
    )
    assert row.split()[6] == "disabled"


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(orchestration, "configured_disabled_runtimes", lambda: frozenset({"codex"}))
    app = local_api.create_app(
        state_dir=tmp_path / "state",
        child_command=(sys.executable, "-c", "raise SystemExit(0)"),
        library_dir=tmp_path / "library",
    )
    yield TestClient(app, base_url="http://127.0.0.1:8765")


def test_local_api_leaves_disabled_presets_out_and_refuses_them(
    api: TestClient, tmp_path: Path
) -> None:
    names = {preset["name"] for preset in api.get("/presets").json()}
    assert "agy-flash-low" in names
    assert not any(name.startswith("codex-") for name in names)

    source = tmp_path / "book.epub"
    _book(source)
    response = api.post(
        "/runs/upload",
        files={"file": ("book.epub", source.read_bytes(), "application/epub+zip")},
        data={"preset": "codex-gpt-6.1-sol-low"},
    )
    assert response.status_code == 422  # not among the dropdown's choices
    assert not (tmp_path / "library").exists() or not any((tmp_path / "library").rglob("*.epub"))


def test_post_runs_refuses_a_disabled_preset(api: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    _book(source)

    response = api.post(
        "/runs",
        json={
            "source": str(source),
            "output": str(tmp_path / "out.epub"),
            "preset": "codex-gpt-6.1-sol-low",
        },
    )

    assert response.status_code == 400
    assert "runtimes.disabled" in response.json()["detail"]


def test_the_upload_has_no_default_when_the_default_runtime_is_disabled(tmp_path: Path) -> None:
    app = local_api.create_app(
        state_dir=tmp_path / "state",
        library_dir=tmp_path / "library",
        disabled_runtimes=frozenset({"antigravity"}),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    schema = client.get("/openapi.json").json()
    form = next(
        value for name, value in schema["components"]["schemas"].items() if "upload" in name.lower()
    )
    assert form["properties"]["preset"].get("default") is None  # no silent default
    choices = schema["components"]["schemas"]["PresetName"]["enum"]
    assert choices and not any(name.startswith("agy-") for name in choices)
    assert client.get("/presets").json()[0]["runtime"] != "antigravity"
    source = tmp_path / "book.epub"
    _book(source)
    response = client.post(
        "/runs/upload", files={"file": ("book.epub", source.read_bytes(), "application/epub+zip")}
    )
    assert response.status_code == 400
    assert "choose a preset" in response.json()["detail"]


def test_presets_read_runtimes_disabled_from_the_configuration_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No patch: the user configuration file reaches the listing."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    user_config = tmp_path / ".config" / "bookweaver" / "config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"runtimes": {"disabled": ["claude-code"]}}')

    cli.main(["presets", "--json"])
    listed = {p["name"]: p["status"] for p in json.loads(capsys.readouterr().out)}
    assert listed["claude-opus-5-5-low"] == "disabled"
    assert listed["agy-flash-low"] == "default"

    user_config.write_text('{"runtimes": {"disabled": ["copilot"]}}')
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["presets"])
    assert exit_info.value.code == 2
    assert "Invalid runtime configuration" in capsys.readouterr().err
