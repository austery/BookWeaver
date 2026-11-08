"""Local API contract at the HTTP boundary (SPEC-026 Phases 2-4)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ai.cli as entry_module
from ai import local_api, orchestration
from ai.antigravity_provider import default_certification_path
from ai.model_profiles import Row, enabled_rows, is_metered, resolve_profile
from ai.runtime_factory import DefaultProviderFactory, PaidAuthorizationError
from tests.runtime_fakes import install_fake_any_llm

BASE_URL = "http://127.0.0.1:8765"
METERED_ROWS = [row for row in enabled_rows() if is_metered(row.provider)]
SUBSCRIPTION_ROWS = [row for row in enabled_rows() if not is_metered(row.provider)]


def row_name(row: Row) -> str:
    return row.name


# A stand-in for `python -m ai.cli`: echoes its arguments, optionally writes a checkpoint,
# then sleeps or exits as the test asks through environment variables.
FAKE_CHILD = """
import json, os, sys, time
from pathlib import Path
print("ARGS " + json.dumps(sys.argv[1:]), flush=True)
print("STDIN_IS_DEVNULL " + str(os.path.samestat(os.fstat(0), os.stat(os.devnull))), flush=True)
checkpoint = os.environ.get("FAKE_CHECKPOINT")
if checkpoint:
    Path(checkpoint).mkdir(parents=True, exist_ok=True)
    (Path(checkpoint) / "checkpoint.json").write_text(json.dumps({"translated_segment_count": 1}))
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


def make_epub(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata/><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
        )
        archive.writestr(
            "chapter.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Example</title></head><body><p>The garden gate was open.</p><p>The moon rose above the hill.</p></body></html>',
        )
    return path


@pytest.fixture
def client() -> TestClient:
    return TestClient(local_api.create_app(), base_url=BASE_URL)


