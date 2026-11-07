"""Single-attempt Antigravity adapter with private prompt-file transport."""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ai.adapters.providers._delimiter import (
    augment_prompt_for_batch,
    join_segments,
    split_response,
)
from ai.model_profiles import CERTIFIED_AGY_MODELS, ResolvedModel
from ai.ports.provider import (
    ITranslationProvider,
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranslationError,
)


def _execute(args: list[str], *, cwd: Path | None, timeout: float) -> str:
    """Run one owned process group; never expose raw source-bearing output on failure."""
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise ProviderUnavailableError(
            "Unable to launch Antigravity; check the executable"
        ) from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    if process.returncode:
        raise ProviderUnavailableError(f"Antigravity exited with status {process.returncode}")
    # Terminal status responses are short and outside translated segment blocks.
    # Startup stderr can contain transient auth diagnostics followed by successful login.
    response = stdout.strip()
    status = response.lower()
    if not response:
        raise ProviderUnavailableError("Antigravity returned empty output")
    if len(response) < 1000 and not response.startswith("<segment"):
        if re.match(
            r"^(?:error[: ]+)?(?:(?:you are )?not logged in|authentication required|please sign in)",
            status,
        ):
            raise ProviderAuthenticationError("Sign in to Antigravity before resuming")
        if re.match(r"^(?:error[: ]+)?(?:timed out waiting|timeout|response timed out)", status):
            raise ProviderTimeoutError("Antigravity timed out waiting for a response")
        if re.match(
            r"^(?:error[: ]+)?(?:resource exhausted|quota exceeded|capacity exhausted|network error)",
            status,
        ):
            raise ProviderUnavailableError("Antigravity capacity or transport is unavailable")
        if "file://" in status or ".gemini/antigravity-cli/brain/" in status:
            raise ProviderUnavailableError(
                "Antigravity returned an artifact instead of inline text"
            )
    return response


# Per-batch response deadline; configurable as antigravity.timeout_seconds.
DEFAULT_TIMEOUT_SECONDS = 600.0

# Synthetic compatibility probe (SPEC-025 §3.3). No book content is ever sent by the probe.
PROBE_SAMPLES = (
    "The old key was hidden beneath a cracked flowerpot beside the garden gate.",
    "When the power failed, the program resumed from its last saved checkpoint "
    "instead of starting over.",
    "Through the small telescope she counted four moons circling the bright planet.",
)
# Used only for the delimiter protocol: its production prompt (glossary extraction)
# returns terms, not translations, so it cannot judge a translation probe.
PROBE_SYSTEM_PROMPT = (
    "You are a professional translator. Translate each segment into Simplified Chinese. "
    "Keep the segment structure exactly as requested."
)
_CJK = re.compile(r"[\u4e00-\u9fff]")
_PROBE_ARTIFACT = re.compile(r"```|file://|antigravity-cli/brain/")
_ENTRY_KEYS = ("runtime", "version", "model_id", "protocol", "result", "probed_at")


def default_certification_path() -> Path:
    """User-local record of runtime versions that passed the automatic probe."""
    state_home = os.environ.get("XDG_STATE_HOME", "")
    # The XDG base directory specification says to ignore relative values.
    root = Path(state_home) if os.path.isabs(state_home) else Path.home() / ".local" / "state"
    return root / "bookweaver" / "runtime-certifications.json"


def probe_problems(outputs: Sequence[str], *, require_chinese: bool) -> list[str]:
    """Defects in probe output; empty when every synthetic passage was translated in order."""
    problems: list[str] = []
    for index, (source, text) in enumerate(zip(PROBE_SAMPLES, outputs, strict=True), 1):
        stripped = text.strip()
        if not stripped:
            problems.append(f"segment {index} empty")
        elif stripped == source:
            problems.append(f"segment {index} returned untranslated")
        elif require_chinese and not _CJK.search(stripped):
            problems.append(f"segment {index} has no Chinese")
        if _PROBE_ARTIFACT.search(text):
            problems.append(f"segment {index} contains a fence or artifact link")
    return problems


