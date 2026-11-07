"""Public model selection contract for the converged runtime."""

import pytest

from ai.model_profiles import is_metered, resolve_profile


def test_default_flash_is_pinned_to_low() -> None:
    selected = resolve_profile("flash")
    assert selected.model_id == "gemini-3.8-flash-low"
    assert selected.effort == "low"
    assert selected.profile == "flash"


@pytest.mark.parametrize("profile,effort", [("lite", None), ("pro", "medium"), ("flash", "max")])
def test_invalid_selection_fails_loudly(profile: str, effort: str | None) -> None:
    with pytest.raises(ValueError):
        resolve_profile(profile, effort=effort)


def test_pro_high_uses_a_distinct_concrete_model() -> None:
    assert resolve_profile("pro", effort="high").model_id == "gemini-3.1-pro-high"


def test_paid_api_does_not_silently_accept_effort() -> None:
    with pytest.raises(ValueError, match="effort"):
        resolve_profile("flash", effort="low", provider="gemini")
    selected = resolve_profile("flash", provider="gemini")
    assert selected.model_id == "gemini-2.5-flash"
    assert selected.effort is None


@pytest.mark.parametrize(
    "profile,model_id", [("flash", "claude-sonnet-5-5"), ("pro", "claude-opus-5-5")]
)
def test_anthropic_profiles_pin_model_cap_and_effort(profile: str, model_id: str) -> None:
    selected = resolve_profile(profile, provider="anthropic")
    assert (selected.model_id, selected.output_cap, selected.api_effort) == (
        model_id,
        128_000,
        "low",
    )
    assert selected.effort is None


def test_unpinned_openai_fails_before_any_request() -> None:
    with pytest.raises(ValueError, match="No pinned openai model for profile flash"):
        resolve_profile("flash", provider="openai")


def test_renamed_api_provider_fails_loudly() -> None:
    with pytest.raises(ValueError, match="renamed; use gemini"):
        resolve_profile(provider="api")


def test_metered_predicate_excludes_subscription_runtime() -> None:
    assert [is_metered(name) for name in ("cli", "gemini", "openai", "anthropic")] == [
        False,
        True,
        True,
        True,
    ]
