"""@brief Deterministic Fake handler/reviewer/capability factories and exception types.

Exception names match ``core.recovery._EXCEPTION_KIND`` so ``classify_error`` correctly identifies
BACKEND_UNAVAILABLE / CAPABILITY_GAP / USER_ACTION_REQUIRED and other categories.
"""
from __future__ import annotations

from typing import Any, Callable


class SolidWorksConnectionError(RuntimeError):
    """@brief Simulate an unavailable backend, classified as BACKEND_UNAVAILABLE."""


class UnsupportedFeatureError(ValueError):
    """@brief Simulate a capability gap, classified as CAPABILITY_GAP."""


class DependencyInstallDeclined(RuntimeError):
    """@brief Simulate declined installation/authorization, classified as USER_ACTION_REQUIRED."""


class FakeCapabilityFacade:
    """@brief Injectable Capability Facade double."""

    def __init__(self, candidates=None, capabilities=None):
        self.candidates = candidates or []
        self.capabilities = capabilities or {}

    def get_backend_candidates(self, operation_id):
        return list(self.candidates)

    def get_capability(self, capability_id):
        return self.capabilities.get(capability_id)


def success_handler(result: dict[str, Any]) -> Callable[[Any], dict[str, Any]]:
    """@brief Return a handler that always succeeds with the supplied result."""
    def run(job=None):
        return dict(result)
    return run


def fail_handler(exc: BaseException) -> Callable[[Any], Any]:
    """@brief Return a handler that always raises the supplied exception."""
    def run(job=None):
        raise exc
    return run


def pass_reviewer() -> Callable[[], dict[str, Any]]:
    return lambda: {"status": "pass", "checks": [{"id": "ok", "status": "pass"}]}


def warn_reviewer() -> Callable[[], dict[str, Any]]:
    return lambda: {"status": "warning", "checks": [{"id": "warn", "status": "warning"}]}


def fail_reviewer(error_code: str = "E_FAIL") -> Callable[[], dict[str, Any]]:
    return lambda: {
        "status": "fail",
        "error_code": error_code,
        "checks": [{"id": "missing", "status": "fail", "severity": "P0"}],
    }


def blocked_reviewer(reason: str = "Environment dependency missing") -> Callable[[], dict[str, Any]]:
    return lambda: {"status": "blocked", "reason": reason}


def crash_reviewer() -> Callable[[], Any]:
    def boom():
        raise RuntimeError("reviewer crashed")
    return boom


def ok_result(artifacts: list[str]) -> dict[str, Any]:
    """@brief Successful handler result with complete artifacts."""
    return {"message": "ok", "outputs": [{"kind": a, "path": f"out/{a}"} for a in artifacts]}


def incomplete_result() -> dict[str, Any]:
    """@brief Handler success without artifacts, for false-completion scenarios."""
    return {"message": "Handler reported success but artifacts are missing", "outputs": []}


def artifacts_from_result(result: dict[str, Any]) -> list[str]:
    """@brief Extract artifact kinds from handler results."""
    outputs = result.get("outputs") or result.get("artifacts") or []
    if not isinstance(outputs, list):
        return []
    names = []
    for item in outputs:
        if isinstance(item, dict):
            names.append(str(item.get("kind") or item.get("path") or item))
        else:
            names.append(str(item))
    return names
