"""Authorization rejects before constructing a metered client."""

import sys
import json
from pathlib import Path

import pytest

from ai.model_profiles import resolve_profile
from ai.runtime_config import validate_config
from ai.runtime_factory import DefaultProviderFactory, PaidAuthorizationError


def test_config_cannot_authorize_paid_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(PaidAuthorizationError, match="non-interactive"):
        DefaultProviderFactory().create(
            resolve_profile(provider="gemini"),
            protocol="segment_tags",
            config={"allow_paid_api": True},
            allow_paid_api=False,
            remaining_chars=100,
        )


def test_paid_flag_is_invalid_for_subscription_provider() -> None:
    with pytest.raises(PaidAuthorizationError, match="requires a metered --provider"):
        DefaultProviderFactory().create(
            resolve_profile(),
            protocol="segment_tags",
            config={},
            allow_paid_api=True,
            remaining_chars=100,
        )


class _FailingClient:
    """Stands in for an any-llm provider client; records what BookWeaver asks for."""

    def __init__(self, calls: list[dict[str, object]], created: dict[str, object]) -> None:
        self.calls = calls
        self.created = created

    def completion(self, **options: object) -> None:
        self.calls.append(options)
        raise RuntimeError("network unavailable")


def _install_failing_client(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]]
) -> dict[str, object]:
    from any_llm import AnyLLM

    created: dict[str, object] = {}

    def create(provider: str, **kwargs: object) -> _FailingClient:
        created.update(kwargs, provider=provider)
        return _FailingClient(calls, created)

    monkeypatch.setattr(AnyLLM, "create", staticmethod(create))
    return created


def test_authorized_api_failure_is_one_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ai.ports.provider import ProviderUnavailableError

    calls: list[dict[str, object]] = []
    created = _install_failing_client(monkeypatch, calls)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-secret")
    factory = DefaultProviderFactory(audit_directory=tmp_path)
    provider = factory.create(
        resolve_profile(provider="gemini"),
        protocol="segment_tags",
        config={},
        allow_paid_api=True,
        remaining_chars=100,
    )
    with pytest.raises(ProviderUnavailableError):
        provider.translate_batch(["one", "two"], system_prompt="Translate")
    assert created == {
        "provider": "gemini",
        "api_key": "test-only-not-a-secret",
        "api_base": None,
        "unified_exceptions": True,
        "max_retries": 0,
    }
    assert [call["model"] for call in calls] == ["gemini-2.5-flash"]
    sent = calls[0]
    assert sent["stream"] is True
    assert sent["max_tokens"] == 65_536
    assert sent["timeout"] == 600.0
    assert "output_config" not in sent
    assert factory.usage_snapshot()[1] == {
        "request_count": 1,
        "input_tokens": None,
        "output_tokens": None,
    }
    audit = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert audit["requests"] == [
        {
            "model": "gemini-2.5-flash",
            "protocol": "segment_tags",
            "provider": "gemini",
            "state": "failed",
            "input_tokens": None,
            "output_tokens": None,
        }
    ]


@pytest.mark.parametrize("provider", ["cli", "gemini", "anthropic"])
def test_audit_distinguishes_unavailable_usage_from_zero_paid_work(
    tmp_path: Path, provider: str
) -> None:
    factory = DefaultProviderFactory(audit_directory=tmp_path)
    factory.persist_audit({"provider": provider, "runtime_version": None})
    audit = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert audit["usage_scope"] == "metered_api_requests"
    assert audit["runtime"]["runtime_version"] is None
    if provider == "cli":
        assert audit["summary"] is None
        assert factory.usage_snapshot() is None
    else:
        assert audit["summary"] == {"request_count": 0, "input_tokens": 0, "output_tokens": 0}


def test_paid_failure_survives_usage_audit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai.ports.provider import ProviderUnavailableError

    class Factory(DefaultProviderFactory):
        writes = 0

        def persist_audit(self, runtime: dict[str, object] | None = None) -> None:
            self.writes += 1
            if self.writes > 1:
                raise OSError("synthetic audit disk failure")

    _install_failing_client(monkeypatch, [])
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-secret")
    provider = Factory().create(
        resolve_profile(provider="gemini"),
        protocol="segment_tags",
        config={},
        allow_paid_api=True,
        remaining_chars=100,
    )
    with pytest.raises(ProviderUnavailableError) as caught:
        provider.translate_batch(["Source"], system_prompt="Translate")
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert "Usage audit also failed: OSError" in caught.value.__cause__.__notes__


def test_missing_vendor_key_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
        DefaultProviderFactory().create(
            resolve_profile(provider="anthropic"),
            protocol="segment_tags",
            config={"gemini_api": {"api_key": "gemini-only"}},
            allow_paid_api=True,
            remaining_chars=100,
        )


def test_interactive_consent_names_vendor_and_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(PaidAuthorizationError, match="not authorized"):
        DefaultProviderFactory().create(
            resolve_profile("pro", provider="anthropic"),
            protocol="segment_tags",
            config={},
            allow_paid_api=False,
            remaining_chars=1234,
        )
    assert "Metered Anthropic API: claude-opus-5-5" in capsys.readouterr().out


def test_configured_api_timeout_reaches_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    created = _install_failing_client(monkeypatch, calls)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-secret")
    provider = DefaultProviderFactory().create(
        resolve_profile(provider="anthropic"),
        protocol="segment_tags",
        config=validate_config({"api": {"timeout_seconds": 1800}}),
        allow_paid_api=True,
        remaining_chars=100,
    )
    with pytest.raises(Exception):
        provider.translate_batch(["Source"], system_prompt="Translate")
    assert calls[0]["timeout"] == 1800.0
    assert calls[0]["output_config"] == {"effort": "low"}
    assert (created["provider"], calls[0]["model"]) == ("anthropic", "claude-sonnet-5-5")


