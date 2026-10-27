"""
Real-machine smoke tests for new modeling, measurement, and specification tools in SolidWorks.

This is a **real-machine regression** requiring locally installed and licensed SolidWorks. It is excluded from default pytest
collection (the filename does not start with test_) and must be run explicitly:

    python tests/live_smoke_new_tools.py

All outputs go to tests/output/live_smoke/. User-opened documents are untouched: the script records
the initial document list and closes only documents it creates.

Exit code 0 means every check passed; nonzero means failures, with details printed to stdout.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "tests" / "output" / "live_smoke"

RESULTS = []


def record(name, ok, detail=None):
    """Record one result."""
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if detail and not ok:
        text = json.dumps(detail, ensure_ascii=False, default=str) if not isinstance(detail, str) else detail
        print(f"        {text[:900]}")


def section(title):
    """Print a section title."""
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main():
    """Run real-machine smoke tests."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts import sw_connect, sw_measure, sw_edge_select
    from scripts.sw_part import (
        sketch, sketch_circle, sketch_corner_rectangle, extrude_boss, fillet, chamfer,
    )
    from scripts.design_spec import validate_design_spec, compare_verification
    from scripts.build_from_spec import build_from_spec, expand_hole_patterns

    # ---------------------------------------------------------------- Connection
    section("1. Connection and version")
    preexisting = []
    try:
        sw, _ = sw_connect.connect_solidworks(wait_seconds=10)
        version = sw_connect.get_sw_version(sw)
        record("Connect to SolidWorks", True, version)
        preexisting = [sw_connect.get_com_member(doc, "GetTitle") for doc in (sw_connect.get_com_member(sw, "GetDocuments") or [])]
        record("Record open documents to protect user documents", True, {"preexisting": preexisting})
    except Exception as exc:
        record("Connect to SolidWorks", False, f"{type(exc).__name__}: {exc}")
        return 1

    # -------------------------------------------------- Verify new_document fix
    section("2. P0-1 new_document no longer mistakes an existing document for a new one")
    created_models = []
    try:
        model = sw_connect.new_document(sw, "part")
        created_models.append(model)
        title = sw_connect.get_com_member(model, "GetTitle")
        record(
            "new_document returns an actual new document",
            title not in preexisting,
            {"new_title": title, "preexisting": preexisting},
        )
    except Exception as exc:
        record("new_document creates a part", False, f"{type(exc).__name__}: {exc}")
        return 1

    # ------------------------------------------------------------ Modeling tools
    section("3. Modeling: sketch/extrusion, fillet, chamfer")
    try:
        with sketch(model, "Front Plane") as sketch_ref:
            sketch_corner_rectangle(model, -0.06, -0.04, 0.06, 0.04)
        base_feature = extrude_boss(model, sketch_ref, 0.008)
        record("Create 120x80x8 plate", base_feature is not None,
               {"feature": sw_connect.get_com_member(base_feature, "Name") if base_feature else None})
    except Exception as exc:
        record("Create 120x80x8 plate", False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:600]}")

    # Semantic edge selection
    try:
        descriptors, errors = sw_edge_select.iter_model_edges(model)
        record("Enumerate model edges", len(descriptors) > 0, {"edge_count": len(descriptors), "errors": errors[:3]})

        vertical, rejected = sw_edge_select.filter_edges(descriptors, axis="z")
        record("Filter vertical edges along Z", len(vertical) == 4,
               {"matched": len(vertical), "sample": [item.get("length_mm") for item in vertical[:6]]})

        selection = sw_edge_select.select_edges(model, {"axis": "z", "convex_only": True})
        record("Select convex vertical edges", selection["status"] == "ok",
               {"selected_count": selection.get("selected_count"), "errors": selection.get("errors", [])[:3]})
    except Exception as exc:
        record("Semantic edge selection", False, f"{type(exc).__name__}: {exc}")

    # Fillet
    try:
        selection = sw_edge_select.select_edges(model, {"axis": "z"})
        fillet_feature = fillet(model, 0.004) if selection["status"] == "ok" else None
        model.ClearSelection2(True)
        record("Create R4 vertical-edge fillet", fillet_feature is not None,
               {"selected": selection.get("selected_count"),
                "feature": sw_connect.get_com_member(fillet_feature, "Name") if fillet_feature else None,
                "errors": selection.get("errors", [])[:3]})
    except Exception as exc:
        record("Create R4 vertical-edge fillet", False, f"{type(exc).__name__}: {exc}")

    # Verify chamfers in a separate document: fillets have already turned the four vertical edges into tangent edges,
    # so selecting them again on that model would select fillet-generated edges rather than the originals.
    try:
        chamfer_model = sw_connect.new_document(sw, "part")
        created_models.append(chamfer_model)
        with sketch(chamfer_model, "Front Plane") as chamfer_sketch:
            sketch_corner_rectangle(chamfer_model, 0.0, 0.0, 0.120, 0.080)
        extrude_boss(chamfer_model, chamfer_sketch, 0.008)
        selection = sw_edge_select.select_edges(chamfer_model, {"axis": "z"})
        chamfer_feature = chamfer(chamfer_model, 0.002, 45.0) if selection["status"] == "ok" else None
        chamfer_model.ClearSelection2(True)
        record("Create C2 vertical-edge chamfer in separate document", chamfer_feature is not None,
               {"selected": selection.get("selected_count"),
                "feature": sw_connect.get_com_member(chamfer_feature, "Name") if chamfer_feature else None})
    except Exception as exc:
        record("Create C2 vertical-edge chamfer in separate document", False, f"{type(exc).__name__}: {exc}")

    # Measurement
    section("4. Measurement: bounding box and mass properties")
    try:
        box = sw_measure.collect_bounding_box(model)
        size = box.get("size_mm")
        ok = bool(size) and abs(size[0] - 120.0) < 0.5 and abs(size[1] - 80.0) < 0.5 and abs(size[2] - 8.0) < 0.5
        record("Bounding box = 120 x 80 x 8 mm", ok, {"size_mm": size, "errors": box.get("errors")})
    except Exception as exc:
        record("Bounding box", False, f"{type(exc).__name__}: {exc}")

    try:
        mass = sw_measure.collect_mass_properties(model)
        volume = mass.get("volume_mm3")
        expected_volume = 120.0 * 80.0 * 8.0
        # Fillets remove a little volume; allow a 2% deviation.
        ok = bool(volume) and abs(volume - expected_volume) / expected_volume < 0.02
        record("Volume near 76800 mm3", ok,
               {"volume_mm3": volume, "expected": expected_volume, "material_assigned": mass.get("material_assigned"),
                "warnings": mass.get("warnings"), "errors": mass.get("errors")})
    except Exception as exc:
        record("Mass properties", False, f"{type(exc).__name__}: {exc}")

    # Real-machine density tests found IMassProperty.Density read-only and SetOverrideMass unavailable;
    # the only working route is the swMaterialPropertyDensity(7) preference.
    try:
        steel = sw_measure.collect_mass_properties(model, density_kg_m3=7850.0)
        volume_mm3 = steel.get("volume_mm3") or 0.0
        expected_mass_g = volume_mm3 * 7850.0 / 1_000_000.0
        actual_mass_g = steel.get("mass_g") or 0.0
        ok = (
            steel.get("density_overridden") is True
            and not steel.get("errors")
            and abs(actual_mass_g - expected_mass_g) / max(expected_mass_g, 1e-9) < 0.02
        )
        record("Correct mass after setting density to 7850 kg/m3", ok,
               {"mass_g": actual_mass_g, "expected_mass_g": round(expected_mass_g, 3),
                "implied_density": steel.get("implied_density_kg_m3"),
                "previous_density": steel.get("previous_density_kg_m3"),
                "errors": steel.get("errors")})
    except Exception as exc:
        record("Correct mass after setting density", False, f"{type(exc).__name__}: {exc}")

    # --------------------------------------------------------- Design-spec construction
    section("5. Specification-driven modeling: design_spec_build core")
    spec = {
        "schema_version": "1.0",
        "part_name": "live_smoke_bracket",
        "units": "mm",
        "base": {"type": "rect_plate", "width": 100, "height": 60, "thickness": 6},
        # Drawing-based locations: origin at plate lower left; coordinates are hole-center distances from left/bottom edges.
        "holes": [
            {"id": "H1", "type": "through", "diameter": 6.6, "position": [10, 10]},
            {"id": "H2", "type": "through", "diameter": 6.6, "position": [90, 10]},
            {"id": "H3", "type": "through", "diameter": 6.6, "position": [10, 50]},
            {"id": "H4", "type": "through", "diameter": 6.6, "position": [90, 50]},
        ],
        "verify": {"envelope_mm": [100, 60, 6], "hole_count": 4, "tolerance_mm": 0.5},
    }
    validation = validate_design_spec(spec)
    record("Specification validation passed", validation["status"] == "ok", validation.get("errors"))

    if validation["status"] == "ok":
        try:
            spec_model = sw_connect.new_document(sw, "part")
            created_models.append(spec_model)
            audit = build_from_spec(spec_model, validation["normalized"], apply_fillets=True, verify_geometry=True)
            record("Build part from specification", audit["status"] in ("ok", "warn"),
                   {"status": audit["status"], "errors": audit.get("errors", [])[:5],
                    "warnings": audit.get("warnings", [])[:5]})
            record("Specification readback: all four holes created", audit.get("hole_count_created") == 4,
                   {"created": audit.get("hole_count_created"), "requested": audit.get("hole_count_requested")})

            verification = audit.get("verification", {})
            record("Specification verification: bounding box and hole count match", verification.get("status") == "pass",
                   {"status": verification.get("status"), "failed": verification.get("failed"),
                    "checks": verification.get("checks")})

            saved = sw_connect.save_document(spec_model, str(OUTPUT_DIR / "live_smoke_bracket.sldprt"))
            record("Save specification part", bool(saved), str(OUTPUT_DIR / "live_smoke_bracket.sldprt"))
        except Exception as exc:
            record("Build part from specification", False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:800]}")

    # Hole-pattern expansion: pure calculation
    try:
        holes = expand_hole_patterns([
            {"id": "B", "type": "through", "diameter_mm": 5.0, "position_mm": [0.0, 0.0, 0.0],
             "pattern": {"type": "circular", "count": 6, "radius": 30.0, "start_angle": 0.0}},
        ])
        record("Expand circular pattern to six holes", len(holes) == 6,
               {"count": len(holes), "positions": [hole["position_mm"][:2] for hole in holes[:3]]})
    except Exception as exc:
        record("Hole-pattern expansion", False, f"{type(exc).__name__}: {exc}")

    # --------------------------------------------------------------- Cleanup
    section("6. Cleanup: close only documents created by this script")
    closed = []
    for doc in created_models:
        try:
            title = sw_connect.get_com_member(doc, "GetTitle")
            sw.CloseDoc(title)
            closed.append(title)
        except Exception as exc:
            closed.append(f"<failed: {exc}>")
    try:
        remaining = [sw_connect.get_com_member(doc, "GetTitle") for doc in (sw_connect.get_com_member(sw, "GetDocuments") or [])]
    except Exception:
        remaining = None
    record("Close script-created documents", True, {"closed": closed, "remaining": remaining})
    record("Preexisting user documents unaffected",
           remaining is None or all(title in remaining for title in preexisting),
           {"preexisting": preexisting, "remaining": remaining})

    # --------------------------------------------------------------- Results
    section('Özet')
    failed = [item for item in RESULTS if not item["ok"]]
    print(f"Total {len(RESULTS)} checks; passed {len(RESULTS) - len(failed)}, failed {len(failed)}")
    report_path = OUTPUT_DIR / "live_smoke_report.json"
    report_path.write_text(
        json.dumps({"results": RESULTS, "failed_count": len(failed)}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Report: {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
