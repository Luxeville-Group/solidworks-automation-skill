"""
Real SolidWorks sketch-selection regression.

Purpose:
1. Create a part and sketch a rectangular base.
2. Explicitly clear the selection set, confirm count 0, then call `extrude_boss()`.
3. Sketch a circular hole, explicitly clear selection, then call `extrude_cut()`.
4. Save SLDPRT, export STEP, and generate multiview previews through `sw_review.run_review()`.

Requires Windows + SolidWorks + pywin32/comtypes. It is excluded from default
`python -m unittest discover` execution and must run explicitly by a person or CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sw_connect import connect_solidworks, get_com_member, mm, new_document, save_document  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_part import _get_selection_count, extrude_boss, extrude_cut, sketch, sketch_circle, sketch_rectangle  # noqa: E402
from sw_review import run_review  # noqa: E402


def _default_output_dir() -> Path:
    """Return the default output directory."""
    return Path(tempfile.gettempdir()) / "solidworks_skill_regression"


def _feature_name(feature) -> str | None:
    """Read a feature name safely."""
    if feature is None:
        return None
    try:
        return get_com_member(feature, "Name")
    except Exception:
        return None


def run_regression(output_dir: Path, visible: bool = True, wait_seconds: int = 12) -> dict:
    """
    Run real SolidWorks regression.

    Parameters:
        output_dir: directory for SLDPRT, STEP, review reports, and previews.
        visible: whether to display the SolidWorks window.
        wait_seconds: seconds to wait after starting SolidWorks.

    Returns:
        dict: test result summary.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / "sketch_selection_regression.SLDPRT"
    step_path = output_dir / "sketch_selection_regression.step"
    review_dir = output_dir / "review"

    result = {
        "output_dir": str(output_dir),
        "part_path": str(part_path),
        "step_path": str(step_path),
        "steps": [],
    }

    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    result["revision"] = get_com_member(sw, "RevisionNumber")
    try:
        sw.CloseDoc(part_path.name)
    except Exception as exc:
        result["steps"].append({"close_existing_warning": str(exc)})

    model = new_document(sw, "part")
    result["document_title"] = get_com_member(model, "GetTitle")

    with sketch(model, "Front Plane") as base_sketch:
        sketch_rectangle(model, 0, 0, mm(60), mm(36))
    model.ClearSelection2(True)
    base_selection_count = _get_selection_count(model)
    result["steps"].append({
        "name": "after_base_sketch_clear_selection",
        "selection_count": base_selection_count,
        "base_sketch": base_sketch,
    })
    if base_selection_count != 0:
        raise RuntimeError(f"Selection must be empty before base extrusion; actual count {base_selection_count}")

    base_feature = extrude_boss(model, base_sketch, mm(12))
    if base_feature is None:
        raise RuntimeError("base FeatureExtrusion3 returned None")
    result["steps"].append({
        "name": "base_extrude",
        "feature": _feature_name(base_feature),
        "selection_count_after": _get_selection_count(model),
    })

    with sketch(model, "Front Plane") as hole_sketch:
        sketch_circle(model, 0, 0, mm(7))
    model.ClearSelection2(True)
    hole_selection_count = _get_selection_count(model)
    result["steps"].append({
        "name": "after_hole_sketch_clear_selection",
        "selection_count": hole_selection_count,
        "hole_sketch": hole_sketch,
    })
    if hole_selection_count != 0:
        raise RuntimeError(f"Selection must be empty before cut; actual count {hole_selection_count}")

    cut_feature = extrude_cut(model, hole_sketch, 0, direction=True, flip=False)
    if cut_feature is None:
        cut_feature = extrude_cut(model, hole_sketch, 0, direction=True, flip=True)
    if cut_feature is None:
        raise RuntimeError("FeatureCut4 returned None for both flip directions")
    result["steps"].append({
        "name": "hole_cut",
        "feature": _feature_name(cut_feature),
        "selection_count_after": _get_selection_count(model),
    })

    model.ForceRebuild3(False)
    try:
        model.ViewZoomtofit2()
    except Exception:
        pass

    save_ok = save_document(model, str(part_path))
    step_ok = export_to_step(model, str(step_path))
    result["save_ok"] = bool(save_ok)
    result["step_ok"] = bool(step_ok)
    result["part_exists"] = part_path.exists()
    result["part_size"] = part_path.stat().st_size if part_path.exists() else 0
    result["step_exists"] = step_path.exists()
    result["step_size"] = step_path.stat().st_size if step_path.exists() else 0
    if not save_ok or not step_ok:
        raise RuntimeError("save/export failed")

    report, report_path = run_review(
        model,
        str(review_dir),
        basename="sketch_selection_regression",
        expected_outputs=[str(part_path), str(step_path)],
    )
    result["review_report"] = str(report_path)
    result["review_evaluation"] = report.get("evaluation")
    result["review_checks"] = report.get("checks")
    return result


def parse_args() -> argparse.Namespace:
    'Parse command-line arguments.'
    parser = argparse.ArgumentParser(description="Run real SolidWorks sketch-selection regression.")
    parser.add_argument(
        "--output-dir",
        default=str(_default_output_dir()),
        help="Output directory; defaults to the system temporary directory.",
    )
    parser.add_argument("--hidden", action="store_true", help="Attempt to hide the SolidWorks window.")
    parser.add_argument("--wait-seconds", type=int, default=12, help="Seconds to wait after starting SolidWorks.")
    return parser.parse_args()


def main() -> int:
    'CLI entry point.'
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result_path = output_dir / "sketch_selection_regression_result.json"

    try:
        result = run_regression(output_dir, visible=not args.hidden, wait_seconds=args.wait_seconds)
        result["status"] = "ok"
    except Exception as exc:
        result = {
            "status": "failed",
            "output_dir": str(output_dir),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
