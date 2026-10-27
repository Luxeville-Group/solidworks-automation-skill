"""@brief Internal Execution Core package; this is not a user entry point.

Lightweight reliable-execution models and adapters:
- state: unified execution state model
- capability: facade for capabilities.yaml using the existing router
- trace: append-only Execution Trace adapter for queue/events
- verification: adapt existing Reviewer results into VerificationResult
- recovery: deterministic failure classification and decisions, without actions
- execution: State + Handler + Verification + Recovery + Trace orchestration

Import through top-level core.* with scripts/ on sys.path in CAD-free CI to avoid
legacy COM dependency loading and pywin32 interaction through scripts/__init__.py.
"""
from .capability import (
    capability_gap,
    get_backend_candidates,
    get_capability,
    get_capability_status,
    get_operation_route,
    load_capabilities,
    requires_review,
    resolve_backend,
)
from .state import (
    InvalidStateTransition,
    RECOVERY_ACTIONS,
    SCHEMA_VERSION,
    ExecutionResult,
    RecoveryDecision,
    RunContext,
    RunStatus,
    StepRecord,
    StepStatus,
    VerificationResult,
    VerificationStatus,
    can_transition_run,
    can_transition_step,
    ensure_run_transition,
    ensure_step_transition,
    now_iso,
)
from .trace import (
    TRACE_EVENT_TYPES,
    append_event,
    emit,
    events_dir,
    read_events,
    redact,
    sanitize_id,
    trace_path_for,
)
from .verification import (
    aggregate_checks,
    aggregate_statuses,
    check_status,
    normalize_status,
    verify,
)
from .recovery import (
    DEFAULT_MAX_RETRIES,
    ErrorKind,
    classify_error,
    decide,
)
from .execution import (
    ExecutionAssessment,
    execute_with_core,
)

__all__ = [
    # state
    "InvalidStateTransition",
    "RECOVERY_ACTIONS",
    "SCHEMA_VERSION",
    "ExecutionResult",
    "RecoveryDecision",
    "RunContext",
    "RunStatus",
    "StepRecord",
    "StepStatus",
    "VerificationResult",
    "VerificationStatus",
    "can_transition_run",
    "can_transition_step",
    "ensure_run_transition",
    "ensure_step_transition",
    "now_iso",
    # capability
    "capability_gap",
    "get_backend_candidates",
    "get_capability",
    "get_capability_status",
    "get_operation_route",
    "load_capabilities",
    "requires_review",
    "resolve_backend",
    # trace
    "TRACE_EVENT_TYPES",
    "append_event",
    "emit",
    "events_dir",
    "read_events",
    "redact",
    "sanitize_id",
    "trace_path_for",
    # verification
    "aggregate_checks",
    "aggregate_statuses",
    "check_status",
    "normalize_status",
    "verify",
    # recovery
    "DEFAULT_MAX_RETRIES",
    "ErrorKind",
    "classify_error",
    "decide",
    # execution
    "ExecutionAssessment",
    "execute_with_core",
]
