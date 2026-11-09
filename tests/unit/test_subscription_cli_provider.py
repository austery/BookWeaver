"""The shared subscription CLI adapter, driven through a runtime that is not Antigravity."""

from pathlib import Path

import pytest

from ai.antigravity_provider import AntigravityProvider
from ai.model_profiles import ResolvedModel, resolve_profile
from ai.ports.provider import ProviderTimeoutError, ProviderUnavailableError
from ai.subscription_cli_provider import CliCall, ProcessResult, SubscriptionCliProvider


class _OtherSpec:
    """A runtime with a different roster format and no seeded versions."""

    runtime = "other-cli"
    label = "Other CLI"
    roster_name = "other list"
    temp_prefix = "bookweaver-other-"
    version_args = ("version",)
    roster_args = ("list",)
    login_args = None

    def child_environment(self) -> dict[str, str] | None:
        return None

    def check_login(self, result: ProcessResult) -> None:
        raise AssertionError("no login guard")

    def interpret(self, result: ProcessResult, call: CliCall) -> str:
        return result.stdout.strip()

    def parse_roster(self, text: str) -> set[str]:
        return set(text.split(","))

    def is_seeded(self, version: str, model_id: str) -> bool:
        return False

    def invocation(self, model: ResolvedModel, prompt_path: Path, timeout: float) -> CliCall:
        return CliCall(["run", prompt_path.name])


def _fake_executable(path: Path, *, calls: Path, batch: str) -> str:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\nfrom pathlib import Path\n"
        'if sys.argv[1:] in (["version"], ["--version"]): print("2.0")\n'
        'elif sys.argv[1:] == ["list"]: print("gemini-3.8-flash-low,other-model")\n'
        'elif sys.argv[1:] == ["models"]: print("gemini-3.8-flash-low")\n'
        "else:\n"
        f'    with Path({str(calls)!r}).open("a") as stream: stream.write("batch\\n")\n'
        f"    {batch}\n"
    )
    path.chmod(0o700)
    return str(path)


def _reply(count: int) -> str:
    """Fake batch code: three segments for the synthetic probe, else `count`."""
    return (
        f'count = 3 if "flowerpot" in Path("prompt.txt").read_text() else {count}\n'
        '    print("\\n".join(f"<segment id=\\"{i}\\">译文</segment>" for i in range(1, count + 1)))'
    )


def test_a_new_runtime_only_needs_a_spec(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    workspace = tmp_path / "prompts"
    workspace.mkdir()
    provider = SubscriptionCliProvider(
        _OtherSpec(),
        resolve_profile(),
        executable=_fake_executable(tmp_path / "other", calls=calls, batch=_reply(2)),
        temp_root=workspace,
        certification_path=tmp_path / "certifications.json",
    )

    assert provider.translate_batch(["garden", "moon"], system_prompt="Translate") == [
        "译文",
        "译文",
    ]
    assert provider.backend == "other-cli"
    assert provider.runtime_version == "2.0"
    assert list(workspace.iterdir()) == []


def test_errors_name_the_runtime_and_its_roster(tmp_path: Path) -> None:
    executable = tmp_path / "other"
    executable.write_text(
        '#!/usr/bin/env python3\nimport sys\nprint("2.0" if sys.argv[1:] == ["version"] else "x")\n'
    )
    executable.chmod(0o700)
    provider = SubscriptionCliProvider(
        _OtherSpec(),
        resolve_profile(),
        executable=str(executable),
        certification_path=tmp_path / "certifications.json",
    )

    with pytest.raises(ProviderUnavailableError, match="absent from other list"):
        provider.translate_batch(["garden"], system_prompt="Translate")


def test_outer_deadline_names_the_runtime(tmp_path: Path) -> None:
    calls = tmp_path / "calls"
    provider = SubscriptionCliProvider(
        _OtherSpec(),
        resolve_profile(),
        executable=_fake_executable(
            tmp_path / "other", calls=calls, batch="import time; time.sleep(30)"
        ),
        timeout_seconds=0.2,
        outer_grace_seconds=0,
        certification_path=tmp_path / "certifications.json",
    )

    with pytest.raises(ProviderTimeoutError, match="Other CLI exceeded its outer deadline"):
        provider.translate_batch(["garden"], system_prompt="Translate")


def test_a_pass_on_one_runtime_does_not_certify_the_same_model_on_another(tmp_path: Path) -> None:
    """The same model through a second runtime draws on another pool, so it is probed again."""
    certifications = tmp_path / "certifications.json"
    other_calls = tmp_path / "other-calls"
    agy_calls = tmp_path / "agy-calls"
    model = resolve_profile()

    SubscriptionCliProvider(
        _OtherSpec(),
        model,
        executable=_fake_executable(tmp_path / "other", calls=other_calls, batch=_reply(1)),
        certification_path=certifications,
    ).translate_batch(["garden"], system_prompt="Translate")
    assert other_calls.read_text().count("batch") == 2  # probe, then the batch

    AntigravityProvider(
        model,
        executable=_fake_executable(tmp_path / "agy", calls=agy_calls, batch=_reply(1)),
        certification_path=certifications,
    ).translate_batch(["garden"], system_prompt="Translate")
    assert agy_calls.read_text().count("batch") == 2
