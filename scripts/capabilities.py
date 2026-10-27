"""@brief Read the authoritative CAD Studio/SolidWorks capability registry and enforce gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "capabilities.yaml"
VALID_LEVELS = {"verified", "pilot", "reference_only", "not_implemented"}
VALID_ROUTE_SEMANTICS = {
    "automation_equivalent",
    "exact_automation",
    "exact_managed_addin",
    "exact_managed_plugin",
    "exact_native",
    "exact_native_addin",
    "open_format",
    "solver_native",
}


def manifest_path(path: str | Path | None = None) -> Path:
    """@brief Return the capability registry path."""
    return Path(path).expanduser().resolve() if path else MANIFEST_PATH


def load_capabilities(path: str | Path | None = None) -> dict[str, Any]:
    """@brief Read JSON-compatible YAML and validate capabilities and language-backend routes."""
    source = manifest_path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("capabilities"), list):
        raise ValueError(f"Capability listesi biçimi geçersiz: {source}")
    for item in payload["capabilities"]:
        if not isinstance(item, dict) or not item.get("id") or item.get("level") not in VALID_LEVELS:
            raise ValueError(f"Capability listesi kaydı geçersiz: {item!r}")
    backends = payload.get("backend_catalog", {})
    routes = payload.get("operation_routes", [])
    if not isinstance(backends, dict) or not all(isinstance(item, dict) for item in backends.values()):
        raise ValueError("backend_catalog bir object mapping olmalıdır")
    if not isinstance(routes, list):
        raise ValueError("operation_routes bir array olmalıdır")
    route_ids: set[str] = set()
    capability_ids = {str(item["id"]) for item in payload["capabilities"]}
    for route in routes:
        if not isinstance(route, dict) or not route.get("id") or route["id"] in route_ids:
            raise ValueError(f"İşlem route ID geçersiz veya yineleniyor: {route!r}")
        route_ids.add(str(route["id"]))
        unknown_capabilities = set(route.get("capability_ids", [])) - capability_ids
        if unknown_capabilities:
            raise ValueError(f"Route {route['id']} bilinmeyen capability referansı içeriyor: {sorted(unknown_capabilities)}")
        candidates = route.get("candidates", [])
        if not isinstance(candidates, list):
            raise ValueError(f"Route {route['id']} candidates alanı dizi olmalı")
        for candidate in candidates:
            backend_id = candidate.get("backend") if isinstance(candidate, dict) else None
            semantics = candidate.get("semantics") if isinstance(candidate, dict) else None
            if backend_id not in backends:
                raise ValueError(f"Route {route['id']} bilinmeyen backend referansı içeriyor: {backend_id!r}")
            if semantics not in VALID_ROUTE_SEMANTICS:
                raise ValueError(f"Route {route['id']} semantik türü geçersiz: {semantics!r}")
            if not isinstance(candidate.get("priority"), int):
                raise ValueError(f"Route {route['id']} önceliği tamsayı olmalı")
        unknown_diagnostics = set(route.get("diagnostic_backends", [])) - set(backends)
        if unknown_diagnostics:
            raise ValueError(f"Route {route['id']} bilinmeyen tanılama backend referansı içeriyor: {sorted(unknown_diagnostics)}")
    return payload


def capability_index(payload: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """@brief Index capability entries by ID."""
    source = payload or load_capabilities()
    return {str(item["id"]): dict(item) for item in source.get("capabilities", [])}


def backend_index(payload: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """@brief Index execution-backend definitions by ID."""
    source = payload or load_capabilities()
    return {str(key): dict(value) for key, value in source.get("backend_catalog", {}).items()}


def operation_route_index(payload: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """@brief Index language-backend routes by atomic-operation ID."""
    source = payload or load_capabilities()
    return {str(item["id"]): dict(item) for item in source.get("operation_routes", [])}


def resolve_operation_backend(
    operation_id: str,
    *,
    available_backends: Iterable[str] | None = None,
    available_requirements: Iterable[str] | None = None,
    solidworks_revision: str | None = None,
    exact_api: bool = False,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """@brief Choose a language backend by semantics, version, dependencies and available runtimes.

    exact_api=False permits preference for official Automation equivalents.
    Skip automation_equivalent candidates only when the caller explicitly
    requires raw I* pointer semantics.
    """
    source = payload or load_capabilities()
    backends = backend_index(source)
    route = operation_route_index(source).get(operation_id)
    if route is None:
        return {
            "status": "blocked",
            "operation_id": operation_id,
            "error_code": "UNKNOWN_OPERATION_ROUTE",
            "reason": "Capability matrix içinde bu atomik işlem rotası yok",
        }

    revision = str(solidworks_revision or "").strip()
    blocked_revisions = route.get("blocked_revisions", {})
    if revision and revision in blocked_revisions:
        return {
            "status": "blocked",
            "operation_id": operation_id,
            "error_code": "KNOWN_HOST_REVISION_BLOCKER",
            "reason": str(blocked_revisions[revision]),
            "solidworks_revision": revision,
            "diagnostic_backends": list(route.get("diagnostic_backends", [])),
            "review_required": True,
        }

    supplied_requirements = {str(item) for item in (available_requirements or [])}
    missing_requirements = [
        str(item) for item in route.get("requires", []) if str(item) not in supplied_requirements
    ]
    if missing_requirements:
        return {
            "status": "blocked",
            "operation_id": operation_id,
            "error_code": "MISSING_RUNTIME_REQUIREMENT",
            "reason": "Programlama dilinden bağımsız çalışma koşulları eksik; dil değiştirmek engeli kaldırmaz",
            "missing_requirements": missing_requirements,
            "review_required": True,
        }

    candidates = sorted(route.get("candidates", []), key=lambda item: item["priority"])
    if not candidates:
        return {
            "status": "blocked",
            "operation_id": operation_id,
            "error_code": "NO_LANGUAGE_SUBSTITUTION",
            "reason": str(route.get("blocked_reason") or "Bu işlem için kullanılabilir execution backend yok"),
            "review_required": bool(route.get("review_required", True)),
        }

    available = {str(item) for item in (available_backends or [])}
    considered: list[dict[str, Any]] = []
    for candidate in candidates:
        backend_id = str(candidate["backend"])
        semantics = str(candidate["semantics"])
        if exact_api and semantics == "automation_equivalent":
            considered.append({
                "backend": backend_id,
                "accepted": False,
                "reason": "Çağıran ham arayüz semantiği gerektiriyor; Automation eşdeğeri kullanılamaz",
            })
            continue
        if backend_id not in available:
            considered.append({"backend": backend_id, "accepted": False, "reason": "Runtime kullanılamıyor"})
            continue
        backend = backends[backend_id]
        considered.append({"backend": backend_id, "accepted": True, "reason": "Öncelik sırasına göre seçildi"})
        return {
            "status": "ready",
            "operation_id": operation_id,
            "backend": backend_id,
            "language": backend.get("language"),
            "runtime": backend.get("runtime"),
            "semantics": semantics,
            "exact_api_requested": exact_api,
            "review_required": bool(route.get("review_required", True)),
            "considered": considered,
            "notes": list(route.get("notes", [])),
        }

    return {
        "status": "unavailable",
        "operation_id": operation_id,
        "error_code": "NO_COMPATIBLE_BACKEND_AVAILABLE",
        "reason": "Bilinen backend seçenekleri kullanılamıyor veya istenen arayüz semantiğini karşılamıyor",
        "exact_api_requested": exact_api,
        "considered": considered,
        "diagnostic_backends": list(route.get("diagnostic_backends", [])),
        "review_required": bool(route.get("review_required", True)),
    }


def backend_route_snapshot(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """@brief Summarize languages, runtimes and operation routes in the skill matrix."""
    source = payload or load_capabilities()
    backends = backend_index(source)
    routes = operation_route_index(source)
    return {
        "schema_version": source.get("backend_schema_version", "1.0"),
        "backend_count": len(backends),
        "route_count": len(routes),
        "languages": sorted({str(item.get("language", "")) for item in backends.values()}),
        "backend_ids": sorted(backends),
        "operation_ids": sorted(routes),
    }


def capability_level(capability_id: str, payload: Mapping[str, Any] | None = None) -> str:
    """@brief Return capability level; treat unknown capabilities as unimplemented."""
    return capability_index(payload).get(capability_id, {}).get("level", "not_implemented")


def unattended_allowed(capability_ids: Iterable[str], payload: Mapping[str, Any] | None = None) -> bool:
    """@brief Determine whether capabilities permit unattended execution."""
    return all(capability_level(capability_id, payload) == "verified" for capability_id in capability_ids)


def capability_snapshot(capability_ids: Iterable[str] | None = None, payload: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """@brief Create a capability snapshot for task evidence."""
    index = capability_index(payload)
    selected = list(capability_ids) if capability_ids is not None else list(index)
    return [dict(index.get(capability_id, {"id": capability_id, "level": "not_implemented"})) for capability_id in selected]
