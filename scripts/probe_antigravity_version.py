"""Compatibility probe for an uncertified Antigravity CLI version (SPEC-021).

Sends three synthetic English passages through the production translation path
(system prompt, segment-tag framing, ``agy`` invocation, response parser) for
each CLI profile, and checks that every result is a non-empty Chinese segment in
order. Only synthetic text is sent; no book content leaves the machine.

The runtime now probes an unknown version automatically before the first book
batch (SPEC-025 §3.3). Use this script to inspect the roster and read the
translations by eye, for example before adding a version to the seed list:

    uv run python scripts/probe_antigravity_version.py

Exit status 0 means every probed profile passed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import antigravity_provider  # noqa: E402
from ai.adapters.providers._delimiter import PROTOCOL_SEGMENT_TAGS  # noqa: E402
from ai.antigravity_provider import (  # noqa: E402
    PROBE_SAMPLES,
    AntigravityProvider,
    probe_problems,
)
from ai.model_profiles import CERTIFIED_AGY_MODELS, resolve_profile  # noqa: E402
from ai.prompt_preparation import build_system_prompt  # noqa: E402

SAMPLES = list(PROBE_SAMPLES)
PROFILES = [("flash", "low"), ("pro", "low")]


def probe(executable: str, version: str, profile: str, effort: str, timeout: float) -> bool:
    model = resolve_profile(profile, effort=effort, provider="cli")
    provider = AntigravityProvider(
        model,
        # Inspect by eye only: treat this pair as seeded, so the provider skips its automatic
        # probe and leaves the certification cache untouched.
        certified_models=frozenset({(version, model.model_id)}),
        executable=executable,
        timeout_seconds=timeout,
        protocol=PROTOCOL_SEGMENT_TAGS,
    )
    system_prompt = build_system_prompt("zh", immersive=True)
    started = time.monotonic()
    try:
        outputs = provider.translate_batch(SAMPLES, system_prompt=system_prompt)
    except Exception as exc:  # report every failure kind, keep probing other profiles
        print(f"FAIL {model.model_id}: {type(exc).__name__}: {exc}")
        return False
    elapsed = time.monotonic() - started
    problems = probe_problems(outputs, expect_chinese=True)
    status = "FAIL" if problems else "PASS"
    print(f"{status} {model.model_id} ({elapsed:.1f}s)")
    for index, (source, text) in enumerate(zip(SAMPLES, outputs, strict=False), 1):
        print(f"  [{index}] {source}\n      -> {text.strip()}")
    for problem in problems:
        print(f"  problem: {problem}")
    return not problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--executable", default="agy")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    version = antigravity_provider._execute([args.executable, "--version"], cwd=None, timeout=30)
    print(f"Antigravity version: {version}")
    seeded = sorted(f"{v} {m}" for v, m in CERTIFIED_AGY_MODELS)
    print(f"Seed certifications: {', '.join(seeded)}")
    roster = antigravity_provider._execute([args.executable, "models"], cwd=None, timeout=30)
    print("agy models:")
    for line in roster.splitlines():
        if line.strip():
            print(f"  {line.strip()}")

    results = [probe(args.executable, version, p, e, args.timeout) for p, e in PROFILES]
    passed = all(results)
    print(f"\nRESULT: {'PASS' if passed else 'FAIL'} for Antigravity {version}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
