from __future__ import annotations


def weighted_quality_score(*, terminology: float, fidelity: float, fluency: float) -> float:
    return 0.40 * terminology + 0.35 * fidelity + 0.25 * fluency


def gate_decision(*, quality_delta: float, runtime_ratio: float) -> str:
    if quality_delta >= 5.0 and runtime_ratio <= 2.0:
        return "adopt"
    return "defer"
