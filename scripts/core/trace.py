"""@brief Execution Trace adapter reusing the queue/events/ JSONL event system.

Extend append-only queue/events/{safe_id}.jsonl with run_id, trace_id, step_id and
parent_step_id. Create no independent trace storage, runs/traces folders or service.
Trace owns execution history; Artifact Ledger owns final-deliverable facts.
Keep those responsibilities separate. All added fields are optional, preserving
consumers of type/at/message/data.

Append each event in one line, in append mode, then flush. Never record API keys,
complete prompts or secrets; redact sensitive keys defensively. Callers supply
path summaries; this module does not expose complete private paths.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .state import now_iso

#: Normalized Trace vocabulary for documentation/test baselines; emit does not enforce it.
TRACE_EVENT_TYPES = frozenset(
    {
        "run.created",
        "run.started",
        "step.started",
        "tool.called",
        "tool.succeeded",
        "tool.failed",
        "verification.started",
        "verification.passed",
        "verification.failed",
        "recovery.retry",
        "recovery.backend_fallback",
        "capability.gap",
        "run.blocked",
        "run.failed",
        "run.completed",
    }
)

#: Same safe-ID rules as queue_worker.event_path_for; preserve event filenames.
_SAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]")
_SENSITIVE_KEY = re.compile(
    r"prompt|api[_-]?key|token|secret|password|credential|authorization", re.IGNORECASE
)

#: Optional additive event fields; all are backward compatible.
_OPTIONAL_FIELDS = (
    "run_id",
    "trace_id",
    "step_id",
    "parent_step_id",
    "capability_id",
    "backend",
    "duration_ms",
    "error_code",
    "retry_count",
    "verification_status",
)


def sanitize_id(value: Any) -> str:
    """@brief Return a safe ID suitable for event filenames."""
    safe = _SAFE_ID_CHARS.sub("", str(value or ""))
    return safe[:96] if safe else "unknown"


def events_dir(queue_dir: str | Path) -> Path:
    """@brief Return <queue_dir>/events, creating it if needed."""
    directory = Path(queue_dir) / "events"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def trace_path_for(queue_dir: str | Path, key: Any) -> Path:
    """@brief Return the event-file path for a Run/Job."""
    return events_dir(queue_dir) / f"{sanitize_id(key)}.jsonl"


def redact(value: Any, key: str = "") -> Any:
    """@brief Recursively replace values of sensitive keys with [redacted]."""
    if _SENSITIVE_KEY.search(str(key)):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    return value


def _event_key(event: Mapping[str, Any], key: str | None = None) -> str:
    """@brief Resolve event destination: explicit key before run_id/trace_id/jobId."""
    if key:
        return str(key)
    for field in ("run_id", "trace_id", "jobId", "job_id"):
        if event.get(field):
            return str(event[field])
    return "unknown"


def append_event(queue_dir: str | Path, event: Mapping[str, Any], *, key: str | None = None) -> Path:
    """@brief Append one JSON event to events/{safe_id}.jsonl and return its path."""
    path = trace_path_for(queue_dir, _event_key(event, key))
    line = json.dumps(redact(event), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
    return path


def emit(
    queue_dir: str | Path,
    event_type: str,
    *,
    key: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    step_id: str | None = None,
    parent_step_id: str | None = None,
    capability_id: str | None = None,
    backend: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    retry_count: int | None = None,
    verification_status: str | None = None,
    message: str = "",
    data: Mapping[str, Any] | None = None,
    at: str | None = None,
) -> Path:
    """@brief Construct and append a Trace event using the additive schema."""
    event: dict[str, Any] = {
        "type": str(event_type),
        "at": at or now_iso(),
        "message": str(message),
    }
    optional = {
        "run_id": run_id,
        "trace_id": trace_id,
        "step_id": step_id,
        "parent_step_id": parent_step_id,
        "capability_id": capability_id,
        "backend": backend,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "retry_count": retry_count,
        "verification_status": verification_status,
    }
    for name, value in optional.items():
        if value is not None:
            event[name] = value
    if data is not None:
        event["data"] = data
    return append_event(queue_dir, event, key=key)


def read_events(queue_dir: str | Path, key: Any) -> list[dict[str, Any]]:
    """@brief Read old/new-schema events, skipping corrupt lines."""
    path = trace_path_for(queue_dir, key)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


__all__ = [
    "TRACE_EVENT_TYPES",
    "append_event",
    "emit",
    "events_dir",
    "read_events",
    "redact",
    "sanitize_id",
    "trace_path_for",
]
