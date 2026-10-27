"""OCP advanced-surface allowlist and continuity-evidence regression tests."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.advanced_surface_ocp import (
    collect_curvature_radius_evidence,
    collect_surface_continuity_evidence,
    execute_advanced_surface,
    validate_surface_request,
)


def _common(operation: str, model_id: str) -> dict:
    """Return common advanced-surface request fields."""
    return {
        "schemaVersion": "1.0", "modelId": model_id, "units": "mm",
        "operation": operation, "toleranceMm": 0.01, "outputs": ["brep"],
    }


def _smooth_loft_request() -> dict:
    """Return a coaxial equal-diameter smooth Loft golden sample."""
    return {
        **_common("smooth_loft", "smooth_cylinder"),
        "solid": True, "continuityTarget": "C2", "maxDegree": 8,
        "sections": [
            {"id": "bottom", "type": "circle", "z": 0, "radius": 10},
            {"id": "middle", "type": "circle", "z": 20, "radius": 10},
            {"id": "top", "type": "circle", "z": 40, "radius": 10},
        ],
    }


def _write_brep(shape, path: Path) -> dict:
    """Write a test BREP and return a trusted artifact reference."""
    from OCP.BRepTools import BRepTools

    assert BRepTools.Write_s(shape, str(path))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": digest, "producedThisRun": True}


def _rectangle_face():
    """Create a 20x10 mm planar face."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt

    polygon = BRepBuilderAPI_MakePolygon()
    for point in ((0, 0, 0), (20, 0, 0), (20, 10, 0), (0, 10, 0)):
        polygon.Add(gp_Pnt(*point))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _two_faces(*, orthogonal: bool):
    """Create two coplanar or orthogonal faces sharing one topological edge."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp_Pnt

    p0, p1 = gp_Pnt(0, 0, 0), gp_Pnt(10, 0, 0)
    shared = BRepBuilderAPI_MakeEdge(p0, p1).Edge()

    def face(edges):
        wire = BRepBuilderAPI_MakeWire()
        for edge in edges:
            wire.Add(edge)
        assert wire.IsDone()
        return BRepBuilderAPI_MakeFace(wire.Wire()).Face()

    left = face([
        shared,
        BRepBuilderAPI_MakeEdge(p1, gp_Pnt(10, 10, 0)).Edge(),
        BRepBuilderAPI_MakeEdge(gp_Pnt(10, 10, 0), gp_Pnt(0, 10, 0)).Edge(),
        BRepBuilderAPI_MakeEdge(gp_Pnt(0, 10, 0), p0).Edge(),
    ])
    outer1 = gp_Pnt(10, 0, 10) if orthogonal else gp_Pnt(10, -10, 0)
    outer0 = gp_Pnt(0, 0, 10) if orthogonal else gp_Pnt(0, -10, 0)
    right = face([
        TopoDS.Edge(shared.Reversed()),
        BRepBuilderAPI_MakeEdge(p0, outer0).Edge(),
        BRepBuilderAPI_MakeEdge(outer0, outer1).Edge(),
        BRepBuilderAPI_MakeEdge(outer1, p1).Edge(),
    ])
    compound, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, left)
    builder.Add(compound, right)
    return compound


def test_validate_surface_request_rejects_untrusted_brep_and_long_arc(tmp_path: Path) -> None:
    """Block false-hash inputs and first-version arcs exceeding 180 degrees."""
    pytest.importorskip("OCP")
    source = tmp_path / "face.brep"
    artifact = _write_brep(_rectangle_face(), source)
    bad = {**_common("thicken", "bad_thicken"), "input": {**artifact, "sha256": "0" * 64}, "thicknessMm": 1}
    with pytest.raises(ValueError, match="sha256"):
        validate_surface_request(bad)
    arc = {
        **_common("sweep", "bad_arc"), "profile": {"type": "circle", "radiusMm": 2},
        "path": {"type": "arc_xy", "center": [0, 0, 0], "radiusMm": 20, "startAngleDeg": 0, "sweepAngleDeg": 270},
    }
    with pytest.raises(ValueError, match="180"):
        validate_surface_request(arc)


def test_advanced_surface_json_schema_accepts_smooth_loft() -> None:
    """The public advanced-surface Schema accepts smooth Loft requests."""
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[1] / "apps" / "desktop" / "cad_workbench" / "schemas" / "advanced_surface.schema.json"
    schema = jsonschema.loads(schema_path.read_text(encoding="utf-8")) if hasattr(jsonschema, "loads") else None
    if schema is None:
        import json

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_smooth_loft_request(), schema)


def test_continuity_coplanar_passes_g2_and_orthogonal_fails_g1() -> None:
    """Continuity evidence distinguishes coplanar G2 from a 90-degree corner."""
    pytest.importorskip("OCP")
    coplanar = collect_surface_continuity_evidence(_two_faces(orthogonal=False))
    orthogonal = collect_surface_continuity_evidence(_two_faces(orthogonal=True))
    assert coplanar["allSampledEdgesG1"] is True
    assert coplanar["allSampledEdgesG2"] is True
    assert orthogonal["allSampledEdgesG1"] is False
    assert orthogonal["allSampledEdgesG2"] is False
    assert orthogonal["maximumG1AngleDeg"] == pytest.approx(90.0)


def test_smooth_loft_writes_reopens_and_reports_sampled_continuity(tmp_path: Path) -> None:
    """Smooth Loft must write and reopen an actual solid and report G1/G2 samples."""
    pytest.importorskip("OCP")
    report = execute_advanced_surface(_smooth_loft_request(), tmp_path)
    assert report["status"] == "review_required", report
    assert report["geometryEvidence"]["original"]["topology"]["solids"] == 1
    assert report["geometryEvidence"]["reopened"]["brep"]["valid"] is True
    assert report["continuityEvidence"]["sampleCount"] > 0
    assert report["continuityEvidence"]["target"] == "C2"
    assert report["continuityEvidence"]["targetPassed"] is True
    assert report["manual_review_required"] is True


def test_smooth_loft_rejects_excessive_bulge(tmp_path: Path) -> None:
    """Reject smooth geometry outside the section envelope even when it forms a valid solid."""
    pytest.importorskip("OCP")
    request = _smooth_loft_request()
    request["modelId"] = "bulging_loft"
    request["sections"] = [
        {"id": "base", "type": "circle", "z": 0, "radius": 20},
        {"id": "middle", "type": "ellipse", "z": 30, "center": [2, 0], "majorRadius": 16, "minorRadius": 12, "rotationDeg": 15},
        {"id": "top", "type": "circle", "z": 60, "radius": 10},
    ]
    report = execute_advanced_surface(request, tmp_path)
    assert report["status"] == "failed"
    assert report["error_code"] == "ocp_surface_operation_failed"
    assert "teorik kesit zarfını aşıyor" in report["message"]
    assert report["artifacts"] == []


def test_execute_advanced_surface_blocks_when_ocp_dependency_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A missing OCP runtime is an environment block, not an ordinary geometry failure."""
    import scripts.advanced_surface_ocp as surface_module

    def missing_dependency(_request: dict):
        raise ModuleNotFoundError("No module named 'OCP'")

    monkeypatch.setattr(surface_module, "_smooth_loft", missing_dependency)
    report = surface_module.execute_advanced_surface(_smooth_loft_request(), tmp_path)

    assert report["status"] == "blocked"
    assert report["stage"] == "preflight"
    assert report["error_code"] == "ocp_surface_dependency_missing"
    assert report["geometryProduced"] is False


