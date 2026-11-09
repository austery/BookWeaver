"""Version-pinned model selection; update concrete mappings here when upgrading."""

from dataclasses import dataclass
from typing import Literal, get_args

ModelProfile = Literal["flash", "pro"]
Effort = Literal["low", "medium", "high"]
MeteredProvider = Literal["gemini", "openai", "anthropic"]
ProviderName = Literal["cli", MeteredProvider]
# Owner policy for a preset (SPEC-025 §3.8): default, manual (paid), or experiment (not qualified).
PresetStatus = Literal["default", "manual", "experiment"]
# Highest proven evidence layer (SPEC-025 §3.8): 1 legal, 2 executable, 3 qualified.
EvidenceLayer = Literal[1, 2, 3]
CliRuntime = Literal["antigravity", "codex", "claude-code"]
# Subscription CLIs under model trials. A resume that crosses one of their models stops, and the
# local API gives each of their presets its own folder (SPEC-025 §3.9 and §3.10).
TRIAL_CLI_RUNTIMES: frozenset[str] = frozenset({"codex", "claude-code"})
# Runtime = quota pool: a subscription CLI, or the metered vendor for API presets.
PresetRuntime = Literal[CliRuntime, MeteredProvider]
METERED_PROVIDERS: frozenset[str] = frozenset(get_args(MeteredProvider))


@dataclass(frozen=True)
class _CliPreset:
    """One owner-enabled subscription CLI combination (SPEC-025 §3.8)."""

    runtime: CliRuntime
    profile: ModelProfile
    family: str
    effort: Effort
    status: PresetStatus
    layer: EvidenceLayer
    evidence: str
    # The middle of the preset name; the tier when absent. Needed when a tier offers several models.
    variant: str | None = None
    # The model a bare tier means on this runtime, such as the extraction model's flash or pro.
    # Any other preset in that tier runs only when it is selected by name.
    tier_default: bool = True


# Short runtime names used in preset names; one per CliRuntime.
_RUNTIME_PREFIX: dict[CliRuntime, str] = {
    "antigravity": "agy",
    "codex": "codex",
    "claude-code": "claude",
}
_CODEX_EVIDENCE = "offline fake-server capture only; probed automatically on first use"
_CODEX_LIVE_EVIDENCE = "codex-cli 0.167.0 live probe 2026-11-09 (segment_tags and delimiter)"
_CLAUDE_CODE_EVIDENCE = (
    "Claude Code 2.1.311 offline request capture 2026-11-09; no live call; "
    "probed automatically on first use"
)


# Named presets, not the Cartesian product: anything absent here is rejected before a run.
# The family is the runtime's model family; effort is passed once through ``--effort``.
_CLI_PRESETS: tuple[_CliPreset, ...] = (
    _CliPreset(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "low",
        "default",
        2,
        "agy 1.5.3 probe 2026-11-07; one validated book on agy 1.1.27",
    ),
    _CliPreset(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "medium",
        "experiment",
        1,
        "effort comparison only; probed automatically on first use",
    ),
    _CliPreset(
        "antigravity",
        "flash",
        "gemini-3.8-flash",
        "high",
        "experiment",
        1,
        "effort comparison only; probed automatically on first use",
    ),
    _CliPreset(
        "antigravity",
        "pro",
        "gemini-4-argon",
        "low",
        "experiment",
        2,
        "agy 1.5.3 probe 2026-11-07 (segment_tags and delimiter)",
    ),
    _CliPreset(
        "antigravity",
        "pro",
        "gemini-4-argon",
        "high",
        "experiment",
        1,
        "agy 1.5.3 roster 2026-11-07; probed automatically on first use",
    ),
    # Owner decision 2026-11-09: several models stay selectable until test rounds pick one, all at
    # low effort. Astra costs the most, so no bare tier ever resolves to it.
    _CliPreset(
        "codex", "flash", "gpt-6-luna", "low", "experiment", 2, _CODEX_LIVE_EVIDENCE, "gpt-6-luna"
    ),
    _CliPreset(
        "codex",
        "flash",
        "gpt-6.1-terra",
        "low",
        "experiment",
        1,
        _CODEX_EVIDENCE,
        "gpt-6.1-terra",
        tier_default=False,
    ),
    _CliPreset(
        "codex", "pro", "gpt-6.1-sol", "low", "experiment", 2, _CODEX_LIVE_EVIDENCE, "gpt-6.1-sol"
    ),
    _CliPreset(
        "codex",
        "pro",
        "gpt-6-astra",
        "low",
        "experiment",
        1,
        _CODEX_EVIDENCE,
        "gpt-6-astra",
        tier_default=False,
    ),
    # The same models as the metered Anthropic presets, on the Claude subscription pool. That pool
    # is the owner's coding quota, so both stay experiments at low effort.
    _CliPreset(
        "claude-code",
        "flash",
        "claude-sonnet-5-5",
        "low",
        "experiment",
        1,
        _CLAUDE_CODE_EVIDENCE,
        "sonnet-5-5",
    ),
    _CliPreset(
        "claude-code",
        "pro",
        "claude-opus-5-5",
        "low",
        "experiment",
        1,
        _CLAUDE_CODE_EVIDENCE,
        "opus-5-5",
    ),
)


