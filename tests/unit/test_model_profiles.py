"""Public model selection contract for the converged runtime."""

import pytest

from ai.model_profiles import is_metered, resolve_profile


def test_default_flash_is_pinned_to_low() -> None:
    selected = resolve_profile("flash")
    assert selected.model_id == "gemini-3.8-flash-low"
    assert selected.family == "gemini-3.8-flash"
    assert selected.effort == "low"
    assert selected.profile == "flash"
    assert selected.status == "default"


@pytest.mark.parametrize("profile,effort", [("lite", None), ("pro", "medium"), ("flash", "max")])
def test_invalid_selection_fails_loudly(profile: str, effort: str | None) -> None:
    with pytest.raises(ValueError):
        resolve_profile(profile, effort=effort)


def test_disabled_effort_names_the_enabled_rows() -> None:
    with pytest.raises(ValueError, match=r"pro/medium.*enabled.*pro/low.*pro/high"):
        resolve_profile("pro", effort="medium")


def test_pro_is_an_experiment_row_on_gemini_4_argon() -> None:
    selected = resolve_profile("pro", effort="high")
    assert (selected.family, selected.model_id, selected.status) == (
        "gemini-4-argon",
        "gemini-4-argon-high",
        "experiment",
    )


def test_paid_api_does_not_silently_accept_effort() -> None:
    with pytest.raises(ValueError, match="effort"):
        resolve_profile("flash", effort="low", provider="gemini")
    selected = resolve_profile("flash", provider="gemini")
    assert selected.model_id == "gemini-2.5-flash"
    assert selected.effort is None
    assert selected.family is None
    assert selected.status == "manual"


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


def test_registry_validation_rejects_duplicates_and_dead_seeds() -> None:
    from ai import model_profiles

    rows = model_profiles._CLI_ROWS
    with pytest.raises(RuntimeError, match="Duplicate"):
        model_profiles._validate_rows((*rows, rows[0]))
    with pytest.raises(RuntimeError, match="without a row"):
        model_profiles._validate_seeds(rows, frozenset({("1.5.3", "gemini-3.1-pro-low")}))


def test_rows_are_unique_default_first_and_resolve_to_their_model() -> None:
    from ai.model_profiles import enabled_rows

    rows = enabled_rows()
    assert rows[0].name == "agy-flash-low"
    assert len({row.name for row in rows}) == len(rows)
    for row in rows:
        selected = resolve_profile(row.profile, effort=row.effort, provider=row.provider)
        assert (selected.model_id, selected.status) == (row.model_id, row.status)


def test_metered_rows_are_manual_and_carry_no_effort() -> None:
    from ai.model_profiles import find_row

    row = find_row("anthropic-pro")
    assert (row.provider, row.profile, row.effort, row.status) == (
        "anthropic",
        "pro",
        None,
        "manual",
    )


def test_unknown_row_names_the_enabled_rows() -> None:
    from ai.model_profiles import find_row

    with pytest.raises(ValueError, match=r"Unknown row 'agy-pro-medium'.*agy-flash-low"):
        find_row("agy-pro-medium")
