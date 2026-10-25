"""Version-pinned model selection; update concrete mappings here when upgrading."""

from dataclasses import dataclass
from typing import Literal

ModelProfile = Literal["flash", "pro"]
Effort = Literal["low", "medium", "high"]
ProviderName = Literal["cli", "api"]
CERTIFIED_AGY_VERSIONS = frozenset({"1.1.27"})

# A release changes these mappings together with its compatibility evidence.
_CLI_MODELS: dict[tuple[ModelProfile, Effort], str] = {
    ("flash", "low"): "gemini-3.8-flash-low",
    ("flash", "medium"): "gemini-3.8-flash-medium",
    ("flash", "high"): "gemini-3.8-flash-high",
    ("pro", "low"): "gemini-3.1-pro-low",
    ("pro", "high"): "gemini-3.1-pro-high",
}
_API_MODELS: dict[ModelProfile, str] = {
    "flash": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
}


@dataclass(frozen=True)
class ResolvedModel:
    profile: ModelProfile
    provider: ProviderName
    model_id: str
    effort: Effort | None


def resolve_profile(
    profile: str = "flash", *, effort: str | None = None, provider: str = "cli"
) -> ResolvedModel:
    """Freeze a valid logical selection without discovery or silent fallback."""
    if profile not in ("flash", "pro"):
        raise ValueError(
            "Model profile must be flash or pro; concrete model names are not accepted"
        )
    if provider not in ("cli", "api"):
        raise ValueError("Provider must be cli or api")
    if provider == "api":
        if effort is not None:
            raise ValueError("Explicit effort is not supported for the paid API provider")
        return ResolvedModel(profile, provider, _API_MODELS[profile], None)
    effective = effort if effort is not None else "low"
    if effective not in ("low", "medium", "high"):
        raise ValueError("effort must be low, medium, or high")
    model_id = _CLI_MODELS.get((profile, effective))
    if model_id is None:
        raise ValueError(f"Unsupported model/effort combination: {profile}/{effective}")
    return ResolvedModel(profile, provider, model_id, effective)