@pytest.mark.parametrize("value", [0, -5, 86401, "600", True])
def test_invalid_api_timeout_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        validate_config({"api": {"timeout_seconds": value}})


@pytest.mark.parametrize("configured,expected", [(None, 600.0), (1800, 1800.0), (90.5, 90.5)])
def test_antigravity_timeout_reaches_executable_boundary(
    monkeypatch: pytest.MonkeyPatch, configured: float | None, expected: float
) -> None:
    from ai import subscription_cli_provider
    from ai.subscription_cli_provider import ProcessResult

    calls: list[tuple[list[str], float]] = []

    def execute(args: list[str], *, cwd: object, timeout: float, **_: object) -> ProcessResult:
        calls.append((args, timeout))
        if args[1:] == ["--version"]:
            return ProcessResult(0, "1.1.27", "")
        if args[1:] == ["models"]:
            return ProcessResult(0, "gemini-3.8-flash-low\tGemini 3.8 Flash (Low)", "")
        return ProcessResult(
            0, '<segment id="1">花园</segment>\n<segment id="2">月亮</segment>', ""
        )

    monkeypatch.setattr(subscription_cli_provider, "run_owned_process", execute)
    config: dict[str, object] = (
        {} if configured is None else {"antigravity": {"timeout_seconds": configured}}
    )
    provider = DefaultProviderFactory().create(
        resolve_profile(),
        protocol="segment_tags",
        config=validate_config(config),
        allow_paid_api=False,
        remaining_chars=1,
    )

    assert provider.translate_batch(["garden", "moon"], system_prompt="Translate") == [
        "花园",
        "月亮",
    ]
    args, outer_deadline = calls[-1]
    assert args[args.index("--print-timeout") + 1] == f"{expected:g}s"
    assert outer_deadline == expected + 30


@pytest.mark.parametrize("value", [0, -5, 86401, "600", True])
def test_invalid_antigravity_timeout_is_rejected_before_execution(value: object) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        validate_config({"antigravity": {"timeout_seconds": value}})


def test_unknown_antigravity_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="print_timeout"):
        validate_config({"antigravity": {"print_timeout": 600}})


def test_a_codex_preset_reaches_codex_with_its_own_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ai import subscription_cli_provider
    from ai.model_profiles import resolve_preset
    from ai.subscription_cli_provider import ProcessResult

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))  # keeps the login and probe record out
    deadlines: dict[str, float] = {}
    roster = json.dumps(
        {
            "models": [
                {
                    "slug": "gpt-6.1-sol",
                    "visibility": "list",
                    "supported_reasoning_levels": [{"effort": "low"}],
                }
            ]
        }
    )

    def execute(args: list[str], *, cwd: object, timeout: float, **_: object) -> ProcessResult:
        if args[1:] == ["login", "status"]:
            return ProcessResult(0, "", "Logged in using ChatGPT")
        if args[1:] == ["--version"]:
            return ProcessResult(0, "codex-cli 0.167.0", "")
        if args[1:] == ["debug", "models"]:
            return ProcessResult(0, roster, "")
        deadlines["batch"] = timeout
        output = Path(args[args.index("--output-last-message") + 1])
        output.write_text("".join(f'<segment id="{i}">译文</segment>' for i in (1, 2, 3)))
        return ProcessResult(0, "", "")

    monkeypatch.setattr(subscription_cli_provider, "run_owned_process", execute)
    provider = DefaultProviderFactory().create(
        resolve_preset("codex-gpt-6.1-sol-low"),
        protocol="segment_tags",
        config=validate_config({"codex": {"timeout_seconds": 90}}),
        allow_paid_api=False,
        remaining_chars=1,
    )

    assert len(provider.translate_batch(["a", "b", "c"], system_prompt="Translate")) == 3
    assert provider.backend == "codex"
    assert deadlines["batch"] == 90 + 30


def test_a_claude_code_preset_reaches_claude_code_with_its_own_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ai import subscription_cli_provider
    from ai.model_profiles import resolve_preset
    from ai.subscription_cli_provider import ProcessResult

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))  # keeps the probe record out
    deadlines: dict[str, float] = {}
    reply = "".join(f'<segment id="{i}">译文</segment>' for i in (1, 2, 3))

    def execute(args: list[str], *, cwd: object, timeout: float, **_: object) -> ProcessResult:
        if args[1:] == ["auth", "status"]:
            return ProcessResult(0, json.dumps({"loggedIn": True, "authMethod": "claude.ai"}), "")
        if args[1:] == ["--version"]:
            return ProcessResult(0, "2.1.311 (Claude Code)", "")
        deadlines["batch"] = timeout
        return ProcessResult(
            0, json.dumps({"is_error": False, "num_turns": 1, "result": reply}), ""
        )

    monkeypatch.setattr(subscription_cli_provider, "run_owned_process", execute)
    provider = DefaultProviderFactory().create(
        resolve_preset("claude-opus-5-5-low"),
        protocol="segment_tags",
        config=validate_config({"claude_code": {"timeout_seconds": 90}}),
        allow_paid_api=False,
        remaining_chars=1,
    )

    assert len(provider.translate_batch(["a", "b", "c"], system_prompt="Translate")) == 3
    assert provider.backend == "claude-code"
    assert deadlines["batch"] == 90 + 30
