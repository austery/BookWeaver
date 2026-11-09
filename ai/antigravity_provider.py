"""The Antigravity runtime spec on the shared subscription CLI adapter."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ai.model_profiles import CERTIFIED_AGY_MODELS, ResolvedModel
from ai.ports.provider import (
    ProviderAuthenticationError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from ai.subscription_cli_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    CliCall,
    ProcessResult,
    PROBE_SAMPLES,
    PROBE_SYSTEM_PROMPT,
    SubscriptionCliProvider,
    default_certification_path,
    probe_problems,
    run_owned_process,
)

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "PROBE_SAMPLES",
    "PROBE_SYSTEM_PROMPT",
    "AntigravityProvider",
    "default_certification_path",
    "probe_problems",
]

_ERROR_LINE_PREFIX = "AGY_ERROR: "
_MAX_ERROR_CHARS = 300
_LOG_FOLDER = "~/.gemini/antigravity-cli/log"


def _failure(returncode: int, stderr: str) -> ProviderUnavailableError:
    """The error for a failed `agy`, from its one structured line and never from raw stderr.

    Raw stderr can quote source text. The `AGY_ERROR` line is agy's own short status, and the
    prompt travels in a private file, so that line is safe to show.
    """
    for line in stderr.splitlines():
        if not line.startswith(_ERROR_LINE_PREFIX):
            continue
        try:
            details = json.loads(line[len(_ERROR_LINE_PREFIX) :])
        except ValueError:
            continue
        if not isinstance(details, dict):
            continue
        short = details.get("short_error")
        if not isinstance(short, str) or not short:
            continue
        short = short[:_MAX_ERROR_CHARS]
        if details.get("error_code") == 429 or details.get("status") == "RESOURCE_EXHAUSTED":
            return ProviderQuotaError(f"Antigravity quota is used up: {short}")
        return ProviderUnavailableError(f"Antigravity exited with status {returncode}: {short}")
    return ProviderUnavailableError(
        f"Antigravity exited with status {returncode}; details are in {_LOG_FOLDER}"
    )


def _execute(args: list[str], *, cwd: Path | None, timeout: float) -> str:
    """Run `agy` once outside the adapter; the compatibility probe script uses this."""
    try:
        result = run_owned_process(args, cwd=cwd, timeout=timeout)
    except OSError as exc:
        raise ProviderUnavailableError(
            "Unable to launch Antigravity; check the executable"
        ) from exc
    return _interpret(result)


def _interpret(result: ProcessResult) -> str:
    """Usable output of a finished `agy`; never expose raw source-bearing output on failure."""
    if result.returncode:
        raise _failure(result.returncode, result.stderr)
    # Terminal status responses are short and outside translated segment blocks.
    # Startup stderr can contain transient auth diagnostics followed by successful login.
    response = result.stdout.strip()
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


class _AntigravitySpec:
    runtime = "antigravity"
    label = "Antigravity"
    roster_name = "agy models"
    temp_prefix = "bookweaver-agy-"
    version_args = ("--version",)
    roster_args: tuple[str, ...] | None = ("models",)
    login_args = None

    def child_environment(self) -> dict[str, str] | None:
        return None

    def check_login(self, result: ProcessResult) -> None:
        raise NotImplementedError("Antigravity has no login guard")

    def interpret(self, result: ProcessResult, call: CliCall) -> str:
        return _interpret(result)

    def parse_roster(self, text: str) -> set[str]:
        return {line.split()[0] for line in text.splitlines() if line.strip()}

    def is_seeded(self, version: str, model_id: str) -> bool:
        return (version, model_id) in CERTIFIED_AGY_MODELS

    def invocation(self, model: ResolvedModel, prompt_path: Path, timeout: float) -> CliCall:
        wrapper = (
            f"Read {prompt_path} and carry out its translation instructions. "
            "Return ONLY the requested translations inline in stdout. "
            "Do not create or modify files. No commentary or markdown fences."
        )
        return CliCall(
            [
                "--model",
                str(model.family),
                "--effort",
                str(model.effort),
                "--print",
                wrapper,
                "--print-timeout",
                f"{timeout:g}s",
            ]
        )


class AntigravityProvider(SubscriptionCliProvider):
    """The shared adapter bound to the Antigravity spec."""

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
        super().__init__(
            _AntigravitySpec(),
            model,
            executable=executable,
            temp_root=temp_root,
            timeout_seconds=timeout_seconds,
            outer_grace_seconds=outer_grace_seconds,
            protocol=protocol,
            certification_path=certification_path,
        )
