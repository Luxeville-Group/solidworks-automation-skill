"""@brief Internal Execution Core orchestration glue, not another Worker, Queue or Agent.

Connect Phase 2-4 State, Verification, Recovery and Trace:
RunContext + StepRecord -> existing Handler -> minimally normalized ExecutionResult
(with raw result retained) -> Verification Adapter when requires_review -> Recovery
Decision on failure/blocked -> Trace.

Worker and existing modules retain queue claim, lease, heartbeat, approval, policy,
stale recovery, Artifact Ledger, Reviewer and Backend Router implementation, actual
retry/backend switching, replanning and networking.

Preserve compatibility: capture Handler exceptions in ExecutionAssessment.exception
for the caller to re-raise unchanged, retaining the Worker's three except branches.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .recovery import ErrorKind, classify_error, decide
from .state import (
    ExecutionResult,
    RecoveryDecision,
    RunContext,
    RunStatus,
    StepRecord,
    StepStatus,
    VerificationResult,
    VerificationStatus,
)
from .trace import emit
from .verification import verify
from .capability import requires_review as registry_requires_review


def normalize_tool_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """@brief Validate explicit execution facts while preserving legacy fields and failures.
    @param raw Structured result from an existing tool or Handler.
    @return Compatible result with stable error codes and failure fields on failure.
    """
    payload = dict(raw)
    flags = ["success", "saved", "exported", "rebuild_ok"]
    if payload.get("dry_run") is not True:
        flags.extend(("feature_created", "motor_feature_created", "component_added", "mate_created"))
    failed = [name for name in flags if payload.get(name) is False]
    uncertain = [name for name in flags if name in payload and payload[name] is not None and not isinstance(payload[name], bool)]
    uncertain.extend(name for name in ("feature_created", "rebuild_ok") if name in payload and payload[name] is None)
    if payload.get("output_path") and "saved" in payload and payload["saved"] is None:
        uncertain.append("saved")
    if failed:
        payload.update(status="error", success=False,
                       error_code=payload.get("error_code") or "TOOL_OPERATION_FAILED",
                       failed_fields=failed)
        payload.setdefault("message", "Gerekli yürütme adımı başarısız: " + ", ".join(failed))
    elif uncertain:
        payload.update(status="blocked", success=False, error_code="TOOL_RESULT_UNVERIFIED", unverified_fields=uncertain)
    return payload


def _extract_message(raw: Any) -> str:
    """@brief Extract a short handler message without copying the full result."""
    if isinstance(raw, Mapping):
        return str(raw.get("message") or raw.get("summary") or "")
    if raw is None:
        return ""
    return str(raw)[:500]


def _extract_outputs(raw: Any) -> list[Any]:
    """@brief Extract output references from a handler result with minimal normalization."""
    if isinstance(raw, Mapping):
        outputs = raw.get("outputs") or raw.get("artifacts") or []
        return list(outputs) if isinstance(outputs, (list, tuple)) else []
    if raw is None:
        return []
    return [raw]


def _extract_error_code(raw: Any) -> str | None:
    """@brief Extract a structured error_code from the handler result."""
    if isinstance(raw, Mapping):
        return raw.get("error_code") or raw.get("errorCode")
    return None


def _exception_summary(exception: BaseException | None) -> dict[str, Any] | None:
    """@brief Retain exception type, message and error code without the full stack."""
    if exception is None:
        return None
    return {
        "type": type(exception).__name__,
        "message": str(exception)[:500],
        "code": getattr(exception, "code", None),
    }


@dataclass
class ExecutionAssessment:
    """@brief Internal execution assessment sidecar; preserve existing Queue semantics."""

    run_context: RunContext
    step: StepRecord
    execution_result: ExecutionResult
    raw_result: Any = None
    exception: BaseException | None = None
    verification_result: VerificationResult | None = None
    recovery_decision: RecoveryDecision | None = None
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        """@brief Serialize compactly without copying raw_result or the complete exception."""
        return {
            "run_id": self.run_context.run_id,
            "status": self.run_context.status.value,
            "requires_review": self.requires_review,
            "step": self.step.to_dict(),
            "execution": self.execution_result.to_dict(),
            "verification": self.verification_result.to_dict() if self.verification_result else None,
            "recovery": self.recovery_decision.to_dict() if self.recovery_decision else None,
            "exception": _exception_summary(self.exception),
        }


def _trace(
    event_type: str,
    trace_dir: Any,
    *,
    run_id: str | None,
    step_id: str | None,
    capability_id: str | None,
    message: str = "",
    data: Mapping[str, Any] | None = None,
) -> None:
    """@brief Write Trace events; observation failures must not affect execution."""
    if trace_dir is None:
        return
    try:
        emit(
            trace_dir,
            event_type,
            run_id=run_id or None,
            step_id=step_id,
            capability_id=capability_id,
            message=message,
            data=data,
        )
    except Exception:
        pass


def execute_with_core(
    *,
    handler: Callable[[Any], Any],
    handler_arg: Any = None,
    run_id: str,
    step_id: str | None = None,
    tool_name: str = "",
    capability_id: str | None = None,
    operation_id: str | None = None,
    requires_review: bool = False,
    reviewer: Callable[[], Any] | None = None,
    reviewer_result: Any = None,
    artifacts: Sequence[Mapping[str, Any]] | None = None,
    evidence: Sequence[Mapping[str, Any]] | None = None,
    capability_facade: Any = None,
    max_retries: int | None = None,
    trace_dir: Any = None,
    defer_completion: bool = False,
) -> ExecutionAssessment:
    """@brief Connect State + Handler + Verification + Recovery + Trace and return assessment.

    :param handler: Existing handler(job), the only actual execution implementation.
    :param reviewer: Optional zero-argument callable used when requires_review and
        no reviewer_result is supplied.
    :param reviewer_result: Existing dict/list Review result; avoids repeat calls.
    """
    if operation_id or capability_id:
        required = registry_requires_review(operation_id=operation_id, capability_id=capability_id)
        requires_review = requires_review or required is not False
    step_id = step_id or f"{run_id}:step0"
    run = RunContext(run_id=run_id, goal="", trace_id=run_id)
    step = StepRecord(
        step_id=step_id,
        tool_name=tool_name,
        capability_id=capability_id,
        backend=None,
        status=StepStatus.PENDING,
    )
    run.steps.append(step)
    run.current_step = step_id

    _trace("run.started", trace_dir, run_id=run_id, step_id=None, capability_id=capability_id)
    _trace("step.started", trace_dir, run_id=run_id, step_id=step_id, capability_id=capability_id)

    run.transition(RunStatus.RUNNING)
    step.transition(StepStatus.RUNNING)
    _trace("tool.called", trace_dir, run_id=run_id, step_id=step_id, capability_id=capability_id, message=tool_name)

    raw_result: Any = None
    exception: BaseException | None = None
    recovery_decision: RecoveryDecision | None = None
    execution_result: ExecutionResult
    try:
        raw_result = handler(handler_arg)
    except Exception as exc:  # noqa: BLE001 - return captured exceptions to the caller, preserving existing except semantics.
        exception = exc
        kind = classify_error(exception=exc) or ErrorKind.FATAL
        execution_result = ExecutionResult(
            success=False,
            message=str(exc),
            error_code=getattr(exc, "code", None) or type(exc).__name__,
            error_kind=kind.value,
            retryable=kind == ErrorKind.TRANSIENT,
        )
        step.transition(StepStatus.FAILED)
        step.error_code = execution_result.error_code
        step.retryable = execution_result.retryable
        run.transition(RunStatus.FAILED)
        _trace("tool.failed", trace_dir, run_id=run_id, step_id=step_id, capability_id=capability_id,
               message=str(exc), data={"error_code": execution_result.error_code})
        recovery_decision = decide(
            exception=exc,
            operation_id=operation_id,
            capability_id=capability_id,
            capability_facade=capability_facade,
            max_retries=max_retries,
            trace_dir=trace_dir,
            run_id=run_id,
            step_id=step_id,
        )
    else:
        payload = normalize_tool_payload(raw_result) if isinstance(raw_result, Mapping) else None
        failed = raw_result is None or raw_result is False or (
            payload is not None and (payload.get("success") is False or
            str(payload.get("status", "")).lower() in {"error", "fail", "failed", "blocked", "unavailable"})
        )
        execution_result = ExecutionResult(
            success=not failed,
            message=_extract_message(raw_result),
            outputs=_extract_outputs(raw_result),
            error_code=_extract_error_code(payload or {}) or ("TOOL_RESULT_UNAVAILABLE" if failed else None),
        )
        if failed:
            blocked = payload is not None and payload.get("status") == "blocked"
            step.transition(StepStatus.BLOCKED if blocked else StepStatus.FAILED)
            run.transition(RunStatus.BLOCKED if blocked else RunStatus.FAILED)
            step.error_code = execution_result.error_code
            recovery_decision = decide(execution_result=execution_result.to_dict(),
                operation_id=operation_id, capability_id=capability_id,
                capability_facade=capability_facade, max_retries=max_retries,
                trace_dir=trace_dir, run_id=run_id, step_id=step_id)
        _trace("tool.failed" if failed else "tool.succeeded", trace_dir, run_id=run_id, step_id=step_id, capability_id=capability_id,
               message=execution_result.message)

    verification_result: VerificationResult | None = None
    manual_required = isinstance(raw_result, Mapping) and bool(raw_result.get("manual_review_required") or raw_result.get("manualReviewRequired"))
    requires_review = requires_review or manual_required or (isinstance(raw_result, Mapping) and raw_result.get("status") == "review_required")
    if requires_review and execution_result.success and not defer_completion:
        run.transition(RunStatus.VERIFYING)
        step.transition(StepStatus.VERIFYING)
        verification_result = verify(
            reviewer=reviewer,
            reviewer_result=reviewer_result,
            artifacts=artifacts,
            evidence=evidence,
            capability_id=capability_id,
            trace_dir=trace_dir,
            run_id=run_id,
            step_id=step_id,
        )
        step.verification = verification_result
        verification_result.manual_review_required |= manual_required
        if verification_result.status == VerificationStatus.FAIL:
            step.transition(StepStatus.FAILED)
            run.transition(RunStatus.FAILED)
            recovery_decision = decide(
                verification_result=verification_result.to_dict(),
                operation_id=operation_id,
                capability_id=capability_id,
                capability_facade=capability_facade,
                max_retries=max_retries,
                trace_dir=trace_dir,
                run_id=run_id,
                step_id=step_id,
            )
        elif verification_result.status != VerificationStatus.PASS or verification_result.manual_review_required:
            step.transition(StepStatus.BLOCKED)
            run.transition(RunStatus.BLOCKED)
            recovery_decision = decide(
                error_kind=ErrorKind.USER_ACTION_REQUIRED if verification_result.manual_review_required else None,
                verification_result=verification_result.to_dict(),
                operation_id=operation_id,
                capability_id=capability_id,
                capability_facade=capability_facade,
                max_retries=max_retries,
                trace_dir=trace_dir,
                run_id=run_id,
                step_id=step_id,
            )
        else:  # Complete only on explicit PASS with no outstanding manual review.
            step.transition(StepStatus.SUCCESS)
            run.transition(RunStatus.COMPLETED)
    elif execution_result.success:
        step.transition(StepStatus.SUCCESS)
        if not defer_completion:
            run.transition(RunStatus.COMPLETED)

    # Add run terminal events only in full-chain mode; in Worker mode the Worker writes them.
    if requires_review:
        final_event = {
            RunStatus.COMPLETED: "run.completed",
            RunStatus.FAILED: "run.failed",
            RunStatus.BLOCKED: "run.blocked",
        }.get(run.status)
        if final_event:
            _trace(final_event, trace_dir, run_id=run_id, step_id=step_id, capability_id=capability_id,
                   message=verification_result.reason or "" if verification_result else "")

    return ExecutionAssessment(
        run_context=run,
        step=step,
        execution_result=execution_result,
        raw_result=raw_result,
        exception=exception,
        verification_result=verification_result,
        recovery_decision=recovery_decision,
        requires_review=requires_review,
    )


__all__ = ["ExecutionAssessment", "execute_with_core", "normalize_tool_payload"]
