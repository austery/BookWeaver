"""Local HTTP API over the application path (SPEC-026); its generated /docs page is the UI.

Bound to 127.0.0.1 only. It reads the same named presets as the CLI and starts runs as a child
``bookweaver`` process (SPEC-026 §7.3). Its own files are the run record, its lock file,
each run's log, and the uploaded books in the library (§7.5). Requires the optional ``api``
extra (FastAPI, python-multipart and uvicorn), imported at module load so a missing one is
reported by the CLI before anything starts.
"""

from __future__ import annotations

import fcntl
import filecmp
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import python_multipart  # noqa: F401 - Form fields need it; a missing one must fail at import.
import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field

from ai import orchestration

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_LOCAL_HOSTNAMES = ("127.0.0.1", "localhost")
_RECORD_NAME = "current-run.json"
_LOCK_NAME = "current-run.lock"
_RECORD_SCHEMA_VERSION = 2
_START_TOLERANCE_S = 5
_UTF8_LOCALE = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
_LOG_TAIL_LINES = 20
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_COPY_CHUNK_BYTES = 1024 * 1024
_MAX_FILE_NAME_BYTES = 255
# The CLI's own wording: ai/runtime_factory.py (metered preset without consent) and
# ai/orchestration.py (consent on a subscription preset). Tests keep them identical.
PAID_CONSENT_REQUIRED = "Paid API requires --allow-paid-api when non-interactive"
PAID_FLAG_NEEDS_METERED = "--allow-paid-api requires a metered --provider"
_CHILD_COMMAND: tuple[str, ...] = (sys.executable, "-m", "ai.cli")

PresetName = StrEnum(
    "PresetName", [(preset.name, preset.name) for preset in orchestration.enabled_presets()]
)  # type: ignore[misc]

DEFAULT_PRESET = PresetName(orchestration.enabled_presets()[0].name)

RunState = Literal["running", "finished", "failed", "stopped", "ended"]


def default_state_dir() -> Path:
    """Same XDG rule as the runtime-certification store."""
    state_home = os.environ.get("XDG_STATE_HOME", "")
    root = Path(state_home) if os.path.isabs(state_home) else Path.home() / ".local" / "state"
    return root / "bookweaver"


def default_library_dir() -> Path:
    """Where uploaded books and their translations live, one folder per book (§7.5)."""
    return Path.home() / "Documents" / "BookWeaver"


class RunRequest(BaseModel):
    source: str = Field(description="Path to the source EPUB.")
    output: str = Field(description="Path for the bilingual EPUB.")
    preset: PresetName = Field(description="Enabled preset; GET /presets lists them.")
    prompt: str | None = Field(default=None, description="Extra translation instructions.")
    glossary: str | None = Field(default=None, description="Path to a glossary JSON file.")
    allow_paid_api: bool = Field(
        default=False,
        description=(
            "Consent to paid calls for a metered preset (GET /presets shows its provider and model), "
            "for this run only."
        ),
    )


class RunStatus(BaseModel):
    run_id: str
    state: RunState
    preset: str
    source: str
    output: str
    planned_segments: int
    done_segments: int | None = Field(description="From the checkpoint; null if unreadable.")
    checkpoint_dir: str
    exit_code: int | None
    started_at: str
    ended_at: str | None
    log_path: str
    log_tail: list[str]


@dataclass(frozen=True)
class RunRecord:
    """Schema version 2 of ``current-run.json`` (SPEC-026 §7.3 decision 2, §7.6)."""

    schema_version: int
    run_id: str
    pid: int | None
    process_start: str | None
    source: str
    output: str
    preset: str
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
        self._thread_lock = threading.Lock()

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Exclusive across threads and across `serve` processes sharing this state directory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock, (self.path.parent / _LOCK_NAME).open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read(self) -> RunRecord | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise self._damaged(exc) from exc
        if not isinstance(data, dict) or data.get("schema_version") != _RECORD_SCHEMA_VERSION:
            raise self._damaged(ValueError(f"not a schema-version-{_RECORD_SCHEMA_VERSION} record"))
        try:
            record = RunRecord(**data)
        except TypeError as exc:
            raise self._damaged(exc) from exc
        wrong = [name for name, kinds in _FIELD_TYPES.items() if not _is(data[name], kinds)]
        if wrong:
            raise self._damaged(ValueError("wrong type: " + ", ".join(wrong)))
        return record

    def _damaged(self, cause: Exception) -> HTTPException:
        # Whether a run is still live is unknown, so refuse instead of guessing.
        return HTTPException(
            500,
            f"Run record {self.path} is damaged ({cause}); check that no run is active, "
            "then delete the file",
        )

    def write(self, record: RunRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.path.parent, prefix=".current-run-", delete=False
        ) as stream:
            json.dump(asdict(record), stream, indent=2)
        os.replace(stream.name, self.path)

    def finish(self, run_id: str, exit_code: int) -> None:
        with self.lock():
            try:
                record = self.read()
            except HTTPException:
                return  # A damaged record is reported by the next request.
            if record is not None and record.run_id == run_id and record.exit_code is None:
                self.write(replace(record, exit_code=exit_code, ended_at=_now()))


