"""Claude Code runtime behavior at the executable boundary, through a fake `claude`."""

import json
from pathlib import Path

import pytest

from ai.adapters.providers.claude_code_provider import ClaudeCodeProvider
from ai.model_profiles import resolve_preset
from ai.ports.provider import (
    OutputTruncatedError,
    ProviderAuthenticationError,
    ProviderQuotaError,
    ProviderUnavailableError,
)

# A key or base URL moves the run off the subscription; the rest come from a parent session.
_UNSAFE_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDECODE",
    "CLAUDE_CODE_SIMPLE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_EFFORT",
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
)
_SUBSCRIPTION = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
_OK_BATCH = (
    "tags = (f'<segment id=\"{i}\">译文</segment>' for i in (1, 2, 3))\n"
    'body = "\\n".join(tags) if "flowerpot" in prompt else "译文"\n'
    'print(json.dumps({"is_error": False, "num_turns": 1, "stop_reason": "end_turn",'
    ' "result": body}))\n'
)


def _claude(
    tmp_path: Path, *, batch: str = _OK_BATCH, login: dict[str, object] | None = None
) -> tuple[str, Path]:
    """A fake executable that records each batch's argv, environment, stdin and directory."""
    log = tmp_path / "calls.jsonl"
    path = tmp_path / "claude"
    status = json.dumps(_SUBSCRIPTION if login is None else login)
    body = "\n".join(f"    {line}" for line in batch.splitlines())
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        'if args == ["--version"]:\n    print("2.1.311 (Claude Code)")\n'
        f'elif args == ["auth", "status"]:\n    print({status!r})\n'
        "else:\n"
        "    prompt = sys.stdin.read()\n"
        f"    with open({str(log)!r}, 'a') as s:\n"
        "        s.write(json.dumps({'args': args, 'env': dict(os.environ), 'prompt': prompt,\n"
        "            'files': os.listdir('.')}) + '\\n')\n"
        f"{body}\n"
    )
    path.chmod(0o700)
    return str(path), log


def _provider(tmp_path: Path, executable: str) -> ClaudeCodeProvider:
    return ClaudeCodeProvider(
        resolve_preset("claude-sonnet-5-5-low"),
        executable=executable,
        certification_path=tmp_path / "certifications.json",
    )


def test_batch_runs_locked_down_with_the_prompt_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in _UNSAFE_VARIABLES:
        monkeypatch.setenv(name, "must-not-reach-the-child")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/owner/choice")
    executable, log = _claude(tmp_path)
    provider = _provider(tmp_path, executable)

    assert provider.translate_batch(["xylophone"], system_prompt="Translate") == ["译文"]

    assert provider.backend == "claude-code"
    assert provider.runtime_version == "2.1.311 (Claude Code)"
    probe, batch = [json.loads(line) for line in log.read_text().splitlines()]
    assert "flowerpot" in probe["prompt"] and "xylophone" not in probe["prompt"]
    assert "xylophone" in batch["prompt"]
    args = batch["args"]
    assert not any("xylophone" in arg for arg in args)  # source text stays out of the arguments
    assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
    assert args[args.index("--effort") + 1] == "low"
    assert args[args.index("--output-format") + 1] == "json"
    assert "Reply with only the requested text" in args[args.index("--system-prompt") + 1]
    for flag in (
        "-p",
        "--restricted",
        "--strict-mcp-config",
        "--tools=",
        "--no-session-persistence",
    ):
        assert flag in args
    assert "--bare" not in args  # it would read an API key and never the subscription login
    assert batch["files"] == []  # `@name` in book text can inline a file from this directory
    assert batch["env"]["CLAUDE_CODE_MAX_RETRIES"] == "0"
    assert batch["env"]["CLAUDE_CONFIG_DIR"] == "/owner/choice"
    for name in _UNSAFE_VARIABLES:
        assert name not in batch["env"]


@pytest.mark.parametrize(
    "login",
    [
        {"loggedIn": True, "authMethod": "api_key"},
        {"loggedIn": False, "authMethod": "claude.ai"},
        {},
    ],
)
def test_a_login_other_than_the_subscription_stops_before_any_batch(
    tmp_path: Path, login: dict[str, object]
) -> None:
    executable, log = _claude(tmp_path, login=login)

    with pytest.raises(ProviderAuthenticationError, match="claude auth login"):
        _provider(tmp_path, executable).translate_batch(["garden"], system_prompt="Translate")
    assert not log.exists()


def test_a_prompt_that_claude_code_would_run_as_a_command_never_starts_it(tmp_path: Path) -> None:
    executable, log = _claude(tmp_path)

    with pytest.raises(ProviderUnavailableError, match="starts with '/'"):
        _provider(tmp_path, executable).translate_batch(["garden"], system_prompt="/compact")
    assert not log.exists()


def _report(**fields: object) -> str:
    return f"print({json.dumps(json.dumps(fields))})\n"


@pytest.mark.parametrize(
    "batch,error,pattern",
    [
        (
            _report(is_error=True, api_error_status=429, num_turns=1, result="API Error: (429)")
            + "raise SystemExit(1)\n",
            ProviderQuotaError,
            "claude-sonnet-5-5-low",
        ),
        (
            _report(
                is_error=True, api_error_status=401, num_turns=1, result="Failed to authenticate"
            )
            + "raise SystemExit(1)\n",
            ProviderAuthenticationError,
            "claude auth login",
        ),
        (
            _report(is_error=True, api_error_status=529, num_turns=1, result="Overloaded"),
            ProviderUnavailableError,
            "Overloaded",
        ),
        # What a local command leaves: success, no model turn, no translation.
        (
            _report(is_error=False, num_turns=0, result=""),
            ProviderUnavailableError,
            "0 model turns",
        ),
        (
            _report(is_error=False, num_turns=1, stop_reason="end_turn", result=" "),
            ProviderUnavailableError,
            "empty output",
        ),
        # A reply cut at the output cap, a refusal, and a continued reply all carry text.
        (
            _report(is_error=False, num_turns=1, stop_reason="max_tokens", result="译"),
            OutputTruncatedError,
            "token cap",
        ),
        (
            _report(
                is_error=True, num_turns=4, result="API Error: exceeded the output token maximum."
            )
            + "raise SystemExit(1)\n",
            OutputTruncatedError,
            "token cap",
        ),
        (
            _report(is_error=False, num_turns=1, stop_reason="refusal", result="I cannot"),
            ProviderUnavailableError,
            "'refusal'",
        ),
        (
            _report(is_error=False, num_turns=2, stop_reason="end_turn", result="后半"),
            ProviderUnavailableError,
            "2 model turns",
        ),
        # Model output never enters an error message.
        (
            _report(is_error=False, num_turns=1, stop_reason="end_turn", result="secret reply")
            + "raise SystemExit(2)\n",
            ProviderUnavailableError,
            "status 2$",
        ),
        ("raise SystemExit(3)\n", ProviderUnavailableError, "status 3"),
        ('print("not a result object")\n', ProviderUnavailableError, "no result object"),
    ],
)
def test_failures_map_to_port_errors_and_do_not_retry(
    tmp_path: Path, batch: str, error: type[Exception], pattern: str
) -> None:
    executable, log = _claude(tmp_path, batch=batch)

    with pytest.raises(error, match=pattern):
        _provider(tmp_path, executable).translate_batch(["garden"], system_prompt="Translate")
    assert len(log.read_text().splitlines()) == 1  # the probe stops the run
