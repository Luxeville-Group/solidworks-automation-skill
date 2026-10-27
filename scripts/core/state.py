"""@brief Lightweight Execution Core state models.

JSON-serializable, schema-versioned runtime structures decoupled from CAD Studio
Queue Job and shared by Worker/MCP/CLI. Provide a minimal transition allowlist
that rejects FAILED -> COMPLETED and BLOCKED -> COMPLETED rather than a full FSM.

State values are lowercase to match queue conventions; VerificationStatus follows
the uppercase V2 PASS/WARN/FAIL/BLOCKED convention.

Retain no complete prompts, API keys or secrets. Store arguments_summary and
result_summary instead of raw content. Avoid unnecessary complete private paths.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"


def now_iso() -> str:
    """@brief Return a UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunStatus(str, Enum):
    """@brief Lifecycle state of a Run."""

    CREATED = "created"
    RUNNING = "running"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class StepStatus(str, Enum):
    """@brief Lifecycle state of a Step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    BLOCKED = "blocked"


class VerificationStatus(str, Enum):
    """@brief Verification conclusion using uppercase V2 values."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


#: Allowed structured recovery decisions; the engine is implemented in a later phase.
RECOVERY_ACTIONS = frozenset(
    {
        "retry",
        "fallback_backend",
        "replan_required",
        "user_action_required",
        "block",
        "fail",
    }
)


class InvalidStateTransition(ValueError):
    """@brief Invalid state transition."""


# Minimal transition allowlist rejects obvious invalid transitions without a complex FSM.
_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.RUNNING, RunStatus.BLOCKED, RunStatus.FAILED},
    RunStatus.RUNNING: {
        RunStatus.VERIFYING,
        RunStatus.RETRYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.COMPLETED,
    },
    RunStatus.VERIFYING: {
        RunStatus.COMPLETED,
        RunStatus.RETRYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
    },
    RunStatus.RETRYING: {
        RunStatus.RUNNING,
        RunStatus.VERIFYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
    },
    RunStatus.BLOCKED: {RunStatus.RUNNING},
    RunStatus.FAILED: {RunStatus.RETRYING},
    RunStatus.COMPLETED: set(),
}

_STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.BLOCKED},
    StepStatus.RUNNING: {
        StepStatus.SUCCESS,
        StepStatus.FAILED,
        StepStatus.VERIFYING,
        StepStatus.BLOCKED,
    },
    StepStatus.VERIFYING: {
        StepStatus.SUCCESS,
        StepStatus.FAILED,
        StepStatus.RETRYING,
        StepStatus.BLOCKED,
    },
    StepStatus.RETRYING: {StepStatus.RUNNING, StepStatus.BLOCKED, StepStatus.FAILED},
    StepStatus.BLOCKED: {StepStatus.RUNNING, StepStatus.PENDING},
    StepStatus.SUCCESS: set(),
    StepStatus.FAILED: {StepStatus.RETRYING},
}


def _coerce_enum(enum_cls: type[Enum], value: Any, default: Any = None) -> Any:
    """@brief Tolerantly normalize strings/enums to members, using the default for unknown values."""
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    text = str(value)
    for member in enum_cls:
        if member.value.lower() == text.lower():
            return member
    try:
        return enum_cls(text)
    except ValueError:
        return default


