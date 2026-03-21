from __future__ import annotations

from ai.evaluation import gate_decision, weighted_quality_score


def test_weighted_quality_score_formula() -> None:
    score = weighted_quality_score(terminology=80, fidelity=70, fluency=60)
    assert round(score, 2) == 71.5


def test_gate_decision_requires_both_thresholds() -> None:
    assert gate_decision(quality_delta=5.0, runtime_ratio=2.0) == "adopt"
    assert gate_decision(quality_delta=4.9, runtime_ratio=1.8) == "defer"
    assert gate_decision(quality_delta=5.2, runtime_ratio=2.1) == "defer"
