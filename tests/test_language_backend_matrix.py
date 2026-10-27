"""CAD Studio language-backend matrix and deterministic routing tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capabilities import (  # noqa: E402
    backend_route_snapshot,
    load_capabilities,
    resolve_operation_backend,
)


def test_backend_matrix_is_valid_and_covers_multiple_languages() -> None:
    """@brief The registry must include Python, C#, C++, and headless open-format routes."""
    snapshot = backend_route_snapshot(load_capabilities())

    assert snapshot["backend_count"] >= 10
    assert snapshot["route_count"] >= 11
    assert {"Python", "C#", "C++", "SWBasic/VBA"} <= set(snapshot["languages"])
    assert "fillet_hold_lines_exact" in snapshot["operation_ids"]
    assert "solidworks_addin_ui_events" in snapshot["operation_ids"]


def test_addin_ui_route_prefers_in_process_csharp_host() -> None:
    """@brief Prefer managed in-process Add-ins for long-lived UI/event lifecycles."""
    result = resolve_operation_backend(
        "solidworks_addin_ui_events",
        available_backends=["solidworks-csharp-addin", "solidworks-native-cpp"],
    )

    assert result["status"] == "ready"
    assert result["backend"] == "solidworks-csharp-addin"
    assert result["semantics"] == "exact_managed_addin"


def test_pointer_array_route_prefers_automation_equivalent_for_normal_workflow() -> None:
    """@brief Prefer non-I methods for ordinary tasks; avoid unjustified high-risk C++ escalation."""
    result = resolve_operation_backend(
        "solidworks_pointer_array_api",
        available_backends=["solidworks-com-pywin32", "solidworks-native-cpp"],
    )

    assert result["status"] == "ready"
    assert result["backend"] == "solidworks-com-pywin32"
    assert result["semantics"] == "automation_equivalent"


def test_pointer_array_route_uses_native_cpp_for_exact_i_method_semantics() -> None:
    """@brief Raw-pointer interface requirements must bypass Python and C# PIA."""
    result = resolve_operation_backend(
        "solidworks_pointer_array_api",
        available_backends=["solidworks-com-pywin32", "solidworks-csharp-pia", "solidworks-native-cpp"],
        exact_api=True,
    )

    assert result["status"] == "ready"
    assert result["backend"] == "solidworks-native-cpp"
    assert result["semantics"] == "exact_native"
    assert [item["accepted"] for item in result["considered"]] == [False, False, True]


def test_known_hold_line_host_revision_is_blocked_before_backend_selection() -> None:
    """@brief Language switching cannot disguise a known host failure as executable."""
    result = resolve_operation_backend(
        "fillet_hold_lines_exact",
        available_backends=["solidworks-native-cpp"],
        solidworks_revision="34.1.1",
    )

    assert result["status"] == "blocked"
    assert result["error_code"] == "KNOWN_HOST_REVISION_BLOCKER"
    assert "solidworks-swbasic" in result["diagnostic_backends"]
    assert "solidworks-csharp-pia" in result["diagnostic_backends"]


def test_language_switch_cannot_replace_missing_license_or_addin() -> None:
    """@brief Missing Routing add-ins/licenses must remain blocked."""
    result = resolve_operation_backend(
        "solidworks_routing_native_authoring",
        available_backends=["solidworks-com-pywin32", "solidworks-csharp-pia"],
    )

    assert result["status"] == "blocked"
    assert result["error_code"] == "MISSING_RUNTIME_REQUIREMENT"
    assert result["missing_requirements"] == ["SolidWorks Routing add-in", "Valid license"]


def test_missing_api_data_has_no_fake_language_fallback() -> None:
    """@brief Missing exact API bounds cannot be fabricated through C# or C++."""
    result = resolve_operation_backend("drawing_exact_text_bounds")

    assert result["status"] == "blocked"
    assert result["error_code"] == "NO_LANGUAGE_SUBSTITUTION"
    assert "changing languages cannot" in result["reason"]


def test_router_does_not_assume_catalog_backends_are_installed() -> None:
    """@brief Catalog candidates are not available without local probe evidence."""
    result = resolve_operation_backend("solidworks_standard_automation")

    assert result["status"] == "unavailable"
    assert result["error_code"] == "NO_COMPATIBLE_BACKEND_AVAILABLE"
    assert all(item["reason"] == "Runtime kullanılamıyor" for item in result["considered"])


def test_invalid_backend_reference_is_rejected(tmp_path: Path) -> None:
    """@brief Registry validation rejects misspelled backend routes."""
    payload = json.loads((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    payload["operation_routes"][0]["candidates"][0]["backend"] = "missing-backend"
    manifest = tmp_path / "capabilities.yaml"
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="bilinmeyen backend"):
        load_capabilities(manifest)
