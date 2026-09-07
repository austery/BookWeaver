"""Antigravity adapter behavior at the executable boundary."""

from pathlib import Path

import pytest

from ai.antigravity_provider import AntigravityProvider
from ai.model_profiles import resolve_profile
from ai.ports.provider import (
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TranslationError,
)


def test_temp_file_protocol_returns_ordered_translations_and_cleans_up(tmp_path: Path) -> None:
    executable = tmp_path / "agy"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        'if sys.argv[1:] == ["models"]:\n'
        '    print("gemini-3.8-flash-low\\tGemini 3.8 Flash (Low)")\n'
        'elif sys.argv[1:] == ["--version"]:\n'
        '    print("1.1.27")\n'
        "else:\n"
        '    assert sys.argv[sys.argv.index("--effort") + 1] == "low"\n'
        '    prompt = pathlib.Path("prompt.txt").read_text()\n'
        '    assert "<segment id=" in prompt and "garden" in prompt\n'
        '    print(\'<segment id="1">花园</segment>\\n<segment id="2">月亮</segment>\')\n'
    )
    executable.chmod(0o700)
    workspace = tmp_path / "prompts"
    workspace.mkdir()
    provider = AntigravityProvider(
        resolve_profile(), executable=str(executable), temp_root=workspace
    )
    assert provider.translate_batch(["garden", "moon"], system_prompt="Translate to Chinese") == [
        "花园",
        "月亮",
    ]
    assert list(workspace.iterdir()) == []
    assert provider.runtime_version == "1.1.27"


@pytest.mark.parametrize(
    "behavior,error",
    [
        ('print("You are not logged in")', ProviderAuthenticationError),
        ('print("file:///tmp/translation.md")', ProviderUnavailableError),
        ('print("")', ProviderUnavailableError),
        ("raise SystemExit(2)", ProviderUnavailableError),
        ("print('<segment id=\"1\">译文</segment>')", TranslationError),
        ("import time; time.sleep(30)", ProviderTimeoutError),
    ],
)
def test_failure_cleans_prompt_and_does_not_retry(
    tmp_path: Path, behavior: str, error: type[Exception]
) -> None:
    executable = tmp_path / "agy"
    calls = tmp_path / "calls"
    executable.write_text(
        "#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
        'if sys.argv[1:] == ["--version"]: print("1.1.27")\n'
        'elif sys.argv[1:] == ["models"]: print("gemini-3.8-flash-low")\n'
        f'else:\n    with Path({str(calls)!r}).open("a") as stream: stream.write("call\\n")\n'
        f"    {behavior}\n"
    )
    executable.chmod(0o700)
    workspace = tmp_path / "prompts"
    workspace.mkdir()
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        temp_root=workspace,
        timeout_seconds=0.2,
        outer_grace_seconds=0,
    )
    with pytest.raises(error):
        provider.translate_batch(["garden", "moon"], system_prompt="Translate")
    assert calls.read_text() == "call\n"
    assert list(workspace.iterdir()) == []


def test_missing_model_stops_before_translation(tmp_path: Path) -> None:
    executable = tmp_path / "agy"
    executable.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        'assert sys.argv[1:] in (["--version"], ["models"])\n'
        'print("1.1.27" if sys.argv[1] == "--version" else "gemini-3.1-pro-low")\n'
    )
    executable.chmod(0o700)
    with pytest.raises(ProviderUnavailableError, match="absent"):
        AntigravityProvider(resolve_profile(), executable=str(executable)).translate_batch(
            ["garden"], system_prompt="Translate"
        )
