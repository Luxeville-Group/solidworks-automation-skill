"""SolidWorks 2026 standard involute spur-gear creation, save, export, and reopen regression."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sw_connect import connect_solidworks, get_com_member, new_document, open_document, save_document  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_gear import SpurGearSpec, create_external_spur_gear  # noqa: E402
from sw_review import collect_geometry_measurements, collect_model_summary, run_review  # noqa: E402


CASE = SpurGearSpec(
    module_mm=2.0,
    teeth=24,
    face_width_mm=10.0,
    pressure_angle_deg=20.0,
    bore_diameter_mm=10.0,
    involute_segments=14,
    tip_arc_segments=6,
    root_arc_segments=7,
)


def _validate_native_geometry(measurements: dict, expected: dict, *, stage: str) -> None:
    """@brief Cross-check bounding box, face width, and bore; reject results supported only by script-declared parameters."""
    envelope = measurements.get("envelope_mm") or {}
    actual_axes = sorted(float(envelope.get(name) or 0.0) for name in ("length", "width", "height"))
    expected_axes = sorted([
        float(expected["outside_diameter"]),
        float(expected["outside_diameter"]),
        float(expected["face_width"]),
    ])
    if any(abs(actual - wanted) > 0.12 for actual, wanted in zip(actual_axes, expected_axes)):
        raise RuntimeError(f"{stage}: bounding box does not match addendum circle/face width, actual={actual_axes}, expected={expected_axes}")

    bore = float(expected["bore_diameter"])
    holes = measurements.get("holes") or []
    if bore > 0.0 and not any(abs(float(item.get("diameter_mm") or 0.0) - bore) <= 0.02 for item in holes):
        raise RuntimeError(f"{stage}: B-Rep readback did not find a {bore} mm diameter bore")


def run_regression(output_dir: Path, *, visible: bool = True, wait_seconds: int = 12) -> dict:
    """@brief Create an m2/z24 standard spur gear and verify native SLDPRT, STEP, previews, and reopened geometry."""
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / "involute_spur_gear_m2_z24.SLDPRT"
    step_path = output_dir / "involute_spur_gear_m2_z24.step"
    review_dir = output_dir / "review"
    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    revision = str(get_com_member(sw, "RevisionNumber") or "")
    try:
        sw.CloseDoc(part_path.name)
    except Exception:
        pass
    for target in (part_path, step_path):
        if target.exists():
            target.unlink()

    model = new_document(sw, "part")
    feature, evidence = create_external_spur_gear(model, CASE)
    if feature is None:
        raise RuntimeError("Gear extrusion feature is empty")
    model.ForceRebuild3(False)
    created_measurements = collect_geometry_measurements(model)
    _validate_native_geometry(created_measurements, evidence["dimensions_mm"], stage="after creation")
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"Unexpected solid count after creation: {len(bodies)}")

    if not save_document(model, str(part_path)):
        raise RuntimeError("Gear SLDPRT save failed")
    if not export_to_step(model, str(step_path)):
        raise RuntimeError("Gear STEP export failed")
    report, report_path = run_review(
        model,
        str(review_dir),
        basename="involute_spur_gear_m2_z24",
        expected_outputs=[str(part_path), str(step_path)],
    )

    title = str(get_com_member(model, "GetTitle") or part_path.name)
    sw.CloseDoc(title)
    reopened = open_document(sw, str(part_path), silent=True, raise_on_error=True)
    reopened_measurements = collect_geometry_measurements(reopened)
    _validate_native_geometry(reopened_measurements, evidence["dimensions_mm"], stage="after reopen")
    reopened_summary = collect_model_summary(reopened)
    if not any(item.get("name") == evidence["feature_name"] for item in reopened_summary.get("features", [])):
        raise RuntimeError("Named gear-extrusion feature missing after reopen")

    return {
        "status": "ok",
        "revision": revision,
        "gear_evidence": evidence,
        "artifacts": {
            "sldprt": {"path": str(part_path), "size_bytes": part_path.stat().st_size},
            "step": {"path": str(step_path), "size_bytes": step_path.stat().st_size},
            "review_report": str(report_path),
        },
        "created_measurements": created_measurements,
        "reopened_measurements": reopened_measurements,
        "reopened_feature_count": reopened_summary.get("feature_count"),
        "review_evaluation": report.get("evaluation"),
    }


def main() -> int:
    '@brief Command-line entry point.'
    parser = argparse.ArgumentParser(description="Run real SolidWorks involute spur-gear regression.")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "solidworks_spur_gear_regression"))
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=12)
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result_path = output_dir / "spur_gear_regression_result.json"
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
