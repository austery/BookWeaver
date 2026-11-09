"""One single-attempt adapter for subscription CLI runtimes (SPEC-025 §3.5).

A runtime supplies a `CliRuntimeSpec` with what differs: its commands, its argv, and how it
reports failure. This module owns what is the same for all of them: the process group, the
outer deadline, the private prompt file, segment framing, and the version gate with its probe.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ai.adapters.providers._delimiter import (
    augment_prompt_for_batch,
    join_segments,
    split_response,
)
from ai.model_profiles import ResolvedModel
from ai.ports.provider import (
    ITranslationProvider,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranslationError,
)

# Per-batch response deadline; configurable as antigravity.timeout_seconds.
DEFAULT_TIMEOUT_SECONDS = 600.0

# Synthetic compatibility probe (SPEC-025 §3.3). The probe never sends book passages; the
# translation probe reuses the run's prompt, which may include its glossary terms.
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
_CJK = re.compile(r"[一-鿿]")
_PROBE_ARTIFACT = re.compile(r"```|file://|antigravity-cli/brain/")
_ENTRY_KEYS = ("runtime", "version", "model_id", "protocol", "result", "probed_at")


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def run_owned_process(args: list[str], *, cwd: Path | None, timeout: float) -> ProcessResult:
    """Run one process in its own group and kill the whole group if the wait is interrupted.

    `OSError` from launching and `subprocess.TimeoutExpired` reach the caller unchanged.
    """
    process = subprocess.Popen(
        args,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return ProcessResult(process.returncode, stdout, stderr)


class CliRuntimeSpec(Protocol):
    """What differs between subscription CLI runtimes."""

    # The quota pool: the provenance backend and part of the certification key.
    runtime: str
    # The name shown in errors.
    label: str
    # How errors name the roster command.
    roster_name: str
    temp_prefix: str
    version_args: tuple[str, ...]
    roster_args: tuple[str, ...]

    def execute(self, args: list[str], *, cwd: Path | None, timeout: float) -> str:
        """Run the executable; return its usable output, or raise a port error."""
        ...

    def parse_roster(self, text: str) -> set[str]:
        """Concrete model IDs that the roster command listed."""
        ...

    def is_seeded(self, version: str, model_id: str) -> bool:
        """True when the repository holds recorded probe evidence for this pair."""
        ...

    def invocation(self, model: ResolvedModel, prompt_path: Path, timeout: float) -> list[str]:
        """Arguments for one batch, without the executable. Source text stays in the file."""
        ...


def default_certification_path() -> Path:
    """User-local record of runtime versions that passed the automatic probe."""
    state_home = os.environ.get("XDG_STATE_HOME", "")
    # The XDG base directory specification says to ignore relative values.
    root = Path(state_home) if os.path.isabs(state_home) else Path.home() / ".local" / "state"
    return root / "bookweaver" / "runtime-certifications.json"


def probe_problems(outputs: Sequence[str], *, expect_chinese: bool) -> list[str]:
    """Defects in probe output; empty when every synthetic passage came back usable.

    With the run's own prompt the target language is unknown here (an English target may
    legitimately return the English samples), so only protocol defects count. With the
    fixed Chinese prompt, an untranslated or non-Chinese segment is also a defect.
    """
    problems: list[str] = []
    for index, (source, text) in enumerate(zip(PROBE_SAMPLES, outputs, strict=True), 1):
        stripped = text.strip()
        if not stripped:
            problems.append(f"segment {index} empty")
        elif expect_chinese and (stripped == source or not _CJK.search(stripped)):
            problems.append(f"segment {index} not translated into Chinese")
        if _PROBE_ARTIFACT.search(text):
            problems.append(f"segment {index} contains a fence or artifact link")
    return problems


class _Certifications:
    """Probe results keyed by runtime, version, concrete model and framing protocol.

    The same model can be reached through two runtimes, so a pass on one proves nothing
    about the other.
    """

    def __init__(self, path: Path, runtime: str) -> None:
        self._path = path
        self._runtime = runtime

    def _unavailable(self, problem: str) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            f"{problem} runtime certification record {self._path}; fix or remove it"
        )

    def _load(self) -> list[dict[str, str]]:
        try:
            if not self._path.exists():
                return []
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # ValueError covers JSON and UTF-8 decoding
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
        wanted = (self._runtime, version, model_id, protocol, "pass")
        return any(
            (
                entry["runtime"],
                entry["version"],
                entry["model_id"],
                entry["protocol"],
                entry["result"],
            )
            == wanted
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
                        "runtime": self._runtime,
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


class SubscriptionCliProvider(ITranslationProvider):
    """Frame translation batches and invoke one subscription runtime once per batch."""

    def __init__(
        self,
        spec: CliRuntimeSpec,
        model: ResolvedModel,
        *,
        executable: str,
        temp_root: Path | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        outer_grace_seconds: float = 30,
        protocol: str = "segment_tags",
        certification_path: Path | None = None,
    ) -> None:
        if model.provider != "cli" or model.effort is None or model.family is None:
            raise ValueError(f"{spec.label} requires a resolved CLI model family and effort")
        if timeout_seconds <= 0 or outer_grace_seconds < 0:
            raise ValueError(f"Invalid {spec.label} timeout")
        self.backend = spec.runtime
        self.model = model
        self.runtime_version: str | None = None
        self._spec = spec
        self._executable = executable
        self._temp_root = temp_root
        self._timeout = timeout_seconds
        self._grace = outer_grace_seconds
        self._protocol = protocol
        self._certifications = _Certifications(
            certification_path if certification_path is not None else default_certification_path(),
            spec.runtime,
        )

    def _run(self, args: Sequence[str], *, cwd: Path | None, timeout: float) -> str:
        try:
            return self._spec.execute([self._executable, *args], cwd=cwd, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError(f"{self._spec.label} exceeded its outer deadline") from exc
        except ProviderQuotaError as exc:
            raise ProviderQuotaError(f"{exc} (model {self.model.model_id})") from exc

    def _discover(self, system_prompt: str) -> None:
        if self.runtime_version is not None:
            return
        version = self._run(self._spec.version_args, cwd=None, timeout=30)
        roster = self._run(self._spec.roster_args, cwd=None, timeout=30)
        model_id = self.model.model_id
        if model_id not in self._spec.parse_roster(roster):
            raise ProviderUnavailableError(
                f"Selected model {model_id} is absent from {self._spec.roster_name}; "
                "update the registry explicitly"
            )
        if not self._spec.is_seeded(version, model_id) and not self._certifications.contains(
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
        label = f"{self._spec.label} {version} compatibility probe for {self.model.model_id}"
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
        problems = probe_problems(outputs, expect_chinese=not translation)
        if problems:
            raise ProviderUnavailableError(f"{label} failed: {'; '.join(problems)}")

    def _invoke(self, items: list[str], system_prompt: str) -> list[str]:
        prompt = augment_prompt_for_batch(system_prompt, len(items), protocol=self._protocol)
        prompt += "\n\n" + join_segments(items, protocol=self._protocol)
        with tempfile.TemporaryDirectory(
            prefix=self._spec.temp_prefix, dir=self._temp_root
        ) as directory:
            workspace = Path(directory)
            prompt_path = workspace / "prompt.txt"
            with prompt_path.open("x", encoding="utf-8") as stream:
                os.chmod(prompt_path, 0o600)
                stream.write(prompt)
            output = self._run(
                self._spec.invocation(self.model, prompt_path, self._timeout),
                cwd=workspace,
                timeout=self._timeout + self._grace,
            )
        return split_response(output, len(items), protocol=self._protocol)

    def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
        if not segments:
            return []
        self._discover(system_prompt)
        return self._invoke(list(segments), system_prompt)
