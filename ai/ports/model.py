"""Port types for a resolved model selection.

`ai/model_profiles.py` decides which selections exist and builds these values; adapters only
consume them, so the types live here and adapters depend on nothing but the ports.
"""

from dataclasses import dataclass
from typing import Literal

ModelProfile = Literal["flash", "pro"]
Effort = Literal["low", "medium", "high"]
MeteredProvider = Literal["gemini", "openai", "anthropic"]
ProviderName = Literal["cli", MeteredProvider]
# Owner policy for a preset (SPEC-025 §3.8): default, manual (paid), or experiment (not qualified).
PresetStatus = Literal["default", "manual", "experiment"]
CliRuntime = Literal["antigravity", "codex", "claude-code"]


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