_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "run_id": (str,),
    "pid": (int, type(None)),
    "process_start": (str, type(None)),
    "source": (str,),
    "output": (str,),
    "preset": (str,),
    "allow_paid_api": (bool,),
    "started_at": (str,),
    "log_path": (str,),
    "checkpoint_dir": (str,),
    "planned_segments": (int,),
    "exit_code": (int, type(None)),
    "ended_at": (str, type(None)),
}


def _is(value: object, kinds: tuple[type, ...]) -> bool:
    # bool is a subclass of int; a JSON true must not pass as a PID or a count.
    if isinstance(value, bool) and bool not in kinds:
        return False
    return isinstance(value, kinds)


def _marker(record: RunRecord) -> str:
    """The part of the child's command line that names this run."""
    return f"{record.source} --output {record.output} --preset {record.preset}"


def _ps(field: str, *, pid: int | None, locale: str) -> str:
    """One `ps` column for one PID, or for every process when ``pid`` is None.

    `lstart` is read in the C locale so it is stable text; the command line in a UTF-8
    locale, because under C, ps escapes non-ASCII paths.
    """
    target = ["-p", str(pid)] if pid is not None else ["-ax"]
    listing = subprocess.run(
        ["ps", "-o", field, *target],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": locale},
    )
    return listing.stdout.strip()


def _process_start(pid: int) -> str:
    """The kernel's start time for ``pid`` as `ps` prints it; equal text means the same process."""
    return _ps("lstart=", pid=pid, locale="C")


def _elapsed_seconds(text: str) -> int | None:
    """Parse `ps -o etime` ([[dd-]hh:]mm:ss); independent of time zones and daylight saving."""
    days, _, clock = text.strip().rpartition("-")
    parts = clock.split(":")
    try:
        numbers = [int(part) for part in parts]
        whole_days = int(days) if days else 0
    except ValueError:
        return None
    while len(numbers) < 3:
        numbers.insert(0, 0)
    hours, minutes, seconds = numbers[-3:]
    return ((whole_days * 24 + hours) * 60 + minutes) * 60 + seconds


def _locate(record: RunRecord) -> int | None:
    """PID of this run's child while it runs; None otherwise. A reused PID never matches.

    With a PID on record, the process must have the exact recorded start time and carry the
    run's arguments. Without one (the server died between starting the child and recording
    its PID), find the process that carries the run's arguments and started within a few
    seconds of ``started_at``.
    """
    marker = _marker(record)
    if record.pid is not None:
        if record.process_start is None or _process_start(record.pid) != record.process_start:
            return None
        command = _ps("command=", pid=record.pid, locale=_UTF8_LOCALE)
        return record.pid if marker in command else None
    try:
        recorded = datetime.fromisoformat(record.started_at)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    matches: list[int] = []
    for line in _ps("pid=,command=", pid=None, locale=_UTF8_LOCALE).splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if marker not in command or not pid_text.isdigit():
            continue
        elapsed = _elapsed_seconds(_ps("etime=", pid=int(pid_text), locale="C"))
        if elapsed is None:
            continue
        started = now.timestamp() - elapsed
        if abs(started - recorded.timestamp()) <= _START_TOLERANCE_S:
            matches.append(int(pid_text))
    return matches[0] if len(matches) == 1 else None


