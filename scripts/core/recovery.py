"""@brief Deterministic recovery decisions after failure.

Answer which action to take next without performing it. Do not retry, rerun tools,
switch backends, replan, modify models, call reviewers or access the network.
Actual actions remain with the Phase 5 Worker/existing Handler.

classify_error normalizes failures into ten ErrorKind categories; decide maps
ErrorKind and context to the Phase 2 RecoveryDecision model.

Uncertainty defaults to BLOCK / FAIL / REPLAN, never retry. Classify unknown
errors conservatively as FATAL, never transient.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from . import capability as _capability_facade
from .state import RecoveryDecision, VerificationStatus
from .trace import emit
from .verification import check_status, normalize_status

#: Conservative retry-budget default; do not permit 3, 5 or unlimited retries.
DEFAULT_MAX_RETRIES = 2


class ErrorKind(str, Enum):
    """@brief Execution-layer error categories, not an exhaustive CAD error-code catalog."""

    TRANSIENT = "transient"
    INVALID_ARGUMENT = "invalid_argument"
    ENVIRONMENT_MISSING = "environment_missing"
    TOOL_UNAVAILABLE = "tool_unavailable"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    VERIFICATION_FAILED = "verification_failed"
    USER_ACTION_REQUIRED = "user_action_required"
    POLICY_BLOCKED = "policy_blocked"
    CAPABILITY_GAP = "capability_gap"
    FATAL = "fatal"


# Confirmed historical error_code -> ErrorKind mappings from actual Reviewer/Router/Worker
# fields. Keys are lowercase; unknown codes fall through rather than being guessed.
_ERROR_CODE_KIND: dict[str, ErrorKind] = {
    "sw_file_not_found": ErrorKind.INVALID_ARGUMENT,
    "sw_file_requires_repair": ErrorKind.USER_ACTION_REQUIRED,
    "sw_file_future_version": ErrorKind.USER_ACTION_REQUIRED,
    "sw_low_resources": ErrorKind.USER_ACTION_REQUIRED,
    "sw_file_application_busy": ErrorKind.USER_ACTION_REQUIRED,
    "sw_file_load_failed": ErrorKind.TOOL_UNAVAILABLE,
    "sw_document_state_unavailable": ErrorKind.USER_ACTION_REQUIRED,
    "sw_instance_mismatch": ErrorKind.USER_ACTION_REQUIRED,
    "sw_pack_and_go_timeout": ErrorKind.USER_ACTION_REQUIRED,
    "sw_pack_and_go_worker_protocol": ErrorKind.USER_ACTION_REQUIRED,
    "sw_document_budget": ErrorKind.USER_ACTION_REQUIRED,
    "sw_process_state_unavailable": ErrorKind.USER_ACTION_REQUIRED,
    "sw_instance_not_ready": ErrorKind.USER_ACTION_REQUIRED,
    "sw_version_mismatch": ErrorKind.USER_ACTION_REQUIRED,
    # TRANSIENT
    "occt_timeout": ErrorKind.TRANSIENT,
    "drawing_pdf_text_parse_failed": ErrorKind.TRANSIENT,
    "autocad_com_unstable": ErrorKind.TRANSIENT,
    # INVALID_ARGUMENT
    "invalid_neutral_document": ErrorKind.INVALID_ARGUMENT,
    "dfm_unknown_process": ErrorKind.INVALID_ARGUMENT,
    "dfm_invalid_profile": ErrorKind.INVALID_ARGUMENT,
    "dfm_invalid_brep_evidence": ErrorKind.INVALID_ARGUMENT,
    "dfm_missing_inputs": ErrorKind.INVALID_ARGUMENT,
    "advanced_geometry_invalid_plan": ErrorKind.INVALID_ARGUMENT,
    "fea_convergence_invalid_request": ErrorKind.INVALID_ARGUMENT,
    "sketch_not_active": ErrorKind.INVALID_ARGUMENT,
    "drawing_spec_blocked": ErrorKind.INVALID_ARGUMENT,
    "routing_document_invalid": ErrorKind.INVALID_ARGUMENT,
    "operation_required": ErrorKind.INVALID_ARGUMENT,
    # ENVIRONMENT_MISSING
    "fea_solver_missing": ErrorKind.ENVIRONMENT_MISSING,
    "dotnet_sdk_missing": ErrorKind.ENVIRONMENT_MISSING,
    "autocad_not_found": ErrorKind.ENVIRONMENT_MISSING,
    "winget_missing": ErrorKind.ENVIRONMENT_MISSING,
    "windows_required": ErrorKind.ENVIRONMENT_MISSING,
    "advanced_geometry_runtime_missing": ErrorKind.ENVIRONMENT_MISSING,
    "drawing_pdf_text_parser_missing": ErrorKind.ENVIRONMENT_MISSING,
    "drawing_bom_template_missing": ErrorKind.ENVIRONMENT_MISSING,
    "missing_runtime_requirement": ErrorKind.ENVIRONMENT_MISSING,
    "occt_dependency_or_capability_missing": ErrorKind.ENVIRONMENT_MISSING,
    "dfm_brep_evidence_required": ErrorKind.ENVIRONMENT_MISSING,
    "autocad_core_console_prerequisite_missing": ErrorKind.ENVIRONMENT_MISSING,
    # TOOL_UNAVAILABLE
    "sketch_autodimension_call_failed": ErrorKind.TOOL_UNAVAILABLE,
    "autocad_script_command_failed": ErrorKind.TOOL_UNAVAILABLE,
    # BACKEND_UNAVAILABLE
    "no_compatible_backend_available": ErrorKind.BACKEND_UNAVAILABLE,
    "no_language_substitution": ErrorKind.BACKEND_UNAVAILABLE,
    "autocad_dotnet_runtime_not_verified": ErrorKind.BACKEND_UNAVAILABLE,
    "advanced_geometry_backend_unverified": ErrorKind.BACKEND_UNAVAILABLE,
    "occt_result_missing": ErrorKind.BACKEND_UNAVAILABLE,
    # VERIFICATION_FAILED
    "fea_result_frd_missing": ErrorKind.VERIFICATION_FAILED,
    "fea_convergence_case_failed": ErrorKind.VERIFICATION_FAILED,
    "drawing_final_pdf_required": ErrorKind.VERIFICATION_FAILED,
    "drawing_structure_evidence_missing": ErrorKind.VERIFICATION_FAILED,
    "drawing_semantic_evidence_incomplete": ErrorKind.VERIFICATION_FAILED,
    "drawing_review_findings": ErrorKind.VERIFICATION_FAILED,
    "autocad_dotnet_evidence_invalid": ErrorKind.VERIFICATION_FAILED,
    # USER_ACTION_REQUIRED
    "solidworks_busy_timeout": ErrorKind.USER_ACTION_REQUIRED,
    "known_host_revision_blocker": ErrorKind.USER_ACTION_REQUIRED,
    # POLICY_BLOCKED
    "script_command_not_allowed": ErrorKind.POLICY_BLOCKED,
    # CAPABILITY_GAP
    "unknown_operation_route": ErrorKind.CAPABILITY_GAP,
    "fea_elmer_adapter_not_implemented": ErrorKind.CAPABILITY_GAP,
    "drawing_spec_capability_unsupported": ErrorKind.CAPABILITY_GAP,
    # FATAL
    "occt_geometry_failed": ErrorKind.FATAL,
    "autocad_dotnet_build_failed": ErrorKind.FATAL,
    "drawing_sheet_setup_failed": ErrorKind.FATAL,
    "drawing_view_create_failed": ErrorKind.FATAL,
}

# Explicit exception type -> ErrorKind; match type name before isinstance fallback.
_EXCEPTION_KIND: dict[str, ErrorKind] = {
    "TimeoutError": ErrorKind.TRANSIENT,
    "SolidWorksNotInstalledError": ErrorKind.ENVIRONMENT_MISSING,
    "DependencyInstallDeclined": ErrorKind.USER_ACTION_REQUIRED,
    "SolidWorksConnectionError": ErrorKind.BACKEND_UNAVAILABLE,
    "DesignSpecError": ErrorKind.INVALID_ARGUMENT,
    "DfmProfileError": ErrorKind.INVALID_ARGUMENT,
    "UnsupportedFeatureError": ErrorKind.CAPABILITY_GAP,
    "ModuleNotFoundError": ErrorKind.ENVIRONMENT_MISSING,
    "ImportError": ErrorKind.ENVIRONMENT_MISSING,
}

# General message keywords, lowest priority and restricted to actual repository wording.
_MESSAGE_HINTS: tuple[tuple[str, ErrorKind], ...] = (
    ("timeout", ErrorKind.TRANSIENT),
    ("zaman aşımı", ErrorKind.TRANSIENT),
    ("unstable", ErrorKind.TRANSIENT),
    ("kararsız", ErrorKind.TRANSIENT),
    ("not installed", ErrorKind.ENVIRONMENT_MISSING),
    ("bulunamadı", ErrorKind.ENVIRONMENT_MISSING),
    ("not found", ErrorKind.ENVIRONMENT_MISSING),
    ("license", ErrorKind.USER_ACTION_REQUIRED),
    ("lisans", ErrorKind.USER_ACTION_REQUIRED),
    ("approval", ErrorKind.POLICY_BLOCKED),
    ("onay", ErrorKind.POLICY_BLOCKED),
    ("not allowed", ErrorKind.POLICY_BLOCKED),
    ("unsupported", ErrorKind.CAPABILITY_GAP),
    ("not implemented", ErrorKind.CAPABILITY_GAP),
    ("desteklenmiyor", ErrorKind.CAPABILITY_GAP),
)

# BLOCKED subcategories exclude transient to avoid misclassification.
_BLOCKED_HINTS: tuple[tuple[str, ErrorKind], ...] = (
    ("license", ErrorKind.USER_ACTION_REQUIRED),
    ("lisans", ErrorKind.USER_ACTION_REQUIRED),
    ("approval", ErrorKind.POLICY_BLOCKED),
    ("onay", ErrorKind.POLICY_BLOCKED),
    ("not allowed", ErrorKind.POLICY_BLOCKED),
    ("not installed", ErrorKind.ENVIRONMENT_MISSING),
    ("bulunamadı", ErrorKind.ENVIRONMENT_MISSING),
    ("missing", ErrorKind.ENVIRONMENT_MISSING),
    ("eksik", ErrorKind.ENVIRONMENT_MISSING),
    ("unsupported", ErrorKind.CAPABILITY_GAP),
    ("not implemented", ErrorKind.CAPABILITY_GAP),
    ("desteklenmiyor", ErrorKind.CAPABILITY_GAP),
    ("unavailable", ErrorKind.BACKEND_UNAVAILABLE),
)


def _coerce_kind(value: Any) -> ErrorKind | None:
    """@brief Normalize a string/enum to ErrorKind; unknown values return None rather than being trusted."""
    if isinstance(value, ErrorKind):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    for member in ErrorKind:
        if member.value == text:
            return member
    return None


def _hint_kind(text: str, hints: tuple[tuple[str, ErrorKind], ...]) -> ErrorKind | None:
    """@brief Return the first keyword-table match or None."""
    lowered = text.lower()
    for keyword, kind in hints:
        if keyword in lowered:
            return kind
    return None


def _classify_exception(exception: BaseException) -> ErrorKind:
    """@brief Map exception types to ErrorKind, preferring names before isinstance fallback."""
    name = type(exception).__name__
    if name in _EXCEPTION_KIND:
        return _EXCEPTION_KIND[name]
    if isinstance(exception, TimeoutError):
        return ErrorKind.TRANSIENT
    if isinstance(exception, (ModuleNotFoundError, ImportError)):
        return ErrorKind.ENVIRONMENT_MISSING
    if isinstance(exception, ValueError):
        return ErrorKind.INVALID_ARGUMENT
    return ErrorKind.FATAL


def _verification_fail_present(verification_result: Mapping[str, Any]) -> bool:
    """@brief Check required/critical FAIL so aggregate BLOCKED cannot conceal it."""
    for check in verification_result.get("checks") or []:
        if isinstance(check, Mapping) and check_status(check) == VerificationStatus.FAIL:
            return True
    return False


def _classify_blocked(result: Mapping[str, Any]) -> ErrorKind:
    """@brief Classify a BLOCKED reason, defaulting to USER_ACTION_REQUIRED."""
    text = " ".join(
        filter(
            None,
            [str(result.get("reason") or ""), str(result.get("message") or "")],
        )
    ).strip()
    if text:
        kind = _hint_kind(text, _BLOCKED_HINTS)
        if kind is not None:
            return kind
    return ErrorKind.USER_ACTION_REQUIRED


def _classify_verification(verification_result: Mapping[str, Any]) -> ErrorKind | None:
    """@brief Map VerificationResult to ErrorKind; PASS/WARN return None without recovery."""
    status = normalize_status(verification_result.get("status"))
    if status in (VerificationStatus.PASS, VerificationStatus.WARN):
        return None
    if status == VerificationStatus.FAIL:
        return ErrorKind.VERIFICATION_FAILED
    # Required FAIL overrides BLOCKED; otherwise classify the reason.
    if _verification_fail_present(verification_result):
        return ErrorKind.VERIFICATION_FAILED
    return _classify_blocked(verification_result)


def _classify_capability(capability_result: Mapping[str, Any]) -> ErrorKind | None:
    """@brief Map Capability Facade/Router results to ErrorKind."""
    status = str(capability_result.get("status") or "").strip().lower()
    if status == "capability_gap":
        return ErrorKind.CAPABILITY_GAP
    code = str(capability_result.get("error_code") or "").strip().lower()
    if code and code in _ERROR_CODE_KIND:
        return _ERROR_CODE_KIND[code]
    if status == "unavailable":
        return ErrorKind.BACKEND_UNAVAILABLE
    if status == "blocked":
        return _classify_blocked(capability_result)
    return None


def _classify_execution(execution_result: Mapping[str, Any]) -> ErrorKind | None:
    """@brief Map ExecutionResult to ErrorKind; tool success returns None for verification to assess."""
    if execution_result.get("success") is True:
        return None
    code = str(execution_result.get("error_code") or "").strip().lower()
    if code and code in _ERROR_CODE_KIND:
        return _ERROR_CODE_KIND[code]
    kind = _coerce_kind(execution_result.get("error_kind"))
    if kind is not None:
        return kind
    return ErrorKind.TOOL_UNAVAILABLE


def classify_error(
    *,
    error_kind: Any = None,
    error_code: str | None = None,
    exception: BaseException | None = None,
    execution_result: Mapping[str, Any] | None = None,
    verification_result: Mapping[str, Any] | None = None,
    capability_result: Mapping[str, Any] | None = None,
    policy_result: Mapping[str, Any] | None = None,
    message: str | None = None,
) -> ErrorKind | None:
    """@brief Classify failure facts as ErrorKind; nonfailures such as PASS return None.

    Deterministic precedence: explicit error_kind -> structured error_code ->
    result state (policy > capability > verification > execution) -> exception
    type -> message keywords -> FATAL for unknown failures.
    """
    if error_kind is not None:
        kind = _coerce_kind(error_kind)
        if kind is not None:
            return kind

    if error_code:
        code = str(error_code).strip().lower()
        kind = _ERROR_CODE_KIND.get(code)
        if kind is not None:
            return kind

    if policy_result is not None:
        return ErrorKind.POLICY_BLOCKED

    if capability_result is not None:
        kind = _classify_capability(capability_result)
        if kind is not None:
            return kind

    if verification_result is not None:
        # PASS/WARN deterministically require no recovery; FAIL/BLOCKED return their kind.
        return _classify_verification(verification_result)

    if execution_result is not None:
        kind = _classify_execution(execution_result)
        if kind is not None:
            return kind

    if exception is not None:
        code = str(getattr(exception, "code", "") or "").lower()
        if code in _ERROR_CODE_KIND:
            return _ERROR_CODE_KIND[code]
        return _classify_exception(exception)

    if message:
        kind = _hint_kind(str(message), _MESSAGE_HINTS)
        if kind is not None:
            return kind

    return ErrorKind.FATAL


def _resolve_fallback(
    *,
    operation_id: str | None,
    failed_backend: str | None,
    explicit_fallback: str | None,
    capability_facade: Any,
) -> str | None:
    """@brief Query fallback backends through the facade; recommend without executing."""
    if explicit_fallback:
        return str(explicit_fallback)
    if not operation_id or capability_facade is None:
        return None
    try:
        candidates = capability_facade.get_backend_candidates(operation_id)
    except Exception:
        return None
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        backend = candidate.get("backend")
        if backend and str(backend) != (failed_backend or ""):
            return str(backend)
    return None


def _trace_decision(decision: RecoveryDecision, trace_dir: Any, run_id: str | None, step_id: str | None) -> None:
    """@brief Write recovery events without letting observation failures change decisions."""
    if trace_dir is None:
        return
    if decision.decision == "retry":
        event_type = "recovery.retry"
    elif decision.decision == "fallback_backend":
        event_type = "recovery.backend_fallback"
    else:
        event_type = "recovery.decision"
    try:
        emit(
            trace_dir,
            event_type,
            run_id=run_id or None,
            step_id=step_id,
            error_code=decision.error_kind,
            retry_count=decision.retry_count,
            message=decision.reason,
            data={"action": decision.decision, "fallback_backend": decision.fallback_backend},
        )
    except Exception:
        pass


def decide(
    *,
    error_kind: Any = None,
    error_code: str | None = None,
    exception: BaseException | None = None,
    message: str | None = None,
    execution_result: Mapping[str, Any] | None = None,
    verification_result: Mapping[str, Any] | None = None,
    capability_result: Mapping[str, Any] | None = None,
    policy_result: Mapping[str, Any] | None = None,
    capability_id: str | None = None,
    operation_id: str | None = None,
    failed_backend: str | None = None,
    fallback_backend: str | None = None,
    retry_count: int = 0,
    max_retries: int | None = None,
    capability_facade: Any = None,
    trace_dir: Any = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> RecoveryDecision | None:
    """@brief Choose the next failure action; return None for PASS/WARN or no recovery.

    :param capability_facade: Injectable facade with get_backend_candidates and
        get_capability. Defaults to core.capability; tests may inject a fake.
    """
    kind = classify_error(
        error_kind=error_kind,
        error_code=error_code,
        exception=exception,
        execution_result=execution_result,
        verification_result=verification_result,
        capability_result=capability_result,
        policy_result=policy_result,
        message=message,
    )
    if kind is None:
        return None

    budget = max(0, int(max_retries) if max_retries is not None else DEFAULT_MAX_RETRIES)
    count = max(0, int(retry_count or 0))
    facade = capability_facade if capability_facade is not None else _capability_facade

    action: str
    fallback: str | None = None
    reason: str

    if kind == ErrorKind.TRANSIENT:
        if count < budget:
            action, reason = "retry", "Geçici hata; sınırlı retry yapılabilir"
        else:
            action, reason = "fail", f"Geçici hata yeniden deneme sınırına ulaşıldı (max_retries={budget})"
    elif kind == ErrorKind.INVALID_ARGUMENT:
        action, reason = "replan_required", "Geçersiz parametreler; üst Agent düzeltip yeniden denemelidir"
    elif kind == ErrorKind.BACKEND_UNAVAILABLE:
        fallback = _resolve_fallback(
            operation_id=operation_id,
            failed_backend=failed_backend,
            explicit_fallback=fallback_backend,
            capability_facade=facade,
        )
        if fallback:
            action, reason = "fallback_backend", f"Ana backend kullanılamıyor; fallback: {fallback}"
        else:
            action, reason = "block", "Kullanılabilir backend veya izinli fallback yok"
    elif kind == ErrorKind.TOOL_UNAVAILABLE:
        # Existing capability returns to the agent for composition/alternate entry; absent capability produces CAPABILITY_GAP.
        if capability_id is not None and facade is not None:
            try:
                if facade.get_capability(capability_id) is None:
                    reason = "Capability gap; doğrulama için üst Agent gerekiyor (agent_resolution_required)"
                    decision = RecoveryDecision(
                        decision="replan_required",
                        reason=reason,
                        retry_count=count,
                        max_retries=budget,
                        error_kind=ErrorKind.CAPABILITY_GAP.value,
                    )
                    _trace_decision(decision, trace_dir, run_id, step_id)
                    return decision
            except Exception:
                pass
        action, reason = "replan_required", "Tool kullanılamıyor; birleştirme veya alternatif giriş için üst Agent gerekiyor"
    elif kind == ErrorKind.ENVIRONMENT_MISSING:
        fallback = _resolve_fallback(
            operation_id=operation_id,
            failed_backend=failed_backend,
            explicit_fallback=fallback_backend,
            capability_facade=facade,
        )
        if fallback:
            action, reason = "fallback_backend", f"Ortam eksik; fallback: {fallback}"
        else:
            action, reason = "block", "Ortam eksik ve izinli fallback yok"
    elif kind == ErrorKind.VERIFICATION_FAILED:
        action, reason = "replan_required", "Yürütme başarılı ancak verification başarısız; düzeltip yineleyin, başarı bildirmeyin"
    elif kind == ErrorKind.USER_ACTION_REQUIRED:
        action, reason = "user_action_required", "Engeli kaldırmak için kullanıcı işlemi gerekli"
    elif kind == ErrorKind.POLICY_BLOCKED:
        action, reason = "block", "Policy Gate engelledi; Recovery ile aşılamaz"
    elif kind == ErrorKind.CAPABILITY_GAP:
        action, reason = "replan_required", "Capability gap; doğrulama için üst Agent gerekiyor (agent_resolution_required)"
    else:  # FATAL or unexpected
        action, reason = "fail", "Kritik hata; otomatik retry yapılamaz"

    decision = RecoveryDecision(
        decision=action,
        reason=reason,
        retry_count=count,
        max_retries=budget,
        fallback_backend=fallback,
        error_kind=kind.value,
    )
    _trace_decision(decision, trace_dir, run_id, step_id)
    return decision


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "ErrorKind",
    "classify_error",
    "decide",
]
