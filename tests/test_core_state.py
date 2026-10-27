"""Execution Core state-model unit tests. Import top-level core.* with scripts/ on sys.path to avoid scripts/__init__.py COM dependency loading; these tests require neither pywin32 nor SolidWorks."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core.state import (  # noqa: E402
    SCHEMA_VERSION,
    ExecutionResult,
    InvalidStateTransition,
    RecoveryDecision,
    RunContext,
    RunStatus,
    StepRecord,
    StepStatus,
    VerificationResult,
    VerificationStatus,
    can_transition_run,
    can_transition_step,
)


def test_runcontext_json_roundtrip():
    run = RunContext(run_id="run-1", goal="create plate")
    run.status = RunStatus.RUNNING
    run.steps.append(
        StepRecord(
            step_id="s1",
            tool_name="sketch_and_extrude",
            capability_id="part_and_features",
            status=StepStatus.SUCCESS,
        )
    )
    payload = run.to_dict()
    restored = RunContext.from_dict(payload)
    assert restored.run_id == "run-1"
    assert restored.goal == "create plate"
    assert restored.status == RunStatus.RUNNING
    assert restored.steps[0].step_id == "s1"
    assert restored.steps[0].status == StepStatus.SUCCESS
    assert restored.steps[0].capability_id == "part_and_features"
    # JSON string round-trip preserves equivalence.
    assert RunContext.from_json(run.to_json()).to_dict() == run.to_dict()


def test_steprecord_json_roundtrip_with_verification():
    step = StepRecord(
        step_id="s2",
        tool_name="export_step",
        backend="solidworks-com-pywin32",
        verification=VerificationResult(
            status=VerificationStatus.PASS,
            checks=[{"id": "file-exists", "status": "pass"}],
        ),
    )
    restored = StepRecord.from_json(step.to_json())
    assert restored.step_id == "s2"
    assert restored.backend == "solidworks-com-pywin32"
    assert restored.verification.status == VerificationStatus.PASS
    assert restored.verification.checks[0]["id"] == "file-exists"


def test_schema_version_present():
    assert RunContext(run_id="r").schema_version == SCHEMA_VERSION
    assert "schema_version" in RunContext(run_id="r").to_dict()
    assert "schema_version" in StepRecord(step_id="s").to_dict()


def test_trace_id_defaults_to_run_id():
    assert RunContext(run_id="r1").trace_id == "r1"
    assert RunContext(run_id="r2", trace_id="t2").trace_id == "t2"


def test_legal_run_transitions():
    assert can_transition_run(RunStatus.CREATED, RunStatus.RUNNING)
    assert can_transition_run(RunStatus.RUNNING, RunStatus.VERIFYING)
    assert can_transition_run(RunStatus.VERIFYING, RunStatus.COMPLETED)
    assert can_transition_run(RunStatus.RUNNING, RunStatus.RETRYING)
    assert can_transition_run(RunStatus.RETRYING, RunStatus.RUNNING)

    run = RunContext(run_id="r")
    run.transition(RunStatus.RUNNING)
    assert run.status == RunStatus.RUNNING
    run.transition(RunStatus.VERIFYING)
    assert run.status == RunStatus.VERIFYING


def test_illegal_run_transitions():
    illegal = [
        (RunStatus.FAILED, RunStatus.COMPLETED),
        (RunStatus.BLOCKED, RunStatus.COMPLETED),
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.RUNNING),  # Transition through RETRYING first.
    ]
    for current, target in illegal:
        assert not can_transition_run(current, target), f"{current.value} -> {target.value}"
        with pytest.raises(InvalidStateTransition):
            RunContext(run_id="r", status=current).transition(target)


def test_step_transitions():
    assert can_transition_step(StepStatus.PENDING, StepStatus.RUNNING)
    assert can_transition_step(StepStatus.RUNNING, StepStatus.SUCCESS)
    assert can_transition_step(StepStatus.RUNNING, StepStatus.VERIFYING)
    assert can_transition_step(StepStatus.VERIFYING, StepStatus.SUCCESS)
    assert not can_transition_step(StepStatus.FAILED, StepStatus.SUCCESS)
    assert not can_transition_step(StepStatus.SUCCESS, StepStatus.RUNNING)

    step = StepRecord(step_id="s")
    step.transition(StepStatus.RUNNING)
    assert step.status == StepStatus.RUNNING
    step.transition(StepStatus.SUCCESS)
    assert step.status == StepStatus.SUCCESS


def test_verification_result_roundtrip():
    result = VerificationResult(
        status=VerificationStatus.FAIL,
        reason="artifact missing",
        error_code="E_MISSING",
    )
    restored = VerificationResult.from_json(result.to_json())
    assert restored.status == VerificationStatus.FAIL
    assert restored.reason == "artifact missing"
    assert restored.error_code == "E_MISSING"


def test_execution_result_roundtrip():
    result = ExecutionResult(success=True, outputs=["a.step"], error_code=None)
    restored = ExecutionResult.from_json(result.to_json())
    assert restored.success is True
    assert restored.outputs == ["a.step"]
    assert restored.error_code is None


def test_recovery_decision_roundtrip_and_validation():
    decision = RecoveryDecision(decision="retry", retry_count=1, max_retries=3)
    restored = RecoveryDecision.from_json(decision.to_json())
    assert restored.decision == "retry"
    assert restored.max_retries == 3
    with pytest.raises(ValueError):
        RecoveryDecision(decision="not_a_decision")


def test_runcontext_requires_run_id():
    with pytest.raises(ValueError):
        RunContext(run_id="")


def test_steprecord_requires_step_id():
    with pytest.raises(ValueError):
        StepRecord(step_id="")
