"""SPEC-028 Phase 4: a Term Panel on the local API upload, with a fake child process."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai import local_api, orchestration
from ai.orchestration import EpubTranslationOptions, GlossarySpec, TranslationOrchestrator
from ai.orchestration import run_term_panel
from tests.unit.test_term_panel_runner import _PANEL, FakeMembers, _book
from tests.unit.test_term_panel_translation import PanelAndTranslator

BASE_URL = "http://127.0.0.1:8765"
# Echoes its arguments, like the fake child of the local API tests.
FAKE_CHILD = 'import json, sys\nprint("ARGS " + json.dumps(sys.argv[1:]), flush=True)\n'


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner's configuration holds the three-vendor panel and nothing else."""
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: _PANEL)


@pytest.fixture
def client(tmp_path: Path, configured: None) -> Iterator[TestClient]:
    script = tmp_path / "fake_child.py"
    script.write_text(FAKE_CHILD)
    app = local_api.create_app(
        state_dir=tmp_path / "state",
        child_command=(sys.executable, str(script)),
        library_dir=tmp_path / "library",
        disabled_runtimes=frozenset(),
        term_panels=("three-vendor",),
    )
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client


def _book_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "source" / "garden.epub"
    path.parent.mkdir()
    _book(path)
    return path.read_bytes()


def _upload(client: TestClient, content: bytes, **form: str) -> object:
    return client.post(
        "/runs/upload",
        files={"file": ("garden.epub", content, "application/epub+zip")},
        data=form,
    )


def _child_args(client: TestClient) -> list[str]:
    deadline = time.monotonic() + 10
    while True:
        for line in client.get("/runs/current").json()["log_tail"]:
            if line.startswith("ARGS "):
                return json.loads(line[5:])
        assert time.monotonic() < deadline, "fake child never started"
        time.sleep(0.02)


def test_the_upload_offers_the_configured_panels_with_none_as_default(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    upload = schema["paths"]["/runs/upload"]["post"]["requestBody"]["content"]
    ref = upload["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[1]
    field = schema["components"]["schemas"][ref]["properties"]["term_panel"]
    assert field["default"] == "none"
    choices = schema["components"]["schemas"][field["$ref"].rsplit("/", 1)[1]]["enum"]
    assert choices == ["none", "three-vendor"]


def test_a_panel_upload_runs_the_panel_in_its_own_folder(
    client: TestClient, tmp_path: Path
) -> None:
    response = _upload(
        client, _book_bytes(tmp_path), term_panel="three-vendor", extraction_model="flash"
    )

    assert response.status_code == 202, response.text
    args = _child_args(client)
    assert args[args.index("--term-panel") + 1] == "three-vendor"
    assert "--extraction-model" not in args  # the panel replaces it (SPEC-028 §3.10)
    book = tmp_path / "library" / "garden" / "garden.epub"
    folder = f"panel-three-vendor-{orchestration.panel_upload_plan(book, 'three-vendor').folder_id}"
    expected = tmp_path / "library" / "garden" / folder / "agy-flash-low" / "garden.zh.epub"
    assert args[args.index("--output") + 1] == str(expected)
    plan = response.json()["term_panel_plan"]  # SPEC-028 §3.14, before any call
    assert plan[0].startswith("[terms] Panel three-vendor:")
    assert any("codex-gpt-6.1-sol-low (openai, runtime codex)" in line for line in plan)


def test_the_folder_id_is_the_cache_identity_the_translate_command_uses(
    tmp_path: Path, configured: None
) -> None:
    """The panel cache sits beside the EPUB; its folder name starts with the same identity."""
    book = tmp_path / "garden.epub"
    _book(book)

    glossary = run_term_panel(book, "three-vendor", config=_PANEL, provider_factory=FakeMembers())

    assert glossary.parent.name.startswith(
        orchestration.panel_upload_plan(book, "three-vendor").folder_id
    )
    assert len(orchestration.panel_upload_plan(book, "three-vendor").folder_id) == 8


def test_editing_the_panel_gives_a_new_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "garden.epub"
    _book(book)
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: _PANEL)
    before = orchestration.panel_upload_plan(book, "three-vendor").folder_id
    edited = {
        "terminology_panels": {
            "three-vendor": {
                "nominators": ["agy-flash-low", "codex-gpt-6.1-sol-low"],
                "judges": ["codex-gpt-6.1-sol-low", "claude-opus-5-5-low"],
            }
        }
    }
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: edited)

    assert orchestration.panel_upload_plan(book, "three-vendor").folder_id != before


