"""Antigravity adapter behavior at the executable boundary."""

import json
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
        'print("1.1.27" if sys.argv[1] == "--version" else "gemini-4-argon-low")\n'
    )
    executable.chmod(0o700)
    with pytest.raises(ProviderUnavailableError, match="absent"):
        AntigravityProvider(resolve_profile(), executable=str(executable)).translate_batch(
            ["garden"], system_prompt="Translate"
        )


def _fake_agy(
    tmp_path: Path, *, version: str, reply: str, roster: str = "gemini-3.8-flash-low"
) -> tuple[Path, Path]:
    """Fake runtime that logs each argv and answers segment-tag or %% delimiter prompts.

    reply="translate" returns one Chinese segment per source segment;
    reply="echo" returns the source text unchanged;
    reply="short" returns one segment fewer than requested.
    """
    executable = tmp_path / "agy"
    log = tmp_path / "argv.log"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, re, sys\n"
        f"pathlib.Path({str(log)!r}).open('a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        'if sys.argv[1:] == ["--version"]:\n'
        f"    print({version!r})\n"
        'elif sys.argv[1:] == ["models"]:\n'
        f"    print({roster!r})\n"
        "else:\n"
        '    prompt = pathlib.Path("prompt.txt").read_text()\n'
        f"    echo = {reply == 'echo'!r}\n"
        "    if 'separated by %%' in prompt:\n"
        "        parts = prompt.split('as the input.\\n\\n', 1)[1].split('\\n\\n%%\\n\\n')\n"
        "        out = [p if echo else f'译文{i}' for i, p in enumerate(parts, 1)]\n"
        "        print('\\n\\n%%\\n\\n'.join(out)); raise SystemExit\n"
        "    # Skip the '...' examples in the framing instructions.\n"
        "    pairs = re.findall(r'<segment id=\"(\\d+)\">(?!\\.\\.\\.<)(.*?)</segment>', prompt, re.S)\n"
        f"    if {reply == 'short'!r}:\n"
        "        pairs = pairs[:-1]\n"
        "    if not pairs:\n"
        "        print('译文1'); raise SystemExit\n"
        "    print('\\n'.join(f'<segment id=\"{i}\">{s if echo else \"译文\" + i}</segment>' for i, s in pairs))\n"
    )
    executable.chmod(0o700)
    return executable, log


def _model_calls(log: Path) -> list[list[str]]:
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    return [argv for argv in calls if "--print" in argv]


def test_effort_is_passed_once_with_the_model_family(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="1.5.3", reply="translate")
    provider = AntigravityProvider(resolve_profile(), executable=str(executable))
    assert provider.translate_batch(["garden"], system_prompt="Translate") == ["译文1"]
    [argv] = _model_calls(log)
    assert argv[argv.index("--model") + 1] == "gemini-3.8-flash"
    assert argv.count("--effort") == 1
    assert argv[argv.index("--effort") + 1] == "low"


def test_unknown_version_is_probed_once_then_certified(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="translate")
    cache = tmp_path / "state" / "certifications.json"
    provider = AntigravityProvider(
        resolve_profile(), executable=str(executable), certification_path=cache
    )
    assert provider.translate_batch(["garden"], system_prompt="Translate") == ["译文1"]
    assert len(_model_calls(log)) == 2  # synthetic probe, then the book batch
    assert provider.runtime_version == "9.9.9"
    assert "9.9.9" in cache.read_text() and "gemini-3.8-flash-low" in cache.read_text()

    second = AntigravityProvider(
        resolve_profile(), executable=str(executable), certification_path=cache
    )
    second.translate_batch(["moon"], system_prompt="Translate")
    assert len(_model_calls(log)) == 3  # cached certification: no second probe


def test_failed_probe_stops_before_any_book_batch(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="echo")
    cache = tmp_path / "certifications.json"
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        certification_path=cache,
        protocol="delimiter",  # the fixed Chinese probe prompt rejects untranslated output
    )
    with pytest.raises(ProviderUnavailableError, match="compatibility probe"):
        provider.translate_batch(["garden"], system_prompt="Translate")
    assert len(_model_calls(log)) == 1  # the probe only; the book batch never ran
    assert not cache.exists()