def _state(record: RunRecord, child: subprocess.Popen[bytes] | None) -> RunState:
    exit_code = record.exit_code
    if exit_code is None and child is not None:
        # This server started the child: its own exit status is authoritative.
        exit_code = child.poll()
        if exit_code is None:
            return "running"
    if exit_code is None:
        return "running" if _locate(record) is not None else "ended"
    if exit_code == 0:
        return "finished"
    if exit_code in (-signal.SIGINT, 128 + signal.SIGINT):
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


def _status(record: RunRecord, child: subprocess.Popen[bytes] | None) -> RunStatus:
    exit_code = record.exit_code
    if exit_code is None and child is not None:
        exit_code = child.poll()
    return RunStatus(
        run_id=record.run_id,
        state=_state(record, child),
        preset=record.preset,
        source=record.source,
        output=record.output,
        planned_segments=record.planned_segments,
        done_segments=_done_segments(record),
        exit_code=exit_code,
        started_at=record.started_at,
        ended_at=record.ended_at,
        log_path=record.log_path,
        checkpoint_dir=record.checkpoint_dir,
        log_tail=_log_tail(record.log_path),
    )


def _hostname(value: str) -> str:
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _check_consent(preset: orchestration.Preset, allow_paid_api: bool) -> None:
    """The same paid-API rule for both ways to start a run; it runs before anything is stored."""
    metered = preset.provider != "cli"
    if metered and not allow_paid_api:
        raise HTTPException(
            400, f"Metered {preset.provider} API: {preset.model_id}. {PAID_CONSENT_REQUIRED}"
        )
    if not metered and allow_paid_api:
        raise HTTPException(400, PAID_FLAG_NEEDS_METERED)


def _checked_file_name(name: str, label: str) -> str:
    """A name that stays inside its book folder: no directories and no hidden files."""
    is_plain = name == Path(name).name and "\\" not in name
    # `ps` escapes unprintable characters, and finding a live run after a restart reads `ps`.
    if not name or not is_plain or name.startswith(".") or not name.isprintable():
        raise HTTPException(400, f"{label} must be a plain file name: {name!r}")
    if len(os.fsencode(name)) > _MAX_FILE_NAME_BYTES:
        raise HTTPException(400, f"{label} is too long for a file name: {name!r}")
    return name


def _is_epub_name(name: str) -> bool:
    return Path(name).suffix.lower() == ".epub"


def _same_file_name(first: str, second: str) -> bool:
    """macOS file systems usually ignore case and Unicode normalization."""
    return (
        unicodedata.normalize("NFC", first).casefold()
        == unicodedata.normalize("NFC", second).casefold()
    )


def _output_file_name(given: str, source_name: str) -> str:
    name = _checked_file_name(given.strip() or f"{Path(source_name).stem}.zh.epub", "output_name")
    if not Path(name).suffix:
        name = _checked_file_name(f"{name}.epub", "output_name")
    if not _is_epub_name(name):
        raise HTTPException(400, f"output_name must end in .epub: {name!r}")
    if _same_file_name(name, source_name):
        raise HTTPException(400, f"output_name must differ from the uploaded file: {name!r}")
    return name