class _Certifications:
    """Probe results keyed by runtime version, concrete model and framing protocol."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _unavailable(self, problem: str) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            f"{problem} runtime certification record {self._path}; fix or remove it"
        )

    def _load(self) -> list[dict[str, str]]:
        try:
            if not self._path.exists():
                return []
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise self._unavailable("Unreadable") from exc
        if not isinstance(data, list):
            raise self._unavailable("Invalid")
        entries: list[dict[str, str]] = []
        for item in data:
            if not (
                isinstance(item, dict)
                and set(item) == set(_ENTRY_KEYS)
                and all(isinstance(item[key], str) for key in _ENTRY_KEYS)
            ):
                raise self._unavailable("Invalid entry in")
            entries.append({key: item[key] for key in _ENTRY_KEYS})
        return entries

    def contains(self, version: str, model_id: str, protocol: str) -> bool:
        return any(
            (entry["version"], entry["model_id"], entry["protocol"], entry["result"])
            == (version, model_id, protocol, "pass")
            for entry in self._load()
        )

    def record(self, version: str, model_id: str, protocol: str) -> None:
        """Append one pass under an exclusive lock, then replace the file atomically."""
        directory = self._path.parent
        temporary: Path | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / f".{self._path.name}.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                entries = self._load()
                entries.append(
                    {
                        "runtime": "antigravity",
                        "version": version,
                        "model_id": model_id,
                        "protocol": protocol,
                        "result": "pass",
                        "probed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
                )
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=directory,
                    prefix=".certifications-",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    json.dump(entries, stream, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._path)
                temporary = None
                descriptor = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except OSError as exc:
            raise self._unavailable("Unwritable") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class AntigravityProvider(ITranslationProvider):
    """Frame translation batches and invoke the subscription runtime once per batch."""

    backend = "antigravity"

    def __init__(
        self,
        model: ResolvedModel,
        *,
        executable: str = "agy",
        temp_root: Path | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        outer_grace_seconds: float = 30,
        protocol: str = "segment_tags",
        certification_path: Path | None = None,
    ) -> None:
        if model.provider != "cli" or model.effort is None or model.family is None:
            raise ValueError("Antigravity requires a resolved CLI model family and effort")
        if timeout_seconds <= 0 or outer_grace_seconds < 0:
            raise ValueError("Invalid Antigravity timeout")
        self.model = model
        self.runtime_version: str | None = None
        self._executable = executable
        self._temp_root = temp_root
        self._timeout = timeout_seconds
        self._grace = outer_grace_seconds
        self._protocol = protocol
        self._certifications = _Certifications(
            certification_path if certification_path is not None else default_certification_path()
        )

    def _run(self, args: list[str], *, cwd: Path | None, timeout: float) -> str:
        try:
            return _execute([self._executable, *args], cwd=cwd, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError("Antigravity exceeded its outer deadline") from exc

    def _discover(self, system_prompt: str) -> None:
        if self.runtime_version is not None:
            return
        version = self._run(["--version"], cwd=None, timeout=30)
        roster = self._run(["models"], cwd=None, timeout=30)
        identifiers = {line.split()[0] for line in roster.splitlines() if line.strip()}
        model_id = self.model.model_id
        if model_id not in identifiers:
            raise ProviderUnavailableError(
                f"Selected model {model_id} is absent from agy models; update the registry explicitly"
            )
        if (version, model_id) not in CERTIFIED_AGY_MODELS and not self._certifications.contains(
            version, model_id, self._protocol
        ):
            self._probe(version, system_prompt)
            self._certifications.record(version, model_id, self._protocol)
        self.runtime_version = version

    def _probe(self, version: str, system_prompt: str) -> None:
        """Send the synthetic passages through the production path; stop on any defect.

        Translation (segment tags) uses the run's own production prompt. The delimiter
        protocol serves glossary extraction, whose prompt yields terms, so it uses
        PROBE_SYSTEM_PROMPT to judge framing, invocation and parsing.
        """
        translation = self._protocol == "segment_tags"
        label = f"Antigravity {version} compatibility probe for {self.model.model_id}"
        try:
            outputs = self._invoke(
                list(PROBE_SAMPLES), system_prompt if translation else PROBE_SYSTEM_PROMPT
            )
        except ProviderUnavailableError as exc:
            # Keep auth/timeout/transport types for callers; name the probe in the message.
            raise type(exc)(f"{label} stopped: {exc}") from exc
        except TranslationError as exc:
            # A split-eligible parse error must not reach the engine's binary split.
            raise ProviderUnavailableError(f"{label} failed: {exc}") from exc
        problems = probe_problems(outputs, require_chinese=not translation)
        if problems:
            raise ProviderUnavailableError(f"{label} failed: {'; '.join(problems)}")

    def _invoke(self, items: list[str], system_prompt: str) -> list[str]:
        prompt = augment_prompt_for_batch(system_prompt, len(items), protocol=self._protocol)
        prompt += "\n\n" + join_segments(items, protocol=self._protocol)
        with tempfile.TemporaryDirectory(
            prefix="bookweaver-agy-", dir=self._temp_root
        ) as directory:
            workspace = Path(directory)
            prompt_path = workspace / "prompt.txt"
            with prompt_path.open("x", encoding="utf-8") as stream:
                os.chmod(prompt_path, 0o600)
                stream.write(prompt)
            wrapper = (
                f"Read {prompt_path} and carry out its translation instructions. "
                "Return ONLY the requested translations inline in stdout. "
                "Do not create or modify files. No commentary or markdown fences."
            )
            output = self._run(
                [
                    "--model",
                    str(self.model.family),
                    "--effort",
                    str(self.model.effort),
                    "--print",
                    wrapper,
                    "--print-timeout",
                    f"{self._timeout:g}s",
                ],
                cwd=workspace,
                timeout=self._timeout + self._grace,
            )
        return split_response(output, len(items), protocol=self._protocol)

    def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
        if not segments:
            return []
        self._discover(system_prompt)
        return self._invoke(list(segments), system_prompt)
