"""@brief Capability facade over the single authoritative capabilities.yaml registry.

Reuse scripts/capabilities.py indexing, backend resolution and operation routing
through stable interfaces for Execution Core, Worker and MCP. This is not a new
registry. Do not add tool_registry.yaml, runtime_capabilities.yaml or
agent_capabilities.json. This facade performs neither tool search nor planning:
a missing tool does not necessarily mean a missing capability. Return a
structured capability_gap to the parent agent when capability is absent.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

try:
    from .. import capabilities as _capabilities
except ImportError:  # Reuse scripts/capabilities.py when importing the top-level core package.
    import capabilities as _capabilities


def load_capabilities(path: str | None = None) -> dict[str, Any]:
    """@brief Read and validate the authoritative registry using scripts/capabilities.py."""
    return _capabilities.load_capabilities(path)


def get_capability(capability_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """@brief Return a capability by ID, or None when unknown."""
    item = _capabilities.capability_index(payload).get(str(capability_id))
    return dict(item) if item else None


def get_operation_route(operation_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """@brief Return an atomic-operation backend route by ID, or None."""
    item = _capabilities.operation_route_index(payload).get(str(operation_id))
    return dict(item) if item else None


def get_backend_candidates(operation_id: str, payload: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """@brief Return candidate backends for an atomic operation in ascending priority order."""
    route = get_operation_route(operation_id, payload)
    if route is None:
        return []
    candidates = [item for item in (route.get("candidates") or []) if isinstance(item, dict)]
    return sorted(candidates, key=lambda item: int(item.get("priority") or 0))


def resolve_backend(
    operation_id: str,
    *,
    available_backends: Iterable[str] | None = None,
    available_requirements: Iterable[str] | None = None,
    solidworks_revision: str | None = None,
    exact_api: bool = False,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """@brief Select a backend by semantics/version/dependencies/runtime using the existing router."""
    return _capabilities.resolve_operation_backend(
        str(operation_id),
        available_backends=available_backends,
        available_requirements=available_requirements,
        solidworks_revision=solidworks_revision,
        exact_api=exact_api,
        payload=payload,
    )


def requires_review(
    *,
    capability_id: str | None = None,
    operation_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> bool | None:
    """@brief Determine whether review is required; return None when unknown.

    operation_id uses operation_routes.review_required.
    capability_id requires review for every level other than verified.
    """
    if operation_id is not None:
        route = get_operation_route(operation_id, payload)
        return None if route is None else bool(route.get("review_required", True))
    if capability_id is not None:
        item = get_capability(capability_id, payload)
        return None if item is None else item.get("level") != "verified"
    return None


def get_capability_status(capability_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """@brief Return structured capability status; represent unknown capabilities as status: unknown."""
    item = get_capability(capability_id, payload)
    if item is None:
        return {
            "status": "unknown",
            "capability_id": str(capability_id),
            "level": None,
            "review_required": None,
            "unattended_allowed": False,
            "verified_versions": [],
            "allowed_modes": [],
            "backends": [],
            "capability": None,
            "reason": "Capability, capabilities.yaml kaynağında bulunmuyor",
        }
    level = item.get("level", "not_implemented")
    return {
        "status": level,
        "capability_id": str(capability_id),
        "level": level,
        "review_required": level != "verified",
        "unattended_allowed": _capabilities.unattended_allowed([str(capability_id)], payload),
        "verified_versions": list(item.get("verified_versions") or []),
        "allowed_modes": list(item.get("allowed_modes") or []),
        "backends": list(item.get("backends") or []),
        "capability": item,
    }


def capability_gap(
    requested_capability: str,
    reason: str = "",
    *,
    searched_existing_tools: bool = True,
    searched_backends: bool = True,
) -> dict[str, Any]:
    """@brief Return structured CAPABILITY_GAP and return control to the parent agent.

    V2 does not access the network or resolve gaps automatically. The parent
    Codex/Claude agent follows SKILL.md rules for unwrapped APIs to research,
    implement, execute on real CAD and retain verified knowledge.
    """
    return {
        "status": "capability_gap",
        "requested_capability": str(requested_capability),
        "reason": str(reason),
        "searched_existing_tools": bool(searched_existing_tools),
        "searched_backends": bool(searched_backends),
        "recommended_action": "agent_resolution_required",
    }


__all__ = [
    "capability_gap",
    "get_backend_candidates",
    "get_capability",
    "get_capability_status",
    "get_operation_route",
    "load_capabilities",
    "requires_review",
    "resolve_backend",
]
