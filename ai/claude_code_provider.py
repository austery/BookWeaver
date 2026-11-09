"""The Claude Code runtime spec on the shared subscription CLI adapter (SPEC-025 §5).

`claude -p` is a coding agent, so the spec strips it down to a translator. The flags and guards
come from the offline request capture in `docs/plans/2026-11-09-claude-code-request-capture.md`:
`--restricted` keeps the owner's `CLAUDE.md`, memory and skills out of the request,
`--system-prompt` replaces the coding prompt, and the child runs in an empty directory because
`@name` in book text would inline a file from the working directory. The child environment holds
no API key, because a key beats the claude.ai login and turns a subscription run into a metered
one.
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
)

_MAX_ERROR_CHARS = 300
_DROPPED_VARIABLES = frozenset({"CLAUDECODE", "CODEX_API_KEY", "OPENAI_API_KEY"})
# `ANTHROPIC_*` holds keys, tokens and the base URL. A parent Claude Code session exports
# `CLAUDE_*`, such as CLAUDE_EFFORT and CLAUDE_CODE_SIMPLE, the variable `--bare` sets.
_DROPPED_PREFIXES = ("ANTHROPIC_", "CLAUDE_")
# The owner's choice of login folder; it is not a session variable.
_KEPT_VARIABLES = frozenset({"CLAUDE_CONFIG_DIR"})
_SYSTEM_PROMPT = (
    "Carry out the user's message exactly. Reply with only the requested text. "
    "Do not use tools, do not create files, and add no commentary or markdown fences."
)
_SIGN_IN = "Sign in to Claude Code with your Claude subscription: claude auth login"


class _ClaudeCodeSpec:
    runtime = "claude-code"
    label = "Claude Code"
    roster_name = "claude"
    temp_prefix = "bookweaver-claude-"
    version_args = ("--version",)
    # Claude Code has no roster command; an unknown model fails the probe instead.
    roster_args: tuple[str, ...] | None = None
    login_args: tuple[str, ...] | None = ("auth", "status")

    def child_environment(self) -> dict[str, str]:
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in _KEPT_VARIABLES
            or (name not in _DROPPED_VARIABLES and not name.startswith(_DROPPED_PREFIXES))
        }
        # Without this the CLI retries a 401 or 429 past 100 seconds and prints nothing.
        environment["CLAUDE_CODE_MAX_RETRIES"] = "0"
        return environment

    def check_login(self, result: ProcessResult) -> None:
        """Only a claude.ai login draws on the subscription; `api_key` would bill per request."""
        try:
            status = json.loads(result.stdout)
        except ValueError:
            status = None
        if (
            result.returncode
            or not isinstance(status, dict)
            or status.get("loggedIn") is not True
            or status.get("authMethod") != "claude.ai"
        ):
            raise ProviderAuthenticationError(_SIGN_IN)

    def interpret(self, result: ProcessResult, call: CliCall) -> str:
        if call.stdin is None:  # `--version`: plain text
            if result.returncode:
                raise ProviderUnavailableError(
                    f"Claude Code exited with status {result.returncode}"
                )
            return result.stdout.strip()
        # A failed batch also prints the result object, with exit status 1.
        try:
            report = json.loads(result.stdout)
        except ValueError:
            report = None
        if not isinstance(report, dict):
            raise ProviderUnavailableError(
                f"Claude Code exited with status {result.returncode} and no result object"
            )
        text = report.get("result")
        if report.get("is_error") or result.returncode:
            status = report.get("api_error_status")
            detail = text[:_MAX_ERROR_CHARS] if isinstance(text, str) else "no message"
            if status == 429:
                raise ProviderQuotaError(f"Claude Code quota is used up: {detail}")
            if status in (401, 403):
                raise ProviderAuthenticationError(_SIGN_IN)
            raise ProviderUnavailableError(f"Claude Code turn failed: {detail}")
        if report.get("num_turns") != 1:
            # A local command, such as a prompt that starts with `/`, ends with no model turn.
            raise ProviderUnavailableError(
                f"Claude Code ran {report.get('num_turns')} model turns instead of one"
            )
        if not isinstance(text, str) or not text.strip():
            raise ProviderUnavailableError("Claude Code returned empty output")
        return text.strip()

    def parse_roster(self, text: str) -> set[str]:
        raise NotImplementedError("Claude Code has no roster command")

    def is_seeded(self, version: str, model_id: str) -> bool:
        return False  # No live evidence yet; every pair probes with the run's own prompt.

    def invocation(self, model: ResolvedModel, prompt_path: Path, timeout: float) -> CliCall:
        prompt = prompt_path.read_text(encoding="utf-8")
        if prompt.startswith("/"):
            raise ProviderUnavailableError(
                "Claude Code runs a prompt that starts with '/' as a local command; "
                "change the first character of the translation prompt"
            )
        empty = prompt_path.parent / "empty"
        empty.mkdir()
        args = [
            "-p",
            "--restricted",
            "--strict-mcp-config",
            # The `=` form cannot lose its empty value; `--tools ""` can, and then swallows a flag.
            "--tools=",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--model",
            str(model.family),
            "--effort",
            str(model.effort),
            "--system-prompt",
            _SYSTEM_PROMPT,
        ]
        return CliCall(args, stdin=prompt, cwd=empty)


class ClaudeCodeProvider(SubscriptionCliProvider):
    """The shared adapter bound to the Claude Code spec."""

    def __init__(
        self,
        model: ResolvedModel,
        *,
        executable: str = "claude",
        temp_root: Path | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        outer_grace_seconds: float = 30,
        protocol: str = "segment_tags",
        certification_path: Path | None = None,
    ) -> None:
        super().__init__(
            _ClaudeCodeSpec(),
            model,
            executable=executable,
            temp_root=temp_root,
            timeout_seconds=timeout_seconds,
            outer_grace_seconds=outer_grace_seconds,
            protocol=protocol,
            certification_path=certification_path,
        )
