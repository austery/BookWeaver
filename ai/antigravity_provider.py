"""Single-attempt Antigravity adapter with private prompt-file transport."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from ai.adapters.providers._delimiter import (
    augment_prompt_for_batch,
    join_segments,
    split_response,
)
from ai.model_profiles import CERTIFIED_AGY_VERSIONS, ResolvedModel
from ai.ports.provider import (
    ITranslationProvider,
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
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
            r"^(?:error[: ]+)?(?:you are not logged in|authentication required|please sign in)",
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


class AntigravityProvider(ITranslationProvider):
    """Frame translation batches and invoke the subscription runtime once per batch."""

    def __init__(
        self,
        model: ResolvedModel,
        *,
        executable: str = "agy",
        temp_root: Path | None = None,
        timeout_seconds: float = 600,
        outer_grace_seconds: float = 30,
        protocol: str = "segment_tags",
    ) -> None:
        if model.provider != "cli" or model.effort is None:
            raise ValueError("Antigravity requires a resolved CLI model and effort")
        if timeout_seconds <= 0 or outer_grace_seconds < 0:
            raise ValueError("Invalid Antigravity timeout")
        self.model = model
        self.runtime_version: str | None = None
        self._executable = executable
        self._temp_root = temp_root
        self._timeout = timeout_seconds
        self._grace = outer_grace_seconds
        self._protocol = protocol

    def _run(self, args: list[str], *, cwd: Path | None, timeout: float) -> str:
        try:
            return _execute([self._executable, *args], cwd=cwd, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderTimeoutError("Antigravity exceeded its outer deadline") from exc

    def _discover(self) -> None:
        if self.runtime_version is not None:
            return
        version = self._run(["--version"], cwd=None, timeout=30)
        if version not in CERTIFIED_AGY_VERSIONS:
            raise ProviderUnavailableError(
                f"Antigravity {version} requires a compatibility probe before updating CERTIFIED_AGY_VERSIONS"
            )
        roster = self._run(["models"], cwd=None, timeout=30)
        identifiers = {line.split()[0] for line in roster.splitlines() if line.strip()}
        if self.model.model_id not in identifiers:
            raise ProviderUnavailableError(
                f"Selected model {self.model.model_id} is absent from agy models; update the registry explicitly"
            )
        self.runtime_version = version

    def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
        if not segments:
            return []
        self._discover()
        items = list(segments)
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
                    self.model.model_id,
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
