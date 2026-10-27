"""Real SolidWorks weldment/cut-list regression driven by open-source HSS profile data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sw_connect import connect_solidworks, get_com_member, mm, new_document, open_document, save_document  # noqa: E402
from sw_part import sketch, sketch_line  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_weldment import (  # noqa: E402
    create_structural_member,
    create_weldment_profile,
    ensure_cut_list,
    export_cut_list_csv,
    set_cut_list_properties,
    weldment_evidence,
)


def _load_case() -> dict:
    """@brief Read pinned-version open-source profile regression parameters."""
    return json.loads((ROOT / "examples" / "weldment" / "coremark_hss1x1x16ga.json").read_text(encoding="utf-8"))


def _validate_evidence(evidence: dict, *, stage: str) -> None:
    """@brief Reject false weldments lacking structural members, bodies, or cut-list folders."""
    if not evidence.get("has_weldment_feature"):
        raise RuntimeError(f"{stage}: WeldmentFeature not detected")
    if not evidence.get("has_structural_member"):
        raise RuntimeError(f"{stage}: native StructuralMember feature not detected")
    if int(evidence.get("solid_body_count", 0)) < 4:
        raise RuntimeError(f"{stage}: fewer than the four structural-member bodies required for a rectangular frame")
    folders = evidence.get("cut_list_folders") or []
    if not folders or sum(int(item.get("body_count", 0)) for item in folders) < 4:
        raise RuntimeError(f"{stage}: cut list does not cover all structural-member bodies")
    quantities = [
        int(item["properties"]["QUANTITY"]["resolved"])
        for item in folders
        if "QUANTITY" in item.get("properties", {})
    ]
    if sorted(quantities) != [2, 2]:
        raise RuntimeError(f"{stage}: expected two equal-length member groups with quantity two each, actual={quantities}")


def _sketch_rounded_rectangle(model, size: float, radius: float, *, clockwise: bool) -> list:
    """@brief Draw an exact centered closed rounded rectangle with selectable winding direction."""
    half = size / 2.0
    if radius <= 0 or radius >= half:
        raise ValueError("Corner radius must be positive and less than half the square's side")
    low = half - radius
    diagonal = radius / (2.0 ** 0.5)

    def arc(start, end, midpoint):
        return model.SketchManager.Create3PointArc(
            start[0], start[1], 0.0,
            end[0], end[1], 0.0,
            midpoint[0], midpoint[1], 0.0,
        )

    if clockwise:
        return [
            sketch_line(model, -low, half, low, half),
            arc((low, half), (half, low), (low + diagonal, low + diagonal)),
            sketch_line(model, half, low, half, -low),
            arc((half, -low), (low, -half), (low + diagonal, -low - diagonal)),
            sketch_line(model, low, -half, -low, -half),
            arc((-low, -half), (-half, -low), (-low - diagonal, -low - diagonal)),
            sketch_line(model, -half, -low, -half, low),
            arc((-half, low), (-low, half), (-low - diagonal, low + diagonal)),
        ]
    return [
        sketch_line(model, low, half, -low, half),
        arc((-low, half), (-half, low), (-low - diagonal, low + diagonal)),
        sketch_line(model, -half, low, -half, -low),
        arc((-half, -low), (-low, -half), (-low - diagonal, -low - diagonal)),
        sketch_line(model, -low, -half, low, -half),
        arc((low, -half), (half, -low), (low + diagonal, -low - diagonal)),
        sketch_line(model, half, -low, half, low),
        arc((half, low), (low, half), (low + diagonal, low + diagonal)),
    ]


def run_regression(output_dir: Path, *, visible: bool = True, wait_seconds: int = 12) -> dict:
    """@brief Create a custom HSS profile and rectangular welded frame, then verify reopened cut lists."""
    case = _load_case()
    profile_data = case["profile"]
    geometry = case["regressionGeometry"]
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = output_dir / "OpenSource" / "HSS" / "HSS1x1x16ga.sldlfp"
    part_path = output_dir / "hss_rectangular_frame.SLDPRT"
    csv_path = output_dir / "hss_rectangular_frame_cut_list.csv"
    review_dir = output_dir / "review"

    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    revision = str(get_com_member(sw, "RevisionNumber") or "")
    for name in (profile_path.name, part_path.name):
        try:
            sw.CloseDoc(name)
        except Exception:
            pass
    for target in (profile_path, part_path, csv_path):
        if target.exists():
            target.unlink()

    profile_model = new_document(sw, "part")
    outer = mm(float(geometry["outer_mm"]))
    inner = mm(float(geometry["outer_mm"]) - 2.0 * float(geometry["wall_mm"]))
    outer_radius = float(profile_data["corner_radius_outer_in"]) * 0.0254
    inner_radius = float(profile_data["corner_radius_inner_in"]) * 0.0254
    with sketch(profile_model, "Front Plane") as profile_sketch:
        _sketch_rounded_rectangle(profile_model, outer, outer_radius, clockwise=True)
        _sketch_rounded_rectangle(profile_model, inner, inner_radius, clockwise=False)
    profile_evidence = create_weldment_profile(
        profile_model,
        profile_sketch,
        profile_path,
        properties={
            "DESCRIPTION": profile_data["designation"],
            "MATERIAL": profile_data["material"],
            "SOURCE_REPOSITORY": case["source"]["repository"],
            "SOURCE_SKU": profile_data["sku"],
        },
    )
    sw.CloseDoc(str(get_com_member(profile_model, "GetTitle") or profile_path.name))

    model = new_document(sw, "part")
    width = mm(float(geometry["frame_width_mm"]))
    height = mm(float(geometry["frame_height_mm"]))
    with sketch(model, "Front Plane"):
        segments = [
            sketch_line(model, 0.0, 0.0, width, 0.0),
            sketch_line(model, width, 0.0, width, height),
            sketch_line(model, width, height, 0.0, height),
            sketch_line(model, 0.0, height, 0.0, 0.0),
        ]
    member = create_structural_member(
        model,
        profile_path,
        [segments],
        # A standalone single-configuration .sldlfp uses an empty string under official supplied/non-configured profile semantics;
        # retain the configuration name in profile_evidence for later explicit selection of multiconfiguration profiles.
        configuration_name="",
        apply_corner_treatment=True,
    )
    ensure_cut_list(model)
    source_property_evidence = set_cut_list_properties(
        model,
        {
            "PROFILE_DESIGNATION": profile_data["designation"],
            "MATERIAL_SPEC": profile_data["material"],
            "SOURCE_REPOSITORY": case["source"]["repository"],
            "SOURCE_SKU": profile_data["sku"],
        },
    )
    created = weldment_evidence(model)
    _validate_evidence(created, stage="after creation")
    member_name = str(get_com_member(member, "Name") or "")
    if not save_document(model, str(part_path)):
        raise RuntimeError("Weldment SLDPRT save failed")
    csv_output = export_cut_list_csv(created, csv_path)
    if not csv_output.is_file() or csv_output.stat().st_size < 20:
        raise RuntimeError("Cut-list CSV is empty")

    report, report_path = run_review(
        model,
        str(review_dir),
        basename="hss_rectangular_frame",
        # Generic CAD review file-size thresholds do not apply to compact CSV; it was checked separately above.
        expected_outputs=[str(profile_path), str(part_path)],
    )
    sw.CloseDoc(str(get_com_member(model, "GetTitle") or part_path.name))
    reopened = open_document(sw, str(part_path), silent=True, raise_on_error=True)
    reopened_evidence = weldment_evidence(reopened)
    _validate_evidence(reopened_evidence, stage="after reopen")
    if reopened_evidence["solid_body_count"] != created["solid_body_count"]:
        raise RuntimeError("Structural-member body count changed after save-and-reopen")

    return {
        "status": "ok",
        "revision": revision,
        "source": case["source"],
        "profile": {**profile_data, **profile_evidence},
        "member_feature": member_name,
        "source_property_evidence": source_property_evidence,
        "artifacts": {
            "sldprt": {"path": str(part_path), "size_bytes": part_path.stat().st_size},
            "cut_list_csv": {"path": str(csv_path), "size_bytes": csv_path.stat().st_size},
            "review_report": str(report_path),
        },
        "created_evidence": created,
        "reopened_evidence": reopened_evidence,
        "review_evaluation": report.get("evaluation"),
    }


def main() -> int:
    '@brief Command-line entry point.'
    parser = argparse.ArgumentParser(description="Run real SolidWorks weldment cut-list regression.")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "solidworks_weldment_regression"))
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=12)
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result_path = output_dir / "weldment_regression_result.json"
    try:
        result = run_regression(output_dir, visible=not args.hidden, wait_seconds=args.wait_seconds)
    except Exception as exc:
        result = {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
