"""@brief Adapt existing Reviewer results to VerificationResult.

This module implements no CAD, geometry, drawing or file-fact checks and does not
rebuild Artifact Ledger or Reviewer Gate. It calls an injected Reviewer (or accepts
existing results), normalizes statuses and constructs VerificationResult.

The Reviewer owns checks; this adapter only translates their results. Execution
Core combines execution.success and VerificationResult to decide final success.
core.capability.requires_review decides whether review is required; this module
reads no capability configuration and performs no recovery, retry, fallback or repair.

Unverifiable results never become PASS. Missing Reviewers, exceptions and unknown
statuses become BLOCKED, preserving reason/error_code for recovery.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

from .state import VerificationResult, VerificationStatus
from .trace import emit

# Confirmed legacy formats and explicit V2 aliases map to unified statuses;
# normalize_status safely degrades any unlisted value to BLOCKED.
_STATUS_MAP: dict[str, VerificationStatus] = {
    # Confirmed top-level Review status fields
    "pass": VerificationStatus.PASS,
    "warn": VerificationStatus.WARN,
    "warning": VerificationStatus.WARN,
    "review_required": VerificationStatus.WARN,
    "fail": VerificationStatus.FAIL,
    "failed": VerificationStatus.FAIL,
    "blocked": VerificationStatus.BLOCKED,
    # Tool/evidence aliases explicitly required by V2
    "passed": VerificationStatus.PASS,
    "ok": VerificationStatus.PASS,
    "success": VerificationStatus.PASS,
    "error": VerificationStatus.FAIL,
    "invalid": VerificationStatus.FAIL,
    "unsupported": VerificationStatus.BLOCKED,
    "unavailable": VerificationStatus.BLOCKED,
    "manual_required": VerificationStatus.BLOCKED,
}

# BLOCKED > FAIL > WARN > PASS
_STATUS_PRIORITY: dict[VerificationStatus, int] = {
    VerificationStatus.BLOCKED: 3,
    VerificationStatus.FAIL: 2,
    VerificationStatus.WARN: 1,
    VerificationStatus.PASS: 0,
}

# These severities are informational/noncritical: fail becomes WARN rather than FAIL.
_NON_BLOCKING_SEVERITY = frozenset(
    {"p2", "low", "info", "informational", "optional", "note", "debug"}
)

# Final status -> Trace event type, preserving Phase 2 append-only events;
# verification_status carries actual state; warned/blocked were added in Phase 3.
_STATUS_EVENT: dict[VerificationStatus, str] = {
    VerificationStatus.PASS: "verification.passed",
    VerificationStatus.FAIL: "verification.failed",
    VerificationStatus.WARN: "verification.warned",
    VerificationStatus.BLOCKED: "verification.blocked",
}


def normalize_status(value: Any) -> VerificationStatus:
    """@brief Normalize legacy status strings; safely degrade unknown values to BLOCKED."""
    if isinstance(value, VerificationStatus):
        return value
    if value is None or str(value).strip() == "":
        return VerificationStatus.BLOCKED
    return _STATUS_MAP.get(str(value).strip().lower(), VerificationStatus.BLOCKED)


def aggregate_statuses(statuses: Iterable[VerificationStatus | str]) -> VerificationStatus:
    """@brief Aggregate deterministically as BLOCKED > FAIL > WARN > PASS; empty sets become BLOCKED."""
    normalized = [normalize_status(item) for item in statuses]
    if not normalized:
        return VerificationStatus.BLOCKED
    return max(normalized, key=lambda item: _STATUS_PRIORITY[item])


def check_status(check: Mapping[str, Any]) -> VerificationStatus:
    """@brief Normalize a Check respecting severity/required/optional; informational failures become WARN."""
    status = normalize_status(check.get("status"))
    if status == VerificationStatus.FAIL:
        severity = str(check.get("severity") or "").strip().lower()
        if severity in _NON_BLOCKING_SEVERITY:
            return VerificationStatus.WARN
        if check.get("optional") is True or check.get("required") is False:
            return VerificationStatus.WARN
    return status


def aggregate_checks(checks: Iterable[Mapping[str, Any]]) -> VerificationStatus:
    """@brief Aggregate raw Checks respecting severity and required."""
    normalized = [check_status(item) for item in checks if isinstance(item, Mapping)]
    return aggregate_statuses(normalized)


def _coerce_results(value: Any) -> list[Mapping[str, Any]]:
    """@brief Normalize reviewer dict/list/None into a result list."""
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _status_from_result(result: Mapping[str, Any]) -> VerificationStatus:
    """@brief Read formal Review status, including run_review evaluation.status."""
    raw = result.get("status")
    if raw is None and isinstance(result.get("evaluation"), Mapping):
        raw = result["evaluation"].get("status")
    return normalize_status(raw)


def _result_reason(status: VerificationStatus, results: list[Mapping[str, Any]]) -> str | None:
    """@brief Return reason/message for the aggregate final state, or None."""
    if status == VerificationStatus.PASS:
        return None
    for result in results:
        if _status_from_result(result) != status:
            continue
        for key in ("reason", "message", "error_code", "manual_review_reason"):
            value = result.get(key)
            if value:
                return str(value)
    return None


def _result_error_code(status: VerificationStatus, results: list[Mapping[str, Any]]) -> str | None:
    """@brief Return error_code associated with the aggregate final state."""
    if status == VerificationStatus.PASS:
        return None
    for result in results:
        if _status_from_result(result) != status:
            continue
        value = result.get("error_code")
        if value:
            return str(value)
    return None


def _dedup_artifacts(items: Iterable[Any]) -> list[dict[str, Any]]:
    """@brief Merge artifacts and deduplicate paths while preserving order."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        record = dict(item)
        path = record.get("path")
        if path is not None:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
        result.append(record)
    return result


