"""@brief Deterministic Reliability Baseline regression guards: directional comparisons + Release Guard.

Release Guard after V2 semantics correction:
- nominal_first_pass_success_rate >= target_first_pass_rate
- escaped_false_completion_rate == 0: no escaped false completion
- expected_outcome_accuracy meets deterministic scenario expectations
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from evals.runner import run_eval  # noqa: E402

BASELINE_PATH = ROOT / "tests" / "evals" / "baseline.json"


def _load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_baseline_file_present():
    baseline = _load_baseline()
    assert baseline["schema_version"] == "2.0"
    assert baseline["baseline_version"] == "3"
    assert baseline["workflow_count"] == 10
    assert baseline["scenario_count"] == 37
    assert "nominal_metrics" in baseline
    assert "robustness_metrics" in baseline
    assert "safety_metrics" in baseline


def test_nominal_first_pass_meets_target():
    current = run_eval()
    nominal_first_pass = current.metrics["nominal"]["first_pass_success_rate"]
    target = current.target_first_pass_rate
    assert nominal_first_pass >= target


def test_escaped_false_completion_is_zero():
    current = run_eval()
    assert current.metrics["safety"]["escaped_false_completion_rate"] == 0.0


def test_robustness_expected_outcome_accuracy_not_regressed():
    baseline = _load_baseline()
    current = run_eval()
    current_acc = current.metrics["robustness"]["expected_outcome_accuracy"]
    baseline_acc = baseline["robustness_metrics"]["expected_outcome_accuracy"]
    assert current_acc >= baseline_acc


def test_safety_metrics_not_regressed():
    baseline = _load_baseline()
    current = run_eval()
    # Negative metric: escaped false completion must stay zero and never increase.
    assert current.metrics["safety"]["escaped_false_completion_rate"] <= baseline["safety_metrics"]["escaped_false_completion_rate"]
    # Positive metric: false-completion detection must remain 100% and never decrease.
    assert current.metrics["safety"]["false_completion_detection_rate"] >= baseline["safety_metrics"]["false_completion_detection_rate"]
