"""@brief CAD Studio worker health-status records."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .core import now_iso

QUEUE_METADATA_FILES = {"worker_health.json", "provider_verifications.json"}


def health_path_for(queue_dir: Path) -> Path:
    """@brief Return the worker health-status file path."""
    return Path(queue_dir) / "worker_health.json"


def count_jobs(queue_dir: Path) -> dict[str, int]:
    """@brief Count queued jobs by status."""
    counts: dict[str, int] = {}
    for path in Path(queue_dir).glob("*.json"):
        if path.name in QUEUE_METADATA_FILES:
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            counts["unreadable"] = counts.get("unreadable", 0) + 1
            continue
        status = str(job.get("status") or "unknown") if isinstance(job, dict) else "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def health_level(counts: dict[str, int], last_error: str | None = None) -> str:
    """@brief Derive coarse health status from the queue state."""
    if last_error:
        return "error"
    if counts.get("unreadable", 0) > 0 or counts.get("failed", 0) > 0:
        return "warning"
    if counts.get("approval_required", 0) > 0 or counts.get("review_required", 0) > 0:
        return "attention"
    return "healthy"


def write_worker_health(
    queue_dir: Path,
    runner_id: str,
    *,
    processed_count: int = 0,
    recovered_count: int = 0,
    last_error: str | None = None,
) -> dict[str, Any]:
    """@brief Write the worker health heartbeat."""
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    counts = count_jobs(queue_dir)
    health = {
        "schemaVersion": "1.0",
        "worker": "cad-workbench-python-worker",
        "runnerId": runner_id,
        "pid": os.getpid(),
        "status": health_level(counts, last_error),
        "heartbeatAt": now_iso(),
        "processedCount": processed_count,
        "recoveredCount": recovered_count,
        "lastError": last_error,
        "queue": counts,
    }
    health_path_for(queue_dir).write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8")
    return health


def read_worker_health(queue_dir: Path) -> dict[str, Any] | None:
    """@brief Read worker health status, returning None when missing or corrupt."""
    path = health_path_for(queue_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