def _trace_event(
    event_type: str,
    trace_dir: Any,
    *,
    run_id: str | None,
    step_id: str | None,
    capability_id: str | None,
    status: VerificationStatus | None,
    message: str = "",
    data: Mapping[str, Any] | None = None,
) -> None:
    """@brief Write Trace events without allowing observation failure to affect verification."""
    if trace_dir is None:
        return
    try:
        emit(
            trace_dir,
            event_type,
            run_id=run_id or None,
            step_id=step_id,
            capability_id=capability_id,
            verification_status=status.value if status is not None else None,
            message=message,
            data=data,
        )
    except Exception:
        # Observability must not become a prerequisite for business success.
        pass


def _execution_summary(execution: Any) -> dict[str, Any] | None:
    """@brief Extract minimal execution context for Trace only, without judging it."""
    if execution is None:
        return None
    if isinstance(execution, Mapping):
        return {"success": execution.get("success"), "error_code": execution.get("error_code")}
    if hasattr(execution, "success"):
        return {"success": execution.success, "error_code": getattr(execution, "error_code", None)}
    return None


def verify(
    *,
    capability_id: str | None = None,
    execution: Any = None,
    reviewer: Callable[[], Any] | None = None,
    reviewer_result: Any = None,
    artifacts: Sequence[Mapping[str, Any]] | None = None,
    evidence: Sequence[Mapping[str, Any]] | None = None,
    trace_dir: Any = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> VerificationResult:
    """@brief Call the Reviewer and normalize to VerificationResult.

    :param reviewer: Zero-argument callable returning dict, list or None. Use the
        actual reviewer, such as evaluate_ledger, in production; inject fakes in tests.
    :param reviewer_result: Existing dict/list result instead of calling reviewer.
    :param artifacts: Existing Artifact Ledger facts: path/exists/size/hash/kind.
    :param evidence: Existing references attached unchanged to evidence.
    :param trace_dir: Optional queue folder for verification.* events; writing
        failure does not affect the verification result.
    """
    _trace_event(
        "verification.started",
        trace_dir,
        run_id=run_id,
        step_id=step_id,
        capability_id=capability_id,
        status=None,
        message="Doğrulama başlıyor",
        data=_execution_summary(execution),
    )

    results: list[Mapping[str, Any]] = []
    reviewer_error: Exception | None = None
    if reviewer_result is not None:
        # Prefer existing results: do not repeat Reviewer calls when Worker/Handler already produced them.
        results = _coerce_results(reviewer_result)
    elif reviewer is not None:
        try:
            results = _coerce_results(reviewer())
        except Exception as exc:  # noqa: BLE001 - safely degrade Reviewer exceptions rather than propagating them.
            reviewer_error = exc

    if reviewer_error is not None:
        verdict = VerificationResult(
            status=VerificationStatus.BLOCKED,
            reason=f"Reviewer çalıştırılamadı: {type(reviewer_error).__name__}",
            checks=[{"id": "verification_reviewer_error", "status": "blocked", "message": str(reviewer_error)}],
            error_code="reviewer_error",
            manual_review_required=False,
        )
        _trace_event(
            _STATUS_EVENT[verdict.status],
            trace_dir,
            run_id=run_id,
            step_id=step_id,
            capability_id=capability_id,
            status=verdict.status,
            message=verdict.reason or "",
        )
        return verdict

    if not results:
        verdict = VerificationResult(
            status=VerificationStatus.BLOCKED,
            reason="Reviewer yapılandırılmadı ve mevcut Review sonucu yok; verification tamamlanamıyor",
            error_code="verification_unavailable",
        )
        _trace_event(
            _STATUS_EVENT[verdict.status],
            trace_dir,
            run_id=run_id,
            step_id=step_id,
            capability_id=capability_id,
            status=verdict.status,
            message=verdict.reason or "",
        )
        return verdict

    status = aggregate_statuses(_status_from_result(result) for result in results)
    checks: list[dict[str, Any]] = []
    for result in results:
        for key in ("checks", "issues"):
            for item in result.get(key) or []:
                if isinstance(item, Mapping):
                    checks.append(dict(item))
    if checks:
        status = aggregate_statuses((status, aggregate_checks(checks)))

    merged_artifacts = _dedup_artifacts(
        [*(artifacts or [])]
        + [item for result in results for item in (result.get("artifacts") or [])]
    )
    merged_evidence = [*(evidence or [])] + [
        item for result in results for item in (result.get("evidence") or []) if isinstance(item, Mapping)
    ]
    manual_review_required = status == VerificationStatus.WARN or any(
        bool(result.get("manual_review_required") or result.get("manualReviewRequired"))
        for result in results
    )

    verdict = VerificationResult(
        status=status,
        reason=_result_reason(status, results),
        checks=checks,
        artifacts=merged_artifacts,
        evidence=merged_evidence,
        manual_review_required=manual_review_required,
        error_code=_result_error_code(status, results),
    )
    _trace_event(
        _STATUS_EVENT[verdict.status],
        trace_dir,
        run_id=run_id,
        step_id=step_id,
        capability_id=capability_id,
        status=verdict.status,
        message=verdict.reason or ("Doğrulama başarılı" if verdict.status == VerificationStatus.PASS else ""),
    )
    return verdict


__all__ = [
    "aggregate_checks",
    "aggregate_statuses",
    "check_status",
    "normalize_status",
    "verify",
]
