"""Regression checks for advanced-surface and mold neutral-plan gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.advanced_geometry import geometry_preflight, validate_geometry_plan, write_preflight_report


def _plan() -> dict:
    """Return a golden plan covering surface continuity and core mold fields."""
    return {
        "schemaVersion": "1.0",
        "planId": "housing_tool",
        "units": "mm",
        "entities": [
            {"id": "profileA", "type": "profile", "source": "section:A"},
            {"id": "profileB", "type": "profile", "source": "section:B"},
            {"id": "guidePath", "type": "path", "source": "curve:guide"},
            {"id": "surfaceA", "type": "surface", "source": "brep:surfaceA"},
            {"id": "surfaceB", "type": "surface", "source": "brep:surfaceB"},
            {"id": "edgeA", "type": "edge", "source": "signature:edgeA"},
            {"id": "pullDir", "type": "direction", "source": "vector:0,0,1"},
            {"id": "productSolid", "type": "solid", "source": "brep:product"},
            {"id": "blockA", "type": "solid", "source": "brep:blockA"},
            {"id": "blockB", "type": "solid", "source": "brep:blockB"},
        ],
        "operations": [
            {"id": "loftMain", "type": "loft", "profiles": ["profileA", "profileB"], "continuity": "G2", "output": "loftSurface"},
            {"id": "sweepRib", "type": "sweep", "profiles": ["profileA"], "path": "guidePath", "checkSelfIntersection": True, "output": "sweepSurface"},
            {"id": "knitShell", "type": "knit", "surfaces": ["surfaceA", "surfaceB"], "toleranceMm": 0.01, "allowOpenShell": False, "output": "knitSurface"},
            {"id": "thickenShell", "type": "thicken", "surface": "knitSurface", "direction": "pullDir", "thicknessMm": 2.0, "output": "thickSolid"},
            {"id": "checkJoin", "type": "continuity_check", "edges": ["edgeA"], "continuity": "G2", "toleranceMm": 0.005},
            {"id": "draftFaces", "type": "draft", "faces": ["surfaceA"], "direction": "pullDir", "angleDeg": 2.0},
            {"id": "partingPlan", "type": "parting", "solid": "productSolid", "direction": "pullDir", "partingEdges": ["edgeA"]},
            {"id": "splitTool", "type": "core_cavity", "solid": "productSolid", "partingSurfaces": ["surfaceA"], "moldBlocks": ["blockA", "blockB"], "shrinkagePercent": 0.6, "output": "toolingSolid"},
        ],
    }


def test_validate_geometry_plan_covers_surface_continuity_and_mold_requirements() -> None:
    """Complete references, continuity, draft, and core/cavity parameters pass structural validation."""
    assert validate_geometry_plan(_plan())["planId"] == "housing_tool"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda plan: plan["operations"][0].pop("continuity"), "continuity"),
        (lambda plan: plan["operations"][1].update({"path": "missingPath"}), "missingPath"),
        (lambda plan: plan["operations"][2].update({"toleranceMm": 2.0}), "toleranceMm"),
        (lambda plan: plan["operations"][5].update({"angleDeg": 45}), "angleDeg"),
        (lambda plan: plan["operations"][7].update({"moldBlocks": ["blockA"]}), "moldBlocks"),
    ],
)
def test_golden_failure_evidence_blocks_incomplete_or_unsafe_plans(change, message: str) -> None:
    """Reject missing continuity, bad references, excessive tolerances/draft, and incomplete mold bases."""
    plan = _plan()
    change(plan)
    with pytest.raises(ValueError, match=message):
        validate_geometry_plan(plan)


def test_preflight_never_claims_geometry_was_produced() -> None:
    """Even when OCP is found, an unverified executor remains pilot and produces no geometry."""
    report = geometry_preflight(_plan())
    assert report["status"] in {"pilot", "blocked"}
    assert report["geometryProduced"] is False
    assert report["artifacts"] == []
    assert report["error_code"] in {"advanced_geometry_backend_unverified", "advanced_geometry_runtime_missing"}


def test_invalid_plan_returns_stable_blocked_evidence() -> None:
    """Invalid plans return stable stages/error codes rather than exceptional completion states."""
    plan = _plan()
    plan["operations"][0]["continuity"] = "G3"
    report = geometry_preflight(plan)
    assert report["status"] == "blocked"
    assert report["stage"] == "validate"
    assert report["error_code"] == "advanced_geometry_invalid_plan"
    assert report["geometryProduced"] is False


def test_preflight_report_is_versioned_and_hashed(tmp_path: Path) -> None:
    """Preflight reports must preserve old artifacts and record hashes."""
    first = write_preflight_report(_plan(), tmp_path / "geometry.json")
    second = write_preflight_report(_plan(), tmp_path / "geometry.json")
    assert Path(first["artifacts"][0]["path"]).name == "geometry.json"
    assert Path(second["artifacts"][0]["path"]).name == "geometry_v2.json"
    assert first["artifacts"][0]["sha256"]


def test_advanced_geometry_json_schema_is_valid() -> None:
    """The public Schema must conform to Draft 2020-12."""
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[1] / "apps" / "desktop" / "cad_workbench" / "schemas" / "advanced_geometry.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_plan(), schema)
