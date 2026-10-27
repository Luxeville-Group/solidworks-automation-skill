"""@brief Lightweight JSON-serializable Eval models, not tightly coupled to production Queue Schema."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass
class AttemptSpec:
    """@brief One scripted attempt: deterministic handler + reviewer behavior."""

    handler: Callable[[Any], Any]
    reviewer: Callable[[], Any] | None = None
    reviewer_result: Mapping[str, Any] | None = None
    requires_review: bool = True
    policy_blocked: bool = False


@dataclass
class EvalScenario:
    """@brief A reliability-evaluation scenario, preferably derived from golden-workflows.yaml."""

    scenario_id: str
    name: str
    type: str
    workflow_id: str | None
    must_review: bool
    max_retries: int
    max_tool_calls: int
    expected_capabilities: list[str]
    required_artifacts: list[str]
    expected_terminal_status: str
    attempts: list[AttemptSpec] = field(default_factory=list)
    capability_facade: Any = None
    operation_id: str | None = None
    #: benchmark_group: nominal / recovery / fault_injection / guardrail, determined by type.
    category: str = "nominal"


@dataclass
class EvalRecord:
    """@brief Scenario execution facts from ExecutionAssessment / Trace, without guessing."""

    scenario_id: str
    workflow_id: str | None
    scenario_type: str
    handler_success: bool
    handler_called: bool
    verification_status: str | None
    recovery_decisions: list[str]
    attempt_count: int
    tool_call_count: int
    duration_ms: int
    terminal_status: str
    false_completion: bool
    artifacts_present: list[str]
    category: str = "nominal"
    expected_terminal_status: str = "completed"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "workflow_id": self.workflow_id,
            "scenario_type": self.scenario_type,
            "category": self.category,
            "handler_success": self.handler_success,
            "handler_called": self.handler_called,
            "verification_status": self.verification_status,
            "recovery_decisions": list(self.recovery_decisions),
            "attempt_count": self.attempt_count,
            "tool_call_count": self.tool_call_count,
            "duration_ms": self.duration_ms,
            "terminal_status": self.terminal_status,
            "expected_terminal_status": self.expected_terminal_status,
            "false_completion": self.false_completion,
            "artifacts_present": list(self.artifacts_present),
            "notes": list(self.notes),
        }


@dataclass
class EvalReport:
    """@brief Summary report grouped by Nominal / Robustness / Safety / Overall."""

    schema_version: str
    generated_at: str
    workflow_count: int
    scenario_count: int
    target_first_pass_rate: float
    first_pass_target_status: str
    metrics: dict[str, Any]
    scenarios: list[EvalRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "workflow_count": self.workflow_count,
            "scenario_count": self.scenario_count,
            "target_first_pass_rate": self.target_first_pass_rate,
            "first_pass_target_status": self.first_pass_target_status,
            "metrics": self.metrics,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }
