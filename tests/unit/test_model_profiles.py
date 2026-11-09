"""Public model selection contract for the converged runtime."""

import pytest

from ai.model_profiles import is_metered, resolve_preset, resolve_profile


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


def test_disabled_effort_names_the_enabled_presets() -> None:
    with pytest.raises(ValueError, match=r"pro/medium.*enabled.*pro/low.*pro/high"):
        resolve_profile("pro", effort="medium")


def test_pro_is_an_experiment_preset_on_gemini_4_argon() -> None:
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

    presets = model_profiles._CLI_PRESETS
    with pytest.raises(RuntimeError, match="Duplicate"):
        model_profiles._validate_presets((*presets, presets[0]))
    unnamed = model_profiles._CliPreset(
        "claude-code",  # type: ignore[arg-type]  # a runtime without a prefix entry
        "flash",
        "gpt-x",
        "low",
        "experiment",
        1,
        "",
    )
    with pytest.raises(RuntimeError, match="without a preset-name prefix"):
        model_profiles._validate_presets((*presets, unnamed))
    with pytest.raises(RuntimeError, match="without a preset"):
        model_profiles._validate_seeds(presets, frozenset({("1.5.3", "gemini-3.1-pro-low")}))


def test_presets_are_unique_default_first_and_resolve_to_their_model() -> None:
    from ai.model_profiles import enabled_presets

    presets = enabled_presets()
    assert presets[0].name == "agy-flash-low"
    assert len({preset.name for preset in presets}) == len(presets)
    for preset in presets:
        selected = resolve_preset(preset.name)
        assert (selected.model_id, selected.status, selected.provider) == (
            preset.model_id,
            preset.status,
            preset.provider,
        )
        assert selected.runtime == (preset.runtime if preset.provider == "cli" else None)


def test_a_bare_tier_stays_on_antigravity_and_never_means_astra() -> None:
    assert resolve_profile("flash", effort="low").model_id == "gemini-3.8-flash-low"
    assert resolve_profile("flash", runtime="codex").model_id == "gpt-6-luna-low"
    assert resolve_profile("pro", runtime="codex").model_id == "gpt-6.1-sol-low"
    assert resolve_preset("codex-gpt-6-astra-low").model_id == "gpt-6-astra-low"


def test_every_codex_preset_is_selectable_at_low_thinking_as_an_experiment() -> None:
    from ai.model_profiles import enabled_presets

    codex = {preset.name: preset for preset in enabled_presets() if preset.runtime == "codex"}
    assert set(codex) == {
        "codex-gpt-6-luna-low",
        "codex-gpt-6.1-terra-low",
        "codex-gpt-6.1-sol-low",
        "codex-gpt-6-astra-low",
    }
    assert {(preset.effort, preset.status) for preset in codex.values()} == {("low", "experiment")}


def test_metered_presets_are_manual_and_carry_no_effort() -> None:
    from ai.model_profiles import find_preset

    preset = find_preset("anthropic-pro")
    assert (preset.provider, preset.profile, preset.effort, preset.status) == (
        "anthropic",
        "pro",
        None,
        "manual",
    )
    # The listing must carry the paid-consent rule in the data, not only in the table.
    assert preset.layer is None
    assert "--allow-paid-api" in preset.evidence and "USE_API" in preset.evidence


def test_unknown_preset_names_the_enabled_presets() -> None:
    from ai.model_profiles import find_preset

    with pytest.raises(ValueError, match=r"Unknown preset 'agy-pro-medium'.*agy-flash-low"):
        find_preset("agy-pro-medium")
