"""Public model selection contract for the converged runtime."""

import pytest

from ai.model_profiles import resolve_profile


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
        resolve_profile("flash", effort="low", provider="api")
    selected = resolve_profile("flash", provider="api")
    assert selected.model_id == "gemini-2.5-flash"
    assert selected.effort is None