def test_delimiter_protocol_probe_is_certified_separately(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="translate")
    cache = tmp_path / "certifications.json"
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        certification_path=cache,
        protocol="delimiter",
    )
    assert provider.translate_batch(["garden", "moon"], system_prompt="Extract") == [
        "译文1",
        "译文2",
    ]
    assert len(_model_calls(log)) == 2
    assert '"protocol": "delimiter"' in cache.read_text()


def test_argv_never_carries_the_suffixed_model_id(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="1.5.3", reply="translate")
    AntigravityProvider(resolve_profile(), executable=str(executable)).translate_batch(
        ["garden"], system_prompt="Translate"
    )
    [argv] = _model_calls(log)
    assert "gemini-3.8-flash-low" not in argv


def test_seeded_version_still_probes_an_unseeded_model(tmp_path: Path) -> None:
    executable, log = _fake_agy(
        tmp_path, version="1.5.3", reply="translate", roster="gemini-4-argon-high"
    )
    cache = tmp_path / "certifications.json"
    provider = AntigravityProvider(
        resolve_profile("pro", effort="high"),
        executable=str(executable),
        certification_path=cache,
    )
    provider.translate_batch(["garden"], system_prompt="Translate")
    assert len(_model_calls(log)) == 2  # probe for the unseeded pair, then the book batch
    assert "gemini-4-argon-high" in cache.read_text()


def test_each_protocol_needs_its_own_pass(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="translate")
    cache = tmp_path / "certifications.json"
    for protocol in ("segment_tags", "delimiter"):
        AntigravityProvider(
            resolve_profile(),
            executable=str(executable),
            certification_path=cache,
            protocol=protocol,
        ).translate_batch(["garden", "moon"], system_prompt="Translate")
    assert len(_model_calls(log)) == 4  # a segment_tags pass does not certify delimiter


def test_probe_parse_error_halts_instead_of_splitting(tmp_path: Path) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="short")
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        certification_path=tmp_path / "certifications.json",
    )
    with pytest.raises(ProviderUnavailableError, match="compatibility probe") as caught:
        provider.translate_batch(["garden"], system_prompt="Translate")
    assert caught.value.split_eligible is False
    assert len(_model_calls(log)) == 1


@pytest.mark.parametrize("content", [b"not json", b'{"a": 1}', b'["comment"]', b'["\xff\xfe"]'])
def test_invalid_certification_record_stops_loudly(tmp_path: Path, content: bytes) -> None:
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="translate")
    cache = tmp_path / "certifications.json"
    cache.write_bytes(content)
    provider = AntigravityProvider(
        resolve_profile(), executable=str(executable), certification_path=cache
    )
    with pytest.raises(ProviderUnavailableError, match="fix or remove it"):
        provider.translate_batch(["garden"], system_prompt="Translate")
    assert _model_calls(log) == []
    assert cache.read_bytes() == content


def test_unwritable_certification_path_is_a_provider_error(tmp_path: Path) -> None:
    executable, _ = _fake_agy(tmp_path, version="9.9.9", reply="translate")
    blocker = tmp_path / "state"
    blocker.write_text("a file where the cache directory should be")
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        certification_path=blocker / "certifications.json",
    )
    with pytest.raises(ProviderUnavailableError, match="Unwritable"):
        provider.translate_batch(["garden"], system_prompt="Translate")


def test_translation_probe_accepts_output_that_keeps_the_source_language(tmp_path: Path) -> None:
    # An English target may legitimately return the English samples unchanged.
    executable, log = _fake_agy(tmp_path, version="9.9.9", reply="echo")
    provider = AntigravityProvider(
        resolve_profile(),
        executable=str(executable),
        certification_path=tmp_path / "certifications.json",
    )
    outputs = provider.translate_batch(["garden", "moon"], system_prompt="Translate into English")
    assert outputs == ["garden", "moon"]
    assert len(_model_calls(log)) == 2