def cli_model_id(family: str, effort: str) -> str:
    """Concrete ID for provenance: agy 1.5.3 lists ``<family>-<effort>``; for Codex we compose it."""
    return f"{family}-{effort}"


def _preset_name(preset: _CliPreset) -> str:
    return f"{_RUNTIME_PREFIX[preset.runtime]}-{preset.variant or preset.profile}-{preset.effort}"


def _validate_presets(presets: tuple[_CliPreset, ...]) -> None:
    """Layer 1 check at import: unique names, one meaning per bare tier, and a known default."""
    unnamed = sorted({preset.runtime for preset in presets} - set(_RUNTIME_PREFIX))
    if unnamed:
        raise RuntimeError(f"CLI runtimes without a preset-name prefix: {unnamed}")
    names = [_preset_name(preset) for preset in presets]
    keys = [
        (preset.runtime, preset.profile, preset.effort) for preset in presets if preset.tier_default
    ]
    duplicates = sorted({name for name in names if names.count(name) > 1}) + sorted(
        {str(key) for key in keys if keys.count(key) > 1}
    )
    if duplicates:
        raise RuntimeError(f"Duplicate CLI presets in ai/model_profiles.py: {duplicates}")
    if ("antigravity", "flash", "low") not in keys:
        raise RuntimeError("The default antigravity flash/low preset is missing")
    # Glossary extraction asks the run's runtime for a bare tier at the default effort.
    for runtime in {preset.runtime for preset in presets}:
        for profile in ("flash", "pro"):
            if (runtime, profile, "low") not in keys:
                raise RuntimeError(f"No tier default for {runtime} {profile}/low")


# Seed certifications per (agy version, concrete model): pairs with recorded probe evidence.
# Any other pair is probed automatically before its first book batch (SPEC-025 §3.3).
CERTIFIED_AGY_MODELS = frozenset(
    {
        ("1.1.27", "gemini-3.8-flash-low"),
        ("1.5.3", "gemini-3.8-flash-low"),
        ("1.5.3", "gemini-4-argon-low"),
    }
)


def _validate_seeds(presets: tuple[_CliPreset, ...], seeds: frozenset[tuple[str, str]]) -> None:
    """Every seeded model must belong to an enabled preset; a dead seed hides a registry edit."""
    known = {cli_model_id(preset.family, preset.effort) for preset in presets}
    dead = sorted(model for _, model in seeds if model not in known)
    if dead:
        raise RuntimeError(f"CERTIFIED_AGY_MODELS names models without a preset: {dead}")


_validate_presets(_CLI_PRESETS)
_validate_seeds(_CLI_PRESETS, CERTIFIED_AGY_MODELS)


@dataclass(frozen=True)
class _MeteredEntry:
    model_id: str
    output_cap: int
    api_effort: str | None


# Metered API models (SPEC-024 §6.2). Each entry cites its vendor source and read date;
# a provider without an entry fails before any request instead of guessing a model.
_API_MODELS: dict[tuple[MeteredProvider, ModelProfile], _MeteredEntry] = {
    # Output cap 65,536 as listed in LiteLLM 1.108.2's model map, inspected 2026-11-07;
    # not yet checked against ai.google.dev, which was unreachable from that environment.
    ("gemini", "flash"): _MeteredEntry("gemini-2.5-flash", 65_536, None),
    ("gemini", "pro"): _MeteredEntry("gemini-2.5-pro", 65_536, None),
    # platform.claude.com models overview, read 2026-11-07: max output 128K tokens.
    ("anthropic", "flash"): _MeteredEntry("claude-sonnet-5-5", 128_000, "low"),
    ("anthropic", "pro"): _MeteredEntry("claude-opus-5-5", 128_000, "low"),
    # OpenAI: unfilled until its model documentation can be cited (SPEC-024 §11 Phase 3).
}

# Every metered entry becomes a paid preset; a non-metered key would mislabel a free runtime.
if any(provider not in METERED_PROVIDERS for provider, _ in _API_MODELS):
    raise RuntimeError("_API_MODELS may contain only metered providers")


@dataclass(frozen=True)
class Preset:
    """One named, owner-enabled selection shown to users (SPEC-026 §2.2).

    A preset fixes provider, tier, effort and concrete model; ``--preset`` and the local API
    resolve it by name. The separate flags reach only the tier default on Antigravity or a vendor.
    """

    name: str
    runtime: PresetRuntime
    provider: ProviderName
    profile: ModelProfile
    effort: Effort | None
    model_id: str
    status: PresetStatus
    layer: EvidenceLayer | None
    evidence: str


