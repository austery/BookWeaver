"""Version-pinned model selection; update concrete mappings here when upgrading."""

from dataclasses import dataclass
from typing import Literal

ModelProfile = Literal["flash", "pro"]
Effort = Literal["low", "medium", "high"]
ProviderName = Literal["cli", "gemini", "openai", "anthropic"]
CERTIFIED_AGY_VERSIONS = frozenset({"1.1.27", "1.5.3"})
METERED_PROVIDERS = frozenset({"gemini", "openai", "anthropic"})

# A release changes these mappings together with its compatibility evidence.
_CLI_MODELS: dict[tuple[ModelProfile, Effort], str] = {
    ("flash", "low"): "gemini-3.8-flash-low",
    ("flash", "medium"): "gemini-3.8-flash-medium",
    ("flash", "high"): "gemini-3.8-flash-high",
    ("pro", "low"): "gemini-3.1-pro-low",
    ("pro", "high"): "gemini-3.1-pro-high",
}


@dataclass(frozen=True)
class _MeteredEntry:
    model_id: str
    output_cap: int
    api_effort: str | None


# Metered API models (SPEC-024 §6.2). Each row cites its vendor source and read date;
# a provider without a row fails before any request instead of guessing a model.
_API_MODELS: dict[tuple[str, ModelProfile], _MeteredEntry] = {
    # Output cap 65,536 as listed in LiteLLM 1.108.2's model map, inspected 2026-11-07;
    # not yet checked against ai.google.dev, which was unreachable from that environment.
    ("gemini", "flash"): _MeteredEntry("gemini-2.5-flash", 65_536, None),
    ("gemini", "pro"): _MeteredEntry("gemini-2.5-pro", 65_536, None),
    # platform.claude.com models overview, read 2026-11-07: max output 128K tokens.
    ("anthropic", "flash"): _MeteredEntry("claude-sonnet-5-5", 128_000, "low"),
    ("anthropic", "pro"): _MeteredEntry("claude-opus-5-5", 128_000, "low"),
    # OpenAI: unfilled until its model documentation can be cited (SPEC-024 §11 Phase 3).
}


@dataclass(frozen=True)
class ResolvedModel:
    profile: ModelProfile
    provider: ProviderName
    model_id: str
    effort: Effort | None
    # Metered providers only: requested output cap and vendor-pinned effort.
    output_cap: int | None = None
    api_effort: str | None = None


def is_metered(provider: str) -> bool:
    """True for providers that bill per request and require invocation consent."""
    return provider in METERED_PROVIDERS


def resolve_profile(
    profile: str = "flash", *, effort: str | None = None, provider: str = "cli"
) -> ResolvedModel:
    """Freeze a valid logical selection without discovery or silent fallback."""
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
    model_id = _CLI_MODELS.get((profile, effective))
    if model_id is None:
        raise ValueError(f"Unsupported model/effort combination: {profile}/{effective}")
    return ResolvedModel(profile, provider, model_id, effective)