def _serialize(value: Any) -> Any:
    """@brief Recursively convert Enum members to values for JSON compatibility."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def can_transition_run(current: RunStatus | str, target: RunStatus | str) -> bool:
    """@brief Determine whether a Run transition is permitted."""
    current = _coerce_enum(RunStatus, current, None)
    target = _coerce_enum(RunStatus, target, None)
    if current is None or target is None:
        return False
    return target in _RUN_TRANSITIONS.get(current, set())


def can_transition_step(current: StepStatus | str, target: StepStatus | str) -> bool:
    """@brief Determine whether a Step transition is permitted."""
    current = _coerce_enum(StepStatus, current, None)
    target = _coerce_enum(StepStatus, target, None)
    if current is None or target is None:
        return False
    return target in _STEP_TRANSITIONS.get(current, set())


def ensure_run_transition(current: RunStatus | str, target: RunStatus | str) -> None:
    """@brief Validate a Run transition or raise InvalidStateTransition."""
    if not can_transition_run(current, target):
        cur = _coerce_enum(RunStatus, current, current)
        tgt = _coerce_enum(RunStatus, target, target)
        raise InvalidStateTransition(
            f"Geçersiz Run durum geçişi: {getattr(cur, 'value', cur)} -> {getattr(tgt, 'value', tgt)}"
        )


def ensure_step_transition(current: StepStatus | str, target: StepStatus | str) -> None:
    """@brief Validate a Step transition or raise InvalidStateTransition."""
    if not can_transition_step(current, target):
        cur = _coerce_enum(StepStatus, current, current)
        tgt = _coerce_enum(StepStatus, target, target)
        raise InvalidStateTransition(
            f"Geçersiz Step durum geçişi: {getattr(cur, 'value', cur)} -> {getattr(tgt, 'value', tgt)}"
        )


class _JsonModel:
    """@brief JSON-serializable model base providing only to_dict/to_json/from_json."""

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, text: str):
        return cls.from_dict(json.loads(text))


@dataclass
class VerificationResult(_JsonModel):
    """@brief Unified verification conclusion; Tool/Handler success does not establish PASS."""

    status: VerificationStatus
    reason: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    manual_review_required: bool = False
    error_code: str | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerificationResult":
        return cls(
            status=_coerce_enum(VerificationStatus, data.get("status"), VerificationStatus.BLOCKED),
            reason=data.get("reason"),
            checks=list(data.get("checks") or []),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            manual_review_required=bool(data.get("manual_review_required", False)),
            error_code=data.get("error_code"),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class RecoveryDecision(_JsonModel):
    """@brief Structured recovery decision; the engine is implemented in a later phase."""

    decision: str
    reason: str = ""
    retry_count: int = 0
    max_retries: int | None = None
    fallback_backend: str | None = None
    error_kind: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decision not in RECOVERY_ACTIONS:
            raise ValueError(
                f"Geçersiz kurtarma kararı {self.decision!r}; izin verilen değerler: {sorted(RECOVERY_ACTIONS)}"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoveryDecision":
        return cls(
            decision=str(data.get("decision") or "block"),
            reason=str(data.get("reason") or ""),
            retry_count=int(data.get("retry_count") or 0),
            max_retries=data.get("max_retries"),
            fallback_backend=data.get("fallback_backend"),
            error_kind=data.get("error_kind"),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class ExecutionResult(_JsonModel):
    """@brief Single-step execution result.

    success describes the Tool/Handler layer, not final task success. Capabilities
    requiring Review must receive a VerificationResult before COMPLETED.
    """

    success: bool = False
    message: str = ""
    outputs: list[Any] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    error_kind: str | None = None
    retryable: bool = False
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionResult":
        return cls(
            success=bool(data.get("success", False)),
            message=str(data.get("message") or ""),
            outputs=list(data.get("outputs") or []),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            error_code=data.get("error_code"),
            error_kind=data.get("error_kind"),
            retryable=bool(data.get("retryable", False)),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class StepRecord(_JsonModel):
    """@brief Execution Step record shared by Worker/MCP/CLI."""

    step_id: str
    tool_name: str = ""
    capability_id: str | None = None
    backend: str | None = None
    parent_step_id: str | None = None
    status: StepStatus = StepStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    arguments_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
    retry_count: int = 0
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    verification: VerificationResult | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("StepRecord.step_id boş olamaz")

    def transition(self, target: StepStatus | str) -> "StepRecord":
        """@brief Validate and update Step state, raising InvalidStateTransition on invalid transitions."""
        ensure_step_transition(self.status, target)
        self.status = _coerce_enum(StepStatus, target, self.status)
        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StepRecord":
        verification = data.get("verification")
        return cls(
            step_id=str(data.get("step_id") or ""),
            tool_name=str(data.get("tool_name") or ""),
            capability_id=data.get("capability_id"),
            backend=data.get("backend"),
            parent_step_id=data.get("parent_step_id"),
            status=_coerce_enum(StepStatus, data.get("status"), StepStatus.PENDING),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_ms=data.get("duration_ms"),
            arguments_summary=dict(data.get("arguments_summary") or {}),
            result_summary=dict(data.get("result_summary") or {}),
            error_code=data.get("error_code"),
            retryable=bool(data.get("retryable", False)),
            retry_count=int(data.get("retry_count") or 0),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            verification=VerificationResult.from_dict(verification) if isinstance(verification, Mapping) else None,
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class RunContext(_JsonModel):
    """@brief Unified Run context decoupled from CAD Studio Queue Job."""

    run_id: str
    goal: str = ""
    trace_id: str | None = None
    status: RunStatus = RunStatus.CREATED
    started_at: str | None = None
    finished_at: str | None = None
    current_step: str | None = None
    steps: list[StepRecord] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("RunContext.run_id boş olamaz")
        if not self.trace_id:
            self.trace_id = self.run_id

    def transition(self, target: RunStatus | str) -> "RunContext":
        """@brief Validate and update Run state, raising InvalidStateTransition on invalid transitions."""
        ensure_run_transition(self.status, target)
        self.status = _coerce_enum(RunStatus, target, self.status)
        return self

    def step(self, step_id: str) -> StepRecord | None:
        """@brief Find a recorded Step by step_id."""
        for item in self.steps:
            if item.step_id == step_id:
                return item
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunContext":
        raw_steps = data.get("steps") or []
        steps = [
            StepRecord.from_dict(item) if isinstance(item, Mapping) else StepRecord(step_id="")
            for item in raw_steps
        ]
        return cls(
            run_id=str(data.get("run_id") or ""),
            goal=str(data.get("goal") or ""),
            trace_id=data.get("trace_id") or data.get("run_id"),
            status=_coerce_enum(RunStatus, data.get("status"), RunStatus.CREATED),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            current_step=data.get("current_step"),
            steps=steps,
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            errors=list(data.get("errors") or []),
            retry_count=int(data.get("retry_count") or 0),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


__all__ = [
    "InvalidStateTransition",
    "RECOVERY_ACTIONS",
    "RunContext",
    "RunStatus",
    "SCHEMA_VERSION",
    "StepRecord",
    "StepStatus",
    "ExecutionResult",
    "RecoveryDecision",
    "VerificationResult",
    "VerificationStatus",
    "can_transition_run",
    "can_transition_step",
    "ensure_run_transition",
    "ensure_step_transition",
    "now_iso",
]
