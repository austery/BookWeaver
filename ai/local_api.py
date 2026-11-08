"""Local HTTP API over the application path (SPEC-026); its generated /docs page is the UI.

Bound to 127.0.0.1 only. It reads the same named rows as the CLI and starts runs as a child
``bookweaver`` process (SPEC-026 §7.3). Its only own state is the run record file. Requires the
optional ``api`` extra (FastAPI and uvicorn), imported at module load so a missing one is
reported by the CLI before anything starts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ai import orchestration

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_LOCAL_HOSTNAMES = ("127.0.0.1", "localhost")
_RECORD_NAME = "current-run.json"
_LOG_TAIL_LINES = 20
# The CLI paid gate's own wording (ai/runtime_factory.py); a test keeps them identical.
PAID_CONSENT_REQUIRED = "Paid API requires --allow-paid-api when non-interactive"
PAID_FLAG_NEEDS_METERED = (
    "--allow-paid-api requires a metered --provider (gemini, openai, or anthropic)"
)
_CHILD_COMMAND: tuple[str, ...] = (sys.executable, "-m", "ai.cli")

RowName = StrEnum("RowName", [(row.name, row.name) for row in orchestration.enabled_rows()])  # type: ignore[misc]

RunState = Literal["running", "finished", "failed", "stopped", "ended"]


def default_state_dir() -> Path:
    """Same XDG rule as the runtime-certification store."""
    state_home = os.environ.get("XDG_STATE_HOME", "")
    root = Path(state_home) if os.path.isabs(state_home) else Path.home() / ".local" / "state"
    return root / "bookweaver"


class RunRequest(BaseModel):
    source: str = Field(description="Path to the source EPUB.")
    output: str = Field(description="Path for the bilingual EPUB.")
    row: RowName = Field(description="Enabled row; GET /rows lists them.")
    prompt: str | None = Field(default=None, description="Extra translation instructions.")
    glossary: str | None = Field(default=None, description="Path to a glossary JSON file.")
    allow_paid_api: bool = Field(
        default=False, description="Consent to paid calls for a metered row, for this run only."
    )


class RunStatus(BaseModel):
    run_id: str
    state: RunState
    row: str
    source: str
    output: str
    planned_segments: int
    done_segments: int | None = Field(description="From the checkpoint; null if unreadable.")
    exit_code: int | None
    started_at: str
    ended_at: str | None
    log_path: str
    log_tail: list[str]


@dataclass(frozen=True)
class RunRecord:
    """Schema version 1 of ``current-run.json`` (SPEC-026 §7.3 decision 2)."""

    schema_version: int
    run_id: str
    pid: int
    source: str
    output: str
    row: str
    allow_paid_api: bool
    started_at: str
    log_path: str
    checkpoint_dir: str
    planned_segments: int
    exit_code: int | None
    ended_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _RunStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / _RECORD_NAME
        self.lock = threading.Lock()

    def read(self) -> RunRecord | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise HTTPException(500, f"Unreadable run record: {self.path}")
        return RunRecord(**data)

    def write(self, record: RunRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, prefix=".current-run-", delete=False
        ) as stream:
            json.dump(asdict(record), stream, indent=2)
        os.replace(stream.name, self.path)

    def finish(self, run_id: str, exit_code: int) -> None:
        with self.lock:
            record = self.read()
            if record is not None and record.run_id == run_id and record.exit_code is None:
                self.write(replace(record, exit_code=exit_code, ended_at=_now()))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _state(record: RunRecord) -> RunState:
    if record.exit_code is None:
        return "running" if _alive(record.pid) else "ended"
    if record.exit_code == 0:
        return "finished"
    if record.exit_code in (-signal.SIGINT, 128 + signal.SIGINT):
        return "stopped"
    return "failed"


def _done_segments(record: RunRecord) -> int | None:
    path = Path(record.checkpoint_dir) / "checkpoint.json"
    try:
        count = json.loads(path.read_text(encoding="utf-8")).get("translated_segment_count")
    except FileNotFoundError:
        return 0
    except (OSError, ValueError, AttributeError):
        return None
    return count if isinstance(count, int) else None


def _log_tail(path: str) -> list[str]:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    return lines[-_LOG_TAIL_LINES:]


def _status(record: RunRecord) -> RunStatus:
    return RunStatus(
        run_id=record.run_id,
        state=_state(record),
        row=record.row,
        source=record.source,
        output=record.output,
        planned_segments=record.planned_segments,
        done_segments=_done_segments(record),
        exit_code=record.exit_code,
        started_at=record.started_at,
        ended_at=record.ended_at,
        log_path=record.log_path,
        log_tail=_log_tail(record.log_path),
    )


def _hostname(value: str) -> str:
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def create_app(
    *,
    port: int = DEFAULT_PORT,
    state_dir: Path | None = None,
    child_command: Sequence[str] = _CHILD_COMMAND,
) -> FastAPI:
    """Build the API; separate from ``serve`` so tests can call it without a socket."""
    store = _RunStore(state_dir or default_state_dir())
    allowed_origins = {f"http://{name}:{port}" for name in _LOCAL_HOSTNAMES}
    app = FastAPI(
        title="BookWeaver local API",
        description=(
            "Lists the enabled rows, the same as `bookweaver rows`, and starts one run at a "
            "time as a `bookweaver` child process."
        ),
        version="0.2.0",
    )

    @app.middleware("http")
    async def local_requests_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Blocks DNS-rebinding and cross-site requests from pages in the owner's browser.
        if _hostname(request.headers.get("host", "")) not in _LOCAL_HOSTNAMES:
            return PlainTextResponse("Host must be 127.0.0.1 or localhost", status_code=400)
        origin = request.headers.get("origin")
        if request.method == "POST" and origin is not None and origin not in allowed_origins:
            return PlainTextResponse("Cross-origin requests are refused", status_code=403)
        return await call_next(request)

    @app.get(
        "/rows",
        response_model=list[orchestration.Row],
        summary="List enabled rows",
        description=(
            "Every selection a run may use, the default row first. Metered rows are paid "
            "and need per-run consent."
        ),
    )
    def list_rows() -> list[orchestration.Row]:
        return list(orchestration.enabled_rows())

    @app.post(
        "/runs",
        status_code=202,
        response_model=RunStatus,
        summary="Start one run",
        description=(
            "Starts `bookweaver <source> --output <output> --row <row>` in the background. "
            "A metered row needs `allow_paid_api`. Only one run at a time."
        ),
    )
    def start_run(body: RunRequest) -> RunStatus:
        row = orchestration.find_row(body.row.value)
        metered = row.provider != "cli"
        if metered and not body.allow_paid_api:
            raise HTTPException(400, PAID_CONSENT_REQUIRED)
        if not metered and body.allow_paid_api:
            raise HTTPException(400, PAID_FLAG_NEEDS_METERED)
        source = Path(body.source).expanduser().resolve()
        output = Path(body.output).expanduser().resolve()
        if source.suffix.lower() != ".epub" or not source.is_file():
            raise HTTPException(400, f"Source must be an existing EPUB file: {source}")
        if not output.parent.is_dir():
            raise HTTPException(400, f"Output directory does not exist: {output.parent}")
        with store.lock:
            current = store.read()
            if current is not None and _state(current) == "running":
                raise HTTPException(409, f"Run {current.run_id} is still running")
            try:
                planned = orchestration.count_epub_segments(source)
            except Exception as exc:  # noqa: BLE001 - any parse failure is a bad request here.
                raise HTTPException(400, f"Cannot read the EPUB: {exc}") from exc
            run_id = str(uuid.uuid4())
            log_path = output.parent / ".bookweaver_runs" / f"{run_id}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            command = [*child_command, str(source), "--output", str(output), "--row", row.name]
            if body.prompt is not None:
                command += ["--prompt", body.prompt]
            if body.glossary is not None:
                command += ["--glossary", str(Path(body.glossary).expanduser().resolve())]
            if body.allow_paid_api:
                command.append("--allow-paid-api")
            with log_path.open("ab") as log:
                child = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            record = RunRecord(
                schema_version=1,
                run_id=run_id,
                pid=child.pid,
                source=str(source),
                output=str(output),
                row=row.name,
                allow_paid_api=body.allow_paid_api,
                started_at=_now(),
                log_path=str(log_path),
                checkpoint_dir=str(orchestration.default_epub_checkpoint_dir(source, output)),
                planned_segments=planned,
                exit_code=None,
                ended_at=None,
            )
            store.write(record)
        threading.Thread(
            target=lambda: store.finish(run_id, child.wait()), daemon=True, name=f"run-{run_id}"
        ).start()
        return _status(record)

    @app.get(
        "/runs/current",
        response_model=RunStatus,
        summary="Status of the latest run",
        description="Refresh to update. Done segments come from the run's checkpoint.",
    )
    def current_run() -> RunStatus:
        record = store.read()
        if record is None:
            raise HTTPException(404, "No run has been started")
        return _status(record)

    @app.post(
        "/runs/current/stop",
        status_code=202,
        response_model=RunStatus,
        summary="Stop the running run",
        description=(
            "Sends Ctrl-C (SIGINT) to the run. Saved batches resume on the next run; the batch "
            "in flight is lost, and on a metered row it may already be paid for."
        ),
    )
    def stop_run() -> RunStatus:
        record = store.read()
        if record is None or _state(record) != "running":
            raise HTTPException(409, "No run is running")
        os.killpg(record.pid, signal.SIGINT)
        return _status(record)

    return app


def serve(port: int) -> None:
    """Run the API in the foreground until interrupted; never binds beyond this Mac."""
    uvicorn.run(create_app(port=port), host=HOST, port=port)