@pytest.mark.parametrize(
    "path",
    [
        {"type": "line", "start": [0, 0, 0], "end": [0, 0, 40]},
        {"type": "arc_xy", "center": [0, 0, 0], "radiusMm": 30, "startAngleDeg": 0, "sweepAngleDeg": 90},
    ],
)
def test_sweep_line_and_arc_produce_expected_volume(tmp_path: Path, path: dict) -> None:
    """Straight and single-arc Sweeps form actual solids and pass volume-identity checks."""
    pytest.importorskip("OCP")
    request = {**_common("sweep", f"sweep_{path['type']}"), "profile": {"type": "circle", "radiusMm": 2}, "path": path}
    report = execute_advanced_surface(request, tmp_path)
    assert report["status"] == "review_required", report
    assert report["geometryEvidence"]["volumeRelativeError"] <= 1e-4
    assert report["geometryEvidence"]["original"]["topology"]["solids"] == 1


def test_knit_six_box_faces_creates_closed_solid(tmp_path: Path) -> None:
    """Six trusted box faces must Knit into a valid solid without free edges."""
    pytest.importorskip("OCP")
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.TopoDS import TopoDS_Compound

    compound, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(compound)
    explorer = TopExp_Explorer(BRepPrimAPI_MakeBox(20, 10, 5).Shape(), TopAbs_FACE)
    while explorer.More():
        builder.Add(compound, explorer.Current())
        explorer.Next()
    artifact = _write_brep(compound, tmp_path / "box_faces.brep")
    request = {**_common("knit", "knit_box"), "inputs": [artifact], "makeSolid": True}
    report = execute_advanced_surface(request, tmp_path / "out")
    assert report["status"] == "review_required", report
    assert report["geometryEvidence"]["freeEdgeCount"] == 0
    assert report["geometryEvidence"]["multipleEdgeCount"] == 0
    assert report["geometryEvidence"]["original"]["topology"]["solids"] == 1


def test_thicken_planar_face_creates_valid_solid(tmp_path: Path) -> None:
    """A trusted planar face must thicken by simple offset into a reopenable solid."""
    pytest.importorskip("OCP")
    artifact = _write_brep(_rectangle_face(), tmp_path / "plate_face.brep")
    request = {**_common("thicken", "thick_plate"), "input": artifact, "thicknessMm": 2}
    report = execute_advanced_surface(request, tmp_path / "out")
    assert report["status"] == "review_required", report
    assert report["geometryEvidence"]["sourceTopology"]["solids"] == 0
    assert report["geometryEvidence"]["original"]["topology"]["solids"] == 1
    assert report["geometryEvidence"]["reopened"]["brep"]["valid"] is True
    assert report["geometryEvidence"]["curvatureRadiusEvidence"]["curvedSampleCount"] == 0


def test_thicken_rejects_thickness_above_sampled_curvature_gate(tmp_path: Path) -> None:
    """Block thickening beyond half the sampled minimum curvature radius before offsetting."""
    pytest.importorskip("OCP")
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    cylinder = BRepPrimAPI_MakeCylinder(10, 20).Shape()
    explorer = TopExp_Explorer(cylinder, TopAbs_FACE)
    lateral_face = None
    while explorer.More():
        candidate = TopoDS.Face(explorer.Current())
        if BRepAdaptor_Surface(candidate).GetType() == GeomAbs_Cylinder:
            lateral_face = candidate
            break
        explorer.Next()
    assert lateral_face is not None
    curvature = collect_curvature_radius_evidence(lateral_face)
    assert curvature["minimumSampledCurvatureRadiusMm"] == pytest.approx(10.0)
    artifact = _write_brep(lateral_face, tmp_path / "cylinder_face.brep")
    request = {**_common("thicken", "thick_cylinder"), "input": artifact, "thicknessMm": 6}
    report = execute_advanced_surface(request, tmp_path / "out")
    assert report["status"] == "blocked"
    assert report["error_code"] == "ocp_surface_operation_blocked"
    assert "50%" in report["message"]