@pytest.fixture
def runs(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    script = tmp_path / "fake_child.py"
    script.write_text(FAKE_CHILD)
    app = local_api.create_app(
        state_dir=tmp_path / "state", child_command=(sys.executable, str(script))
    )
    with TestClient(app, base_url=BASE_URL) as test_client:
        yield test_client, tmp_path
        current = test_client.get("/runs/current")
        if current.status_code == 200 and current.json()["state"] == "running":
            test_client.post("/runs/current/stop")


def start(client: TestClient, tmp_path: Path, **fields: object) -> dict[str, object]:
    body: dict[str, object] = {
        "source": str(make_epub(tmp_path / "book.epub")),
        "output": str(tmp_path / "book.zh.epub"),
        "row": "agy-flash-low",
    }
    body.update(fields)
    response = client.post("/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()


def settle(client: TestClient, *, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while True:
        status = client.get("/runs/current").json()
        if status["state"] != "running" or time.monotonic() > deadline:
            return status
        time.sleep(0.05)


def wait_until_started(client: TestClient, *, timeout: float = 10.0) -> None:
    """Wait for the fake child to print its arguments, so Python has finished starting."""
    deadline = time.monotonic() + timeout
    while not any(
        line.startswith("ARGS ") for line in client.get("/runs/current").json()["log_tail"]
    ):
        assert time.monotonic() < deadline, "fake child never started"
        time.sleep(0.02)


def child_args(status: dict[str, object]) -> list[str]:
    for line in status["log_tail"]:
        if line.startswith("ARGS "):
            return json.loads(line[5:])
    raise AssertionError(f"no ARGS line in {status['log_tail']}")


def test_rows_endpoint_matches_the_cli_listing(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    response = client.get("/rows")
    assert response.status_code == 200
    entry_module.main(["rows", "--json"])
    assert response.json() == json.loads(capsys.readouterr().out)
    assert response.json()[0]["name"] == "agy-flash-low"


def test_rows_schema_lists_choices_as_enums(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    row = schemas["Row"]["properties"]
    assert row["status"]["enum"] == ["default", "manual", "experiment"]
    assert "antigravity" in row["runtime"]["enum"]
    assert "agy-flash-low" in schemas["RowName"]["enum"]


def test_docs_page_is_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_serve_binds_to_loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, *, host, port: calls.append((host, port)))
    entry_module.main(["serve", "--port", "8800"])
    assert calls == [("127.0.0.1", 8800)]


def test_serve_rejects_an_invalid_port(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        entry_module.main(["serve", "--port", "0"])
    assert "between 1 and 65535" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["fastapi", "uvicorn"])
def test_serve_without_the_api_extra_names_the_install_command(
    missing: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import uvicorn

    import ai

    def never_serve(*args: object, **kwargs: object) -> None:
        raise AssertionError("serve must not start without the api extra")

    monkeypatch.setattr(uvicorn, "run", never_serve)
    # Force a fresh import of ai.local_api with one dependency unavailable.
    monkeypatch.setitem(sys.modules, missing, None)
    monkeypatch.delitem(sys.modules, "ai.local_api")
    monkeypatch.delattr(ai, "local_api")
    with pytest.raises(SystemExit):
        entry_module.main(["serve"])
    error = capsys.readouterr().err
    assert missing in error and "uv sync --extra api" in error


# ── Request protection (SPEC-026 §7.3 decision 4) ────────────────────────────


def test_foreign_host_is_refused(client: TestClient) -> None:
    response = client.get("/rows", headers={"Host": "attacker.example:8765"})
    assert response.status_code == 400


def test_localhost_host_is_accepted(client: TestClient) -> None:
    assert client.get("/rows", headers={"Host": "localhost:8765"}).status_code == 200


def test_cross_origin_post_is_refused(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": "agy-flash-low",
        },
        headers={"Origin": "http://attacker.example"},
    )
    assert response.status_code == 403
    assert client.get("/runs/current").status_code == 404


def test_same_origin_post_is_accepted(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": "agy-flash-low",
        },
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 202


# ── Starting runs (decisions 1-3, 5) ─────────────────────────────────────────


def test_run_starts_the_cli_contract_and_reports_progress(
    runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tmp_path = runs
    checkpoint = tmp_path / ".bookweaver_checkpoints" / "epub" / "book"
    monkeypatch.setenv("FAKE_CHECKPOINT", str(checkpoint))
    started = start(client, tmp_path, prompt="Keep it formal.")
    assert started["planned_segments"] == 2
    status = settle(client)
    assert status["state"] == "finished" and status["exit_code"] == 0
    assert status["done_segments"] == 1
    assert child_args(status) == [
        str(tmp_path / "book.epub"),
        "--output",
        str(tmp_path / "book.zh.epub"),
        "--row",
        "agy-flash-low",
        "--prompt=Keep it formal.",
    ]
    log = Path(str(status["log_path"]))
    assert log.parent == tmp_path / ".bookweaver_runs"
    record = json.loads((tmp_path / "state" / "current-run.json").read_text())
    assert record["schema_version"] == 1 and record["checkpoint_dir"] == str(checkpoint)
    assert started["checkpoint_dir"] == str(checkpoint)


def test_failed_child_is_reported(
    runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tmp_path = runs
    monkeypatch.setenv("FAKE_EXIT", "3")
    start(client, tmp_path)
    status = settle(client)
    assert status["state"] == "failed" and status["exit_code"] == 3


def test_metered_row_without_consent_starts_nothing(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": "gemini-flash",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail.startswith("Metered gemini API: ") and "gemini" in detail.split(":")[1]
    assert detail.endswith(local_api.PAID_CONSENT_REQUIRED)
    assert client.get("/runs/current").status_code == 404


def test_subscription_row_rejects_paid_consent(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": "agy-flash-low",
            "allow_paid_api": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == local_api.PAID_FLAG_NEEDS_METERED


def test_metered_row_with_consent_passes_the_flag(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    start(client, tmp_path, row="gemini-flash", allow_paid_api=True)
    assert child_args(settle(client))[-3:] == ["--row", "gemini-flash", "--allow-paid-api"]


def test_the_consent_tests_cover_metered_and_subscription_rows() -> None:
    assert {"gemini", "anthropic"} <= {row.provider for row in METERED_ROWS}
    assert SUBSCRIPTION_ROWS


def assert_nothing_started(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/runs/current").status_code == 404
    assert not (tmp_path / "state" / "current-run.json").exists()
    assert not (tmp_path / ".bookweaver_runs").exists()


@pytest.mark.parametrize("row", METERED_ROWS, ids=row_name)
@pytest.mark.parametrize("consent", [{}, {"allow_paid_api": False}], ids=["omitted", "false"])
def test_no_metered_row_starts_without_consent(
    runs: tuple[TestClient, Path], row: Row, consent: dict[str, object]
) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": row.name,
            **consent,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        f"Metered {row.provider} API: {row.model_id}. {local_api.PAID_CONSENT_REQUIRED}"
    )
    assert_nothing_started(client, tmp_path)


def test_null_consent_starts_nothing(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": METERED_ROWS[0].name,
            "allow_paid_api": None,
        },
    )
    assert response.status_code == 422
    assert_nothing_started(client, tmp_path)


@pytest.mark.parametrize("row", METERED_ROWS, ids=row_name)
def test_consent_reaches_the_child_once(runs: tuple[TestClient, Path], row: Row) -> None:
    client, tmp_path = runs
    start(client, tmp_path, row=row.name, allow_paid_api=True)
    status = settle(client)
    arguments = child_args(status)
    assert arguments[arguments.index("--row") + 1] == row.name
    assert arguments.count("--allow-paid-api") == 1


def test_child_never_inherits_the_server_stdin(runs: tuple[TestClient, Path]) -> None:
    """The paid gate prompts only on a terminal; the server's own stdin must not reach it."""
    client, tmp_path = runs
    read_end, write_end = os.pipe()
    saved_stdin = os.dup(0)
    os.dup2(read_end, 0)  # pytest's fd 0 is already /dev/null, which would hide inheritance
    try:
        start(client, tmp_path)
        status = settle(client)
    finally:
        os.dup2(saved_stdin, 0)
        for descriptor in (saved_stdin, read_end, write_end):
            os.close(descriptor)
    assert "STDIN_IS_DEVNULL True" in status["log_tail"]


def test_consent_is_not_remembered_for_the_next_run(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    row = METERED_ROWS[0].name
    start(client, tmp_path, row=row, allow_paid_api=True)
    settle(client)
    response = client.post(
        "/runs",
        json={
            "source": str(tmp_path / "book.epub"),
            "output": str(tmp_path / "book.zh.epub"),
            "row": row,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"].endswith(local_api.PAID_CONSENT_REQUIRED)


@pytest.mark.parametrize("row", SUBSCRIPTION_ROWS, ids=row_name)
def test_subscription_rows_never_carry_the_paid_flag(
    runs: tuple[TestClient, Path], row: Row
) -> None:
    client, tmp_path = runs
    refused = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": row.name,
            "allow_paid_api": True,
        },
    )
    assert refused.status_code == 400
    assert refused.json()["detail"] == local_api.PAID_FLAG_NEEDS_METERED
    assert_nothing_started(client, tmp_path)
    start(client, tmp_path, row=row.name)
    assert "--allow-paid-api" not in child_args(settle(client))


@pytest.mark.parametrize("row", METERED_ROWS, ids=row_name)
def test_cli_refuses_a_metered_row_without_the_flag_even_with_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row: Row
) -> None:
    """The second layer: what the API's child does if the server check were bypassed.

    Runs in-process against a fake client and an empty config. A checkout's config can hold
    a real key, so this test must stay offline even when the paid gate is broken.
    """
    calls: list[str] = []
    constructed: list[dict[str, object]] = []
    install_fake_any_llm(monkeypatch, lambda _model: "", calls=calls, constructed=constructed)
    monkeypatch.setattr(orchestration, "load_runtime_config", lambda: {})
    monkeypatch.setenv(f"{row.provider.upper()}_API_KEY", "test-only-not-a-secret")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    output = tmp_path / "o.epub"
    with pytest.raises(PaidAuthorizationError) as refused:
        entry_module.main(
            [str(make_epub(tmp_path / "b.epub")), "--output", str(output), "--row", row.name]
        )
    assert str(refused.value) == local_api.PAID_CONSENT_REQUIRED
    assert not constructed and not calls
    assert not output.exists()


def test_rejection_texts_match_the_cli_paid_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    # Consent on a subscription row: the CLI itself raises this before any provider exists.
    with pytest.raises(ValueError) as cli_error:
        entry_module.main(
            [
                str(make_epub(tmp_path / "b.epub")),
                "--output",
                str(tmp_path / "o.epub"),
                "--row",
                "agy-flash-low",
                "--allow-paid-api",
            ]
        )
    assert str(cli_error.value) == local_api.PAID_FLAG_NEEDS_METERED
    # Metered row without consent, non-interactive: the paid gate's own text.
    # A fake client keeps this offline even when the gate is broken and a real key is set.
    install_fake_any_llm(monkeypatch, lambda _model: "", calls=[], constructed=[])
    factory = DefaultProviderFactory()
    with pytest.raises(PaidAuthorizationError) as missing:
        factory.create(
            resolve_profile("flash", provider="gemini"),
            protocol="segment_tags",
            config={},
            allow_paid_api=False,
            remaining_chars=1,
        )
    assert str(missing.value) == local_api.PAID_CONSENT_REQUIRED


def test_non_epub_source_is_rejected(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes")
    response = client.post(
        "/runs",
        json={"source": str(notes), "output": str(tmp_path / "o.epub"), "row": "agy-flash-low"},
    )
    assert response.status_code == 400


def test_unknown_row_is_a_validation_error(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    response = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "b.epub")),
            "output": str(tmp_path / "o.epub"),
            "row": "agy-ultra-max",
        },
    )
    assert response.status_code == 422


# ── One run at a time, stop, restart (decisions 2, 6) ────────────────────────


def test_second_run_is_refused_while_one_runs(
    runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tmp_path = runs
    monkeypatch.setenv("FAKE_SLEEP", "30")
    start(client, tmp_path)
    second = client.post(
        "/runs",
        json={
            "source": str(make_epub(tmp_path / "c.epub")),
            "output": str(tmp_path / "c.zh.epub"),
            "row": "agy-flash-low",
        },
    )
    assert second.status_code == 409


def test_stop_sends_ctrl_c(runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    client, tmp_path = runs
    monkeypatch.setenv("FAKE_SLEEP", "30")
    start(client, tmp_path)
    wait_until_started(client)
    assert client.post("/runs/current/stop").status_code == 202
    status = settle(client)
    assert status["state"] == "stopped"
    assert client.post("/runs/current/stop").status_code == 409


def test_prompt_starting_with_a_dash_reaches_the_child(runs: tuple[TestClient, Path]) -> None:
    client, tmp_path = runs
    start(client, tmp_path, prompt="-formal")
    status = settle(client)
    assert status["state"] == "finished"
    assert "--prompt=-formal" in child_args(status)


def test_restarted_server_still_controls_a_live_child(
    runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-ASCII path must survive the ps lookup that identifies the child after a restart.
    client, tmp_path = runs
    monkeypatch.setenv("FAKE_SLEEP", "30")
    script = tmp_path / "fake_child.py"
    start(client, tmp_path, source=str(make_epub(tmp_path / "书.epub")))
    wait_until_started(client)
    restarted = TestClient(
        local_api.create_app(
            state_dir=tmp_path / "state", child_command=(sys.executable, str(script))
        ),
        base_url=BASE_URL,
    )
    assert restarted.get("/runs/current").json()["state"] == "running"
    assert restarted.post("/runs/current/stop").status_code == 202
    assert settle(client)["state"] == "stopped"


def test_damaged_record_is_refused_with_its_path(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "current-run.json").write_text("{not json")
    client = TestClient(local_api.create_app(state_dir=state), base_url=BASE_URL)
    response = client.get("/runs/current")
    assert response.status_code == 500
    assert "current-run.json" in response.json()["detail"]


def test_no_run_yet_is_404(runs: tuple[TestClient, Path]) -> None:
    client, _ = runs
    assert client.get("/runs/current").status_code == 404


def test_state_dir_shares_the_certification_root() -> None:
    assert local_api.default_state_dir() == default_certification_path().parent


def test_unrecordable_run_is_stopped(
    runs: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, tmp_path = runs
    monkeypatch.setenv("FAKE_SLEEP", "30")
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "current-run.lock").touch()
    state.chmod(0o500)
    try:
        response = client.post(
            "/runs",
            json={
                "source": str(make_epub(tmp_path / "book.epub")),
                "output": str(tmp_path / "book.zh.epub"),
                "row": "agy-flash-low",
            },
        )
    finally:
        state.chmod(0o700)
    assert response.status_code == 500
    script = str(tmp_path / "fake_child.py")
    survivors = subprocess.run(["pgrep", "-f", script], capture_output=True, text=True).stdout
    assert survivors.strip() == ""


def test_two_servers_never_start_two_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "fake_child.py"
    script.write_text(FAKE_CHILD)
    monkeypatch.setenv("FAKE_SLEEP", "30")
    state = tmp_path / "state"
    clients = [
        TestClient(
            local_api.create_app(
                port=port, state_dir=state, child_command=(sys.executable, str(script))
            ),
            base_url=f"http://127.0.0.1:{port}",
        )
        for port in (8765, 8766)
    ]
    books = [make_epub(tmp_path / f"book{index}.epub") for index in (0, 1)]
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def post(index: int) -> None:
        barrier.wait()
        body = {
            "source": str(books[index]),
            "output": str(tmp_path / f"out{index}.epub"),
            "row": "agy-flash-low",
        }
        codes.append(clients[index].post("/runs", json=body).status_code)

    threads = [threading.Thread(target=post, args=(index,)) for index in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert sorted(codes) == [202, 409]
    finally:
        for test_client in clients:
            test_client.post("/runs/current/stop")


# ── Identity of the child after a restart (§7.3 decision 2) ──────────────────


def write_record(state: Path, **fields: object) -> None:
    record: dict[str, object] = {
        "schema_version": 1,
        "run_id": "r1",
        "pid": None,
        "process_start": None,
        "source": "/books/b.epub",
        "output": "/books/b.zh.epub",
        "row": "agy-flash-low",
        "allow_paid_api": False,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "log_path": str(state / "none.log"),
        "checkpoint_dir": str(state / "none"),
        "planned_segments": 5,
        "exit_code": None,
        "ended_at": None,
    }
    record.update(fields)
    state.mkdir(parents=True, exist_ok=True)
    (state / "current-run.json").write_text(json.dumps(record))


def spawn_lookalike(tmp_path: Path) -> subprocess.Popen[bytes]:
    """A sleeping process whose command line carries a run's arguments."""
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            str(tmp_path / "b.epub"),
            "--output",
            str(tmp_path / "b.zh.epub"),
            "--row",
            "agy-flash-low",
        ],
        start_new_session=True,
    )


def restarted(state: Path) -> TestClient:
    return TestClient(local_api.create_app(state_dir=state), base_url=BASE_URL)


def test_restarted_server_reports_an_unobserved_exit_as_ended(tmp_path: Path) -> None:
    write_record(tmp_path / "state", pid=2**22 + 12345, process_start="Thu Jan  1 00:00:00 2026")
    status = restarted(tmp_path / "state").get("/runs/current").json()
    assert status["state"] == "ended" and status["done_segments"] == 0


def test_reused_pid_with_the_same_arguments_is_never_signalled(tmp_path: Path) -> None:
    # Worst case: the reused PID even carries the run's arguments; only its start time differs.
    lookalike = spawn_lookalike(tmp_path)
    try:
        write_record(
            tmp_path / "state",
            pid=lookalike.pid,
            process_start="Thu Jan  1 00:00:00 2026",
            source=str(tmp_path / "b.epub"),
            output=str(tmp_path / "b.zh.epub"),
        )
        client = restarted(tmp_path / "state")
        assert client.get("/runs/current").json()["state"] == "ended"
        assert client.post("/runs/current/stop").status_code == 409
        assert lookalike.poll() is None
    finally:
        lookalike.kill()
        lookalike.wait()


def test_unrelated_process_with_the_recorded_start_is_never_signalled(tmp_path: Path) -> None:
    # Same PID and start time can only be the same process; here the arguments differ.
    write_record(
        tmp_path / "state",
        pid=os.getpid(),
        process_start=local_api._process_start(os.getpid()),
    )
    client = restarted(tmp_path / "state")
    assert client.get("/runs/current").json()["state"] == "ended"
    assert client.post("/runs/current/stop").status_code == 409


def test_child_started_before_its_pid_was_recorded_is_found_and_stopped(tmp_path: Path) -> None:
    # The server died between starting the child and recording its PID (phase 1 record only).
    lookalike = spawn_lookalike(tmp_path)
    try:
        write_record(
            tmp_path / "state",
            source=str(tmp_path / "b.epub"),
            output=str(tmp_path / "b.zh.epub"),
        )
        client = restarted(tmp_path / "state")
        assert client.get("/runs/current").json()["state"] == "running"
        conflict = client.post(
            "/runs",
            json={
                "source": str(make_epub(tmp_path / "c.epub")),
                "output": str(tmp_path / "c.zh.epub"),
                "row": "agy-flash-low",
            },
        )
        assert conflict.status_code == 409
        assert client.post("/runs/current/stop").status_code == 202
        assert lookalike.wait(timeout=10) == -signal.SIGINT
    finally:
        if lookalike.poll() is None:
            lookalike.kill()
            lookalike.wait()


def test_record_with_a_wrong_field_type_is_refused(tmp_path: Path) -> None:
    write_record(tmp_path / "state", started_at=12345)
    response = restarted(tmp_path / "state").get("/runs/current")
    assert response.status_code == 500 and "started_at" in response.json()["detail"]


def test_elapsed_time_parsing() -> None:
    assert local_api._elapsed_seconds("00:05") == 5
    assert local_api._elapsed_seconds("01:02:03") == 3723
    assert local_api._elapsed_seconds("2-01:00:00") == 2 * 86400 + 3600
    assert local_api._elapsed_seconds("garbage") is None