# The preset never implies consent; the paid gate in ai/runtime_factory.py still applies.
_METERED_EVIDENCE = (
    "paid; consent per run: --allow-paid-api, or type USE_API at the interactive prompt; "
    "offline contract tests only"
)


def enabled_presets() -> tuple[Preset, ...]:
    """Every selection a run may use, subscription CLI presets first, the default preset first."""
    cli = sorted(_CLI_PRESETS, key=lambda preset: preset.status != "default")
    presets = [
        Preset(
            _preset_name(preset),
            preset.runtime,
            "cli",
            preset.profile,
            preset.effort,
            cli_model_id(preset.family, preset.effort),
            preset.status,
            preset.layer,
            preset.evidence,
        )
        for preset in cli
    ]
    presets += [
        # Effort is vendor-pinned. No layer: only offline contract tests (SPEC-024), no live probe.
        Preset(
            f"{provider}-{profile}",
            provider,  # runtime: the vendor is the quota pool
            provider,
            profile,
            None,
            entry.model_id,
            "manual",
            None,
            _METERED_EVIDENCE,
        )
        for (provider, profile), entry in _API_MODELS.items()
    ]
    return tuple(presets)


def find_preset(name: str) -> Preset:
    """The enabled preset with this name; unknown names fail with the enabled list."""
    presets = enabled_presets()
    for preset in presets:
        if preset.name == name:
            return preset
    raise ValueError(
        f"Unknown preset {name!r}; enabled presets: {', '.join(r.name for r in presets)}"
    )


@dataclass(frozen=True)
class ResolvedModel:
    profile: ModelProfile
    provider: ProviderName
    model_id: str
    effort: Effort | None
    # Metered providers only: requested output cap and vendor-pinned effort.
    output_cap: int | None = None
    api_effort: str | None = None
    # Subscription CLI only: the family passed to the runtime with ``--effort``.
    family: str | None = None
    status: PresetStatus = "manual"
    # Subscription CLI only: the quota pool this run draws on.
    runtime: CliRuntime | None = None


def is_metered(provider: str) -> bool:
    """True for providers that bill per request and require invocation consent."""
    return provider in METERED_PROVIDERS


def _resolved_cli(preset: _CliPreset, provider: ProviderName) -> ResolvedModel:
    return ResolvedModel(
        preset.profile,
        provider,
        cli_model_id(preset.family, preset.effort),
        preset.effort,
        family=preset.family,
        status=preset.status,
        runtime=preset.runtime,
    )


def resolve_preset(name: str) -> ResolvedModel:
    """Freeze the selection of one named preset; unknown names fail with the enabled list."""
    selected = find_preset(name)
    for preset in _CLI_PRESETS:
        if _preset_name(preset) == name:
            return _resolved_cli(preset, "cli")
    return resolve_profile(selected.profile, provider=selected.provider)


def resolve_profile(
    profile: str = "flash",
    *,
    effort: str | None = None,
    provider: str = "cli",
    runtime: CliRuntime | None = None,
) -> ResolvedModel:
    """Freeze a valid logical selection without discovery or silent fallback.

    A bare tier means Antigravity unless `runtime` says otherwise, so a new runtime's preset
    cannot take over `--model flash --effort low`.
    """
    if profile not in ("flash", "pro"):
        raise ValueError(
            "Model profile must be flash or pro; concrete model names are not accepted"
        )
    if provider == "api":
        raise ValueError("Provider api was renamed; use gemini")
    if provider != "cli" and not is_metered(provider):
        raise ValueError("Provider must be cli, gemini, openai, or anthropic")
    if is_metered(provider):
        if effort is not None:
            raise ValueError("Explicit effort is not supported for metered API providers")
        entry = _API_MODELS.get((provider, profile))
        if entry is None:
            raise ValueError(
                f"No pinned {provider} model for profile {profile}; "
                "update ai/model_profiles.py with cited limits"
            )
        return ResolvedModel(
            profile, provider, entry.model_id, None, entry.output_cap, entry.api_effort
        )
    effective = effort if effort is not None else "low"
    if effective not in ("low", "medium", "high"):
        raise ValueError("effort must be low, medium, or high")
    wanted_runtime = runtime if runtime is not None else "antigravity"
    candidates = [
        preset
        for preset in _CLI_PRESETS
        if preset.runtime == wanted_runtime and preset.tier_default
    ]
    for preset in candidates:
        if (preset.profile, preset.effort) == (profile, effective):
            return _resolved_cli(preset, "cli")
    enabled = ", ".join(f"{preset.profile}/{preset.effort}" for preset in candidates)
    raise ValueError(
        f"Unsupported model/effort combination: {profile}/{effective}; enabled presets: {enabled}"
    )