def _remove_if_empty(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        pass


def _store_upload(upload: UploadFile, destination: Path) -> bool:
    """Save the upload without ever replacing a file; True when this call created it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.parent / f".upload-{uuid.uuid4()}.part"
    try:
        size = 0
        with partial.open("wb") as saved:
            while chunk := upload.file.read(_COPY_CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"The file is over {MAX_UPLOAD_BYTES} bytes")
                saved.write(chunk)
        try:
            os.link(partial, destination)
        except FileExistsError:
            if filecmp.cmp(partial, destination, shallow=False):
                return False
            raise HTTPException(
                409, f"A different book is already stored at {destination}; rename your file"
            ) from None
        return True
    finally:
        partial.unlink(missing_ok=True)


def create_app(
    *,
    port: int = DEFAULT_PORT,
    state_dir: Path | None = None,
    child_command: Sequence[str] = _CHILD_COMMAND,
    library_dir: Path | None = None,
) -> FastAPI:
    """Build the API; separate from ``serve`` so tests can call it without a socket."""
    store = _RunStore(state_dir or default_state_dir())
    library = library_dir or default_library_dir()
    children: dict[str, subprocess.Popen[bytes]] = {}
    allowed_origins = {f"http://{name}:{port}" for name in _LOCAL_HOSTNAMES}
    app = FastAPI(
        title="BookWeaver local API",
        description=(
            "Lists the enabled presets, the same as `bookweaver presets`, and starts one run at a "
            "time as a `bookweaver` child process. To translate a book, use `POST /runs/upload`."
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
        "/presets",
        response_model=list[orchestration.Preset],
        summary="List enabled presets",
        description=(
            "Every selection a run may use, the default preset first. Metered presets are paid "
            "and need per-run consent."
        ),
    )
    def list_presets() -> list[orchestration.Preset]:
        return list(orchestration.enabled_presets())

    def ensure_idle() -> None:
        """Call with the store lock held."""
        current = store.read()
        if current is not None and _state(current, children.get(current.run_id)) == "running":
            raise HTTPException(409, f"Run {current.run_id} is still running")

    def launch(
        preset: orchestration.Preset,
        source: Path,
        output: Path,
        *,
        prompt: str | None,
        glossary: str | None,
        allow_paid_api: bool,
    ) -> RunStatus:
        """Call with the store lock held."""
        try:
            planned = orchestration.count_epub_segments(source)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a bad request here.
            raise HTTPException(400, f"Cannot read the EPUB: {exc}") from exc
        run_id = str(uuid.uuid4())
        log_path = output.parent / ".bookweaver_runs" / f"{run_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = [*child_command, str(source), "--output", str(output), "--preset", preset.name]
        if prompt is not None:
            # One token, so a prompt that starts with "-" is not read as an option.
            command.append(f"--prompt={prompt}")
        if glossary is not None:
            command += ["--glossary", str(Path(glossary).expanduser().resolve())]
        if allow_paid_api:
            command.append("--allow-paid-api")
        # Phase 1: record the run before the child exists, so a server that dies right
        # after starting it can still find the child by its arguments (_locate).
        pending = RunRecord(
            schema_version=_RECORD_SCHEMA_VERSION,
            run_id=run_id,
            pid=None,
            process_start=None,
            source=str(source),
            output=str(output),
            preset=preset.name,
            allow_paid_api=allow_paid_api,
            started_at=_now(),
            log_path=str(log_path),
            checkpoint_dir=str(orchestration.default_epub_checkpoint_dir(source, output)),
            planned_segments=planned,
            exit_code=None,
            ended_at=None,
        )
        try:
            store.write(pending)
        except OSError as exc:
            raise HTTPException(500, f"Cannot write the run record: {exc}") from exc
        with log_path.open("ab") as log:
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        # Phase 2: the exact kernel start time makes a later PID reuse detectable.
        record = replace(pending, pid=child.pid, process_start=_process_start(child.pid))
        try:
            store.write(record)
        except OSError as exc:
            # An unrecorded child could not be watched or stopped; stop it now.
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise HTTPException(500, f"Cannot write the run record; run stopped: {exc}") from exc
        children[run_id] = child
        threading.Thread(
            target=lambda: store.finish(run_id, child.wait()), daemon=True, name=f"run-{run_id}"
        ).start()
        return _status(record, child)

    @app.post(
        "/runs",
        status_code=202,
        response_model=RunStatus,
        summary="Start one run from paths on this Mac",
        description=(
            "Starts `bookweaver <source> --output <output> --preset <preset>` in the background. "
            "A metered preset needs `allow_paid_api`. Only one run at a time. "
            "To choose a file instead of typing a path, use `POST /runs/upload`."
        ),
    )
    def start_run(
        body: Annotated[
            RunRequest,
            Body(
                openapi_examples={
                    "default": {
                        "summary": "Required fields only",
                        "value": {
                            "source": "/absolute/path/book.epub",
                            "output": "/absolute/path/book.zh.epub",
                            "preset": DEFAULT_PRESET.value,
                        },
                    }
                }
            ),
        ],
    ) -> RunStatus:
        preset = orchestration.find_preset(body.preset.value)
        _check_consent(preset, body.allow_paid_api)
        source = Path(body.source).expanduser().resolve()
        output = Path(body.output).expanduser().resolve()
        if source.suffix.lower() != ".epub" or not source.is_file():
            raise HTTPException(400, f"Source must be an existing EPUB file: {source}")
        if not output.parent.is_dir():
            raise HTTPException(400, f"Output directory does not exist: {output.parent}")
        with store.lock():
            ensure_idle()
            return launch(
                preset,
                source,
                output,
                prompt=body.prompt,
                glossary=body.glossary,
                allow_paid_api=body.allow_paid_api,
            )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.post(
        "/runs/upload",
        status_code=202,
        response_model=RunStatus,
        summary="Upload a book and translate it",
        description=(
            "Choose an EPUB and press Execute. The translation starts at once and can use "
            f"quota or money, as `preset` says. The book and its translation stay in `{library}/"
            "<book name>/`. Upload the same file with the same preset and prompt to continue from "
            "the saved progress; a different prompt, profile or effort fails, because this API "
            "has no `--force-resume`. Only one run at a time."
        ),
    )
    def upload_run(
        file: Annotated[
            UploadFile,
            File(description=f"The source EPUB, at most {MAX_UPLOAD_BYTES // 1024**2} MiB."),
        ],
        output_name: Annotated[
            str,
            Form(description="Name of the translated file; empty means `<book name>.zh.epub`."),
        ] = "",
        preset: Annotated[
            PresetName,
            Form(description="Model and effort to use, as `GET /presets` explains them."),
        ] = DEFAULT_PRESET,
        prompt: Annotated[
            str, Form(description="Extra translation instructions; empty means none.")
        ] = "",
        allow_paid_api: Annotated[
            bool,
            Form(description="Consent to paid calls for this run, which paid presets require."),
        ] = False,
        row: Annotated[str | None, Form(include_in_schema=False)] = None,
    ) -> RunStatus:
        # An ignored old field would silently run the default preset and spend its quota.
        if row is not None:
            raise HTTPException(400, "The field `row` is now `preset`; nothing was started")
        selected = orchestration.find_preset(preset.value)
        _check_consent(selected, allow_paid_api)
        if "\0" in prompt:
            raise HTTPException(400, "prompt must not contain a NUL character")
        source_name = _checked_file_name(file.filename or "", "The uploaded file")
        if not _is_epub_name(source_name):
            raise HTTPException(400, f"The uploaded file must be an EPUB: {source_name!r}")
        book_dir = library / Path(source_name).stem
        source = book_dir / source_name
        output = book_dir / _output_file_name(output_name, source_name)
        # A link here could write outside the library or replace another book.
        if any(path.is_symlink() for path in (book_dir, source, output)):
            raise HTTPException(400, f"{book_dir} must hold no symbolic link for this book")
        with store.lock():
            ensure_idle()
            created = False
            try:
                created = _store_upload(file, source)
                return launch(
                    selected,
                    source,
                    output,
                    prompt=prompt or None,
                    glossary=None,
                    allow_paid_api=allow_paid_api,
                )
            except (HTTPException, OSError) as exc:
                # A refused upload must not block a corrected copy with the same name.
                if created:
                    source.unlink(missing_ok=True)
                _remove_if_empty(book_dir)
                if isinstance(exc, OSError):
                    raise HTTPException(500, f"Cannot start the run: {exc}") from exc
                raise

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
        return _status(record, children.get(record.run_id))

    @app.post(
        "/runs/current/stop",
        status_code=202,
        response_model=RunStatus,
        summary="Stop the running run",
        description=(
            "Sends Ctrl-C (SIGINT) to the run. Saved batches resume on the next run; the batch "
            "in flight is lost, and on a metered preset it may already be paid for."
        ),
    )
    def stop_run() -> RunStatus:
        record = store.read()
        child = children.get(record.run_id) if record is not None else None
        if record is None or _state(record, child) != "running":
            raise HTTPException(409, "No run is running")
        pid = child.pid if child is not None else _locate(record)
        if pid is None:
            raise HTTPException(409, "No run is running")
        try:
            os.killpg(pid, signal.SIGINT)
        except ProcessLookupError:
            raise HTTPException(409, "No run is running") from None
        return _status(record, child)

    return app


def serve(port: int) -> None:
    """Run the API in the foreground until interrupted; never binds beyond this Mac."""
    uvicorn.run(create_app(port=port), host=HOST, port=port)