def test_without_a_panel_the_upload_is_unchanged(client: TestClient, tmp_path: Path) -> None:
    response = _upload(client, _book_bytes(tmp_path))

    assert response.status_code == 202, response.text
    args = _child_args(client)
    assert "--term-panel" not in args
    assert response.json()["term_panel_plan"] is None
    assert args[args.index("--extraction-model") + 1] == "pro"
    assert args[args.index("--output") + 1] == str(
        tmp_path / "library" / "garden" / "garden.zh.epub"
    )


def test_deep_scan_with_a_panel_is_refused_before_anything_is_stored(
    client: TestClient, tmp_path: Path
) -> None:
    response = _upload(
        client, _book_bytes(tmp_path), term_panel="three-vendor", glossary_mode="deep-scan"
    )

    assert response.status_code == 400
    assert "Phase 5" in response.json()["detail"]
    assert not (tmp_path / "library").exists()


def test_an_unknown_panel_is_not_a_choice(client: TestClient, tmp_path: Path) -> None:
    response = _upload(client, _book_bytes(tmp_path), term_panel="missing")

    assert response.status_code == 422


def test_a_panel_removed_after_start_is_refused_and_the_upload_removed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: {})

    response = _upload(client, _book_bytes(tmp_path), term_panel="three-vendor")

    assert response.status_code == 400
    assert "Unknown Term Panel" in response.json()["detail"]
    library = tmp_path / "library"
    assert not library.exists() or not any(library.rglob("*"))
    assert client.get("/runs/current").status_code == 404


def test_only_valid_panels_are_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    config = {
        "terminology_panels": {
            **_PANEL["terminology_panels"],
            "paid": {"nominators": ["anthropic-pro"]},
            "typo": {"nominators": ["agy-flash-lo"]},
            "none": {"nominators": ["agy-flash-low"]},
        }
    }
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: config)

    assert orchestration.configured_term_panels() == ("three-vendor",)


def test_any_panel_name_keeps_the_server_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A panel name is a value, never an enum member name ("mro" is reserved there)."""
    app = local_api.create_app(
        state_dir=tmp_path / "state",
        library_dir=tmp_path / "library",
        disabled_runtimes=frozenset(),
        term_panels=("mro", "_private_"),
    )
    schema = TestClient(app, base_url=BASE_URL).get("/openapi.json").json()

    assert schema["components"]["schemas"]["TermPanelName"]["enum"] == ["none", "mro", "_private_"]


def test_a_cached_panel_glossary_shows_as_reused_in_the_plan(
    tmp_path: Path, configured: None
) -> None:
    book = tmp_path / "garden.epub"
    _book(book)
    run_term_panel(book, "three-vendor", config=_PANEL, provider_factory=FakeMembers())

    lines = orchestration.panel_upload_plan(book, "three-vendor").lines

    assert lines == ("[terms] Panel three-vendor: reusing the saved glossary; no model call.",)


def test_the_folder_id_matches_a_term_panel_translation(tmp_path: Path, configured: None) -> None:
    """Through the translate path itself, not only `bookweaver terms`."""
    book = tmp_path / "garden.epub"
    _book(book)

    summary = TranslationOrchestrator(provider_factory=PanelAndTranslator()).translate(
        book,
        tmp_path / "out" / "garden.zh.epub",
        EpubTranslationOptions(config=_PANEL, glossary=GlossarySpec(term_panel="three-vendor")),
        input_format="epub",
    )

    assert summary.glossary_used is not None
    assert summary.glossary_used.parent.name.startswith(
        orchestration.panel_upload_plan(book, "three-vendor").folder_id
    )


def test_a_panel_name_that_cannot_be_a_folder_is_not_offered(tmp_path: Path) -> None:
    app = local_api.create_app(
        state_dir=tmp_path / "state",
        library_dir=tmp_path / "library",
        disabled_runtimes=frozenset(),
        term_panels=("three-vendor", "a/b", "tab\there"),
    )
    schema = TestClient(app, base_url=BASE_URL).get("/openapi.json").json()

    assert schema["components"]["schemas"]["TermPanelName"]["enum"] == ["none", "three-vendor"]


def test_a_linked_panel_folder_is_refused_without_touching_its_target(
    client: TestClient, tmp_path: Path
) -> None:
    content = _book_bytes(tmp_path)
    book_dir = tmp_path / "library" / "garden"
    book_dir.mkdir(parents=True)
    (book_dir / "garden.epub").write_bytes(content)
    folder_id = orchestration.panel_upload_plan(book_dir / "garden.epub", "three-vendor").folder_id
    outside = tmp_path / "outside"
    (outside / "agy-flash-low").mkdir(parents=True)
    (book_dir / f"panel-three-vendor-{folder_id}").symlink_to(outside)

    response = _upload(client, content, term_panel="three-vendor")

    assert response.status_code == 400
    assert "symbolic link" in response.json()["detail"]
    assert (outside / "agy-flash-low").is_dir()  # never removed through the link
