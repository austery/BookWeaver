"""Codex runtime behavior at the executable boundary, through a fake `codex`."""

import json
from pathlib import Path

import pytest

from ai.adapters.providers.codex_provider import CodexProvider, default_codex_home
from ai.model_profiles import resolve_preset
from ai.ports.provider import (
    ProviderAuthenticationError,
    ProviderQuotaError,
    ProviderUnavailableError,
)

_BILLING_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CODEX_ACCESS_TOKEN",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)
_ROSTER = {
    "models": [
        {
            "slug": "gpt-6-luna",
            "visibility": "list",
            "supported_reasoning_levels": [{"effort": "low"}, {"effort": "medium"}],
        },
        {
            "slug": "gpt-6.1-sol",
            "visibility": "hide",
            "supported_reasoning_levels": [{"effort": "low"}],
        },
    ]
}
_OK_BATCH = (
    "tags = (f'<segment id=\"{i}\">译文</segment>' for i in (1, 2, 3))\n"
    'body = "\\n".join(tags) if "flowerpot" in prompt else "译文"\n'
    'Path(args[args.index("--output-last-message") + 1]).write_text(body)\n'
    'print(json.dumps({"type": "turn.completed"}))\n'
)


def _codex(
    tmp_path: Path, *, batch: str = _OK_BATCH, login: str = "Logged in using ChatGPT"
) -> tuple[str, Path]:
    """A fake executable that records each batch's argv, environment and stdin."""
    log = tmp_path / "calls.jsonl"
    path = tmp_path / "codex"
    roster = json.dumps(_ROSTER)
    body = "\n".join(f"    {line}" for line in batch.splitlines())
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "args = sys.argv[1:]\n"
        'if args == ["--version"]:\n    print("codex-cli 0.167.0")\n'
        f'elif args == ["login", "status"]:\n    print({login!r}, file=sys.stderr)\n'
        f'elif args == ["debug", "models"]:\n    print({roster!r})\n'
        "else:\n"
        "    prompt = sys.stdin.read()\n"
        f"    with open({str(log)!r}, 'a') as s:\n"
        "        s.write(json.dumps({'args': args, 'env': dict(os.environ), 'prompt': prompt,\n"
        "            'instructions': Path(args[args.index('-c') + 1:][0] and\n"
        "            [a for a in args if a.startswith('model_instructions_file=')][0]\n"
        "            .split('=', 1)[1].strip('\"')).read_text()}) + '\\n')\n"
        f"{body}\n"
    )
    path.chmod(0o700)
    return str(path), log


def _provider(tmp_path: Path, executable: str) -> CodexProvider:
    return CodexProvider(
        resolve_preset("codex-gpt-6-luna-low"),
        executable=executable,
        codex_home=tmp_path / "home",
        certification_path=tmp_path / "certifications.json",
    )


def test_batch_runs_locked_down_with_the_prompt_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in _BILLING_VARIABLES:
        monkeypatch.setenv(name, "must-not-reach-the-child")
    executable, log = _codex(tmp_path)
    provider = _provider(tmp_path, executable)

    assert provider.translate_batch(["xylophone"], system_prompt="Translate") == ["译文"]

    assert provider.backend == "codex"
    assert provider.runtime_version == "codex-cli 0.167.0"
    probe, batch = [json.loads(line) for line in log.read_text().splitlines()]
    assert "flowerpot" in probe["prompt"] and "xylophone" not in probe["prompt"]
    assert "xylophone" in batch["prompt"]
    args = batch["args"]
    assert not any("xylophone" in arg for arg in args)  # source text stays out of the arguments
    assert args[args.index("--model") + 1] == "gpt-6-luna"
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert 'model_reasoning_effort="low"' in args
    assert 'approval_policy="never"' in args
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--json"):
        assert flag in args
    assert args[args.index("--disable") + 1] == "shell_tool"
    assert 'forced_login_method="chatgpt"' in args
    for option in (
        "skills.include_instructions",
        "include_apps_instructions",
        "include_environment_context",
        "include_permissions_instructions",
        "include_collaboration_mode_instructions",
    ):
        assert f"{option}=false" in args
    assert args[-1] == "-"
    assert "Reply with only the requested text" in batch["instructions"]
    assert batch["env"]["CODEX_HOME"] == str(tmp_path / "home")
    for name in _BILLING_VARIABLES:
        assert name not in batch["env"]


def test_a_login_other_than_chatgpt_stops_before_any_batch(tmp_path: Path) -> None:
    executable, log = _codex(tmp_path, login="Logged in using an API key")

    with pytest.raises(ProviderAuthenticationError, match=r"CODEX_HOME=.*codex login"):
        _provider(tmp_path, executable).translate_batch(["garden"], system_prompt="Translate")
    assert not log.exists()


def test_a_private_home_is_the_default_and_never_the_owners_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert default_codex_home() == tmp_path / "bookweaver" / "codex-home"


def test_a_model_absent_from_the_roster_stops_before_any_batch(tmp_path: Path) -> None:
    executable, log = _codex(tmp_path)
    provider = CodexProvider(
        resolve_preset("codex-gpt-6.1-sol-low"),  # hidden in the fake roster
        executable=executable,
        codex_home=tmp_path / "home",
        certification_path=tmp_path / "certifications.json",
    )

    with pytest.raises(ProviderUnavailableError, match="absent from codex debug models"):
        provider.translate_batch(["garden"], system_prompt="Translate")
    assert not log.exists()


def _failed_turn(message: str) -> str:
    event = {"type": "turn.failed", "error": {"message": message}}
    return f"print({json.dumps(json.dumps(event))})\nraise SystemExit(1)\n"


@pytest.mark.parametrize(
    "batch,error,pattern",
    [
        (_failed_turn("You've hit your usage limit."), ProviderQuotaError, "gpt-6-luna-low"),
        (
            _failed_turn("unexpected status 401 Unauthorized: token expired"),
            ProviderAuthenticationError,
            "codex login",
        ),
        (_failed_turn("stream disconnected"), ProviderUnavailableError, "stream disconnected"),
        ("raise SystemExit(3)\n", ProviderUnavailableError, "status 3"),
        ('print("no final message")\n', ProviderUnavailableError, "no final message"),
    ],
)
def test_failures_map_to_port_errors_and_do_not_retry(
    tmp_path: Path, batch: str, error: type[Exception], pattern: str
) -> None:
    executable, log = _codex(tmp_path, batch=batch)

    with pytest.raises(error, match=pattern):
        _provider(tmp_path, executable).translate_batch(["garden"], system_prompt="Translate")
    assert len(log.read_text().splitlines()) == 1  # the probe stops the run
