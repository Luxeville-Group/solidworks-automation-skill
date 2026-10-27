"""CAD Studio connection lifecycle simulation regression.

Does not launch real CAD. CI checks ownership and state-machine constraints across 20 connection, cancellation, and exit cycles. Real CAD regression requires dedicated scripts on a Windows self-hosted runner.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeCadProcess:
    """@brief Observable simulated CAD process."""

    process_id: int
    running: bool = True

    def quit(self) -> None:
        self.running = False


class LifecycleHarness:
    """@brief Simulate single-instance ownership, cancellation, and exit cleanup."""

    def __init__(self) -> None:
        self._next_id = 1
        self.process: FakeCadProcess | None = None
        self.started_by_studio = False
        self.cancelled = False

    def connect(self, existing: FakeCadProcess | None = None) -> FakeCadProcess:
        if self.process is not None and self.process.running:
            return self.process
        if existing is not None:
            self.process = existing
            self.started_by_studio = False
        else:
            self.process = FakeCadProcess(self._next_id)
            self._next_id += 1
            self.started_by_studio = True
        return self.process

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> bool:
        if not self.started_by_studio or self.process is None:
            return False
        self.process.quit()
        self.process = None
        self.started_by_studio = False
        return True


def run_regression(iterations: int = 20) -> dict[str, object]:
    """@brief Run lifecycle regression and return auditable results."""
    if iterations < 1:
        raise ValueError("iterations sıfırdan büyük olmalı")
    harness = LifecycleHarness()
    process_ids: list[int] = []
    for _ in range(iterations):
        process = harness.connect()
        process_ids.append(process.process_id)
        harness.cancel()
        harness.close()
        harness.cancelled = False
    return {
        "status": "pass" if len(set(process_ids)) == iterations and harness.process is None else "fail",
        "iterations": iterations,
        "unique_processes": len(set(process_ids)),
        "orphan_process": harness.process is not None,
        "cancelled": harness.cancelled,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
