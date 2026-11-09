"""The Codex runtime spec on the shared subscription CLI adapter (SPEC-025 §5).

`codex exec` is a coding agent, so the spec strips it down to a translator: a private
CODEX_HOME keeps the owner's `AGENTS.md` and skills out of every batch, because
`--ignore-user-config` does not remove them; `model_instructions_file` replaces the coding prompt;
and the child environment holds no API key, because a key would turn a subscription run into a
metered one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ai.model_profiles import ResolvedModel
from ai.ports.provider import (
    ProviderAuthenticationError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from ai.subscription_cli_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    CliCall,
    ProcessResult,
    SubscriptionCliProvider,
    default_certification_path,
)

_MAX_ERROR_CHARS = 300
# Any of these can move a run off the ChatGPT subscription or to another endpoint.
_DROPPED_VARIABLES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CODEX_ACCESS_TOKEN",
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    }
)
_INSTRUCTIONS = (
    "Carry out the user's message exactly. Reply with only the requested text. "
    "Do not use tools, do not create files, and add no commentary or markdown fences."
)


def default_codex_home() -> Path:
    """BookWeaver's own Codex login, next to its runtime certifications."""
    return default_certification_path().parent / "codex-home"


def _turn_failure(stdout: str) -> str | None:
    """The message of the `turn.failed` JSONL event; this is Codex's own status, not raw stderr."""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "turn.failed":
            continue
        error = event.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message:
            return message[:_MAX_ERROR_CHARS]
    return None


class _CodexSpec:
    runtime = "codex"
    label = "Codex"
    roster_name = "codex debug models"
    temp_prefix = "bookweaver-codex-"
    version_args = ("--version",)
    roster_args = ("debug", "models")
    login_args: tuple[str, ...] | None = ("login", "status")

    def __init__(self, home: Path) -> None:
        self._home = home

    def _sign_in(self) -> ProviderAuthenticationError:
        return ProviderAuthenticationError(
            f"Sign in to Codex for BookWeaver with ChatGPT: CODEX_HOME={self._home} codex login"
        )

    def child_environment(self) -> dict[str, str]:
        self._home.mkdir(mode=0o700, parents=True, exist_ok=True)
        environment = {
            name: value for name, value in os.environ.items() if name not in _DROPPED_VARIABLES
        }
        environment["CODEX_HOME"] = str(self._home)
        return environment

    def check_login(self, result: ProcessResult) -> None:
        # `codex login status` writes to stderr. An API key login would bill per request.
        if result.returncode or "using ChatGPT" not in result.stdout + result.stderr:
            raise self._sign_in()

    def interpret(self, result: ProcessResult, output_file: Path | None) -> str:
        failure = _turn_failure(result.stdout)
        if failure is not None:
            lowered = failure.lower()
            if "usage limit" in lowered or "429" in lowered or "rate limit" in lowered:
                raise ProviderQuotaError(f"Codex quota is used up: {failure}")
            if "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
                raise self._sign_in()
            raise ProviderUnavailableError(f"Codex turn failed: {failure}")
        if result.returncode:
            raise ProviderUnavailableError(f"Codex exited with status {result.returncode}")
        if output_file is None:
            return result.stdout.strip()
        try:
            response = output_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ProviderUnavailableError("Codex wrote no final message") from exc
        if not response:
            raise ProviderUnavailableError("Codex returned empty output")
        return response

    def parse_roster(self, text: str) -> set[str]:
        """Every listed model at every effort it supports, composed as `<slug>-<effort>`.

        Codex lists the two separately; the composed ID exists only in BookWeaver's provenance.
        """
        try:
            models = json.loads(text)["models"]
            return {
                f"{model['slug']}-{level['effort']}"
                for model in models
                if model.get("visibility") == "list"
                for level in model["supported_reasoning_levels"]
            }
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderUnavailableError(
                "Codex model roster has an unexpected shape; update ai/codex_provider.py"
            ) from exc

    def is_seeded(self, version: str, model_id: str) -> bool:
        return False  # Every pair probes with the run's own prompt; the recorded probe did not.

    def invocation(self, model: ResolvedModel, prompt_path: Path, timeout: float) -> CliCall:
        workspace = prompt_path.parent
        instructions = workspace / "instructions.md"
        instructions.write_text(_INSTRUCTIONS, encoding="utf-8")
        output_file = workspace / "final-message.txt"
        options = (
            'approval_policy="never"',
            'forced_login_method="chatgpt"',
            f"model_reasoning_effort={json.dumps(model.effort)}",
            f"model_instructions_file={json.dumps(str(instructions))}",
            "skills.include_instructions=false",
            "include_apps_instructions=false",
            "include_environment_context=false",
            "include_permissions_instructions=false",
            "include_collaboration_mode_instructions=false",
        )
        args = [
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--disable",
            "shell_tool",
            "--model",
            str(model.family),
            "--json",
            "--output-last-message",
            str(output_file),
            "--cd",
            str(workspace),
        ]
        for option in options:
            args += ["-c", option]
        args.append("-")
        return CliCall(args, stdin=prompt_path.read_text(encoding="utf-8"), output_file=output_file)


class CodexProvider(SubscriptionCliProvider):
    """The shared adapter bound to the Codex spec."""

    def __init__(
        self,
        model: ResolvedModel,
        *,
        executable: str = "codex",
        codex_home: Path | None = None,
        temp_root: Path | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        outer_grace_seconds: float = 30,
        protocol: str = "segment_tags",
        certification_path: Path | None = None,
    ) -> None:
        super().__init__(
            _CodexSpec(codex_home if codex_home is not None else default_codex_home()),
            model,
            executable=executable,
            temp_root=temp_root,
            timeout_seconds=timeout_seconds,
            outer_grace_seconds=outer_grace_seconds,
            protocol=protocol,
            certification_path=certification_path,
        )
