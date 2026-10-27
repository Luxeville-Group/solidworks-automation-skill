"""Week 4 SolidWorks drawing/BOM real-machine regression.

Requires Windows + SolidWorks + pywin32/comtypes; excluded from normal pytest collection.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sw_connect import create_empty_dispatch_variant, get_com_member, get_sw_version  # noqa: E402
from sw_drawing import (  # noqa: E402
    auto_arrange_drawing_dimensions,
    auto_insert_center_marks,
    create_adaptive_standard_views,
    export_sheet_to_pdf,
    inspect_drawing_structure,
    insert_dimensions,
    first_center_mark,
    plan_standard_view_layout,
    setup_current_sheet_as_a3,
)
from sw_hole_features import create_through_hole  # noqa: E402
from sw_part import auto_dimension_sketch, extrude_boss, sketch_rectangle  # noqa: E402
from sw_review import inspect_bmp_preview, review_drawing_layout, save_review_previews  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


def _require_file(path: Path, label: str) -> dict:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} missing or empty: {path}")
    return {"path": str(path), "size_bytes": path.stat().st_size}


def _sheet_format_candidates() -> list[str]:
    """@brief Return locally available A3/GB drawing-frame candidate paths."""
    roots = [
        Path(r"E:\SolidWroks2026\SOLIDWORKS"),
        Path(r"E:\Solidworks\SOLIDWORKS"),
        Path(r"C:\ProgramData\SOLIDWORKS"),
    ]
    candidates: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            candidates.extend(str(path) for path in root.rglob("*.slddrt") if "a3" in path.name.casefold())
        except OSError:
            continue
    return candidates


def _remove_front_center_marks(drawing, created_views) -> int:
    """@brief Remove automatically generated front-view center marks to establish a verifiable pre-write state."""
    front_record = next(item for item in created_views.get("views", []) if item.get("name") == "*Front")
    front_name = str(front_record.get("actual_name") or "")
    sheet = get_com_member(drawing, "GetCurrentSheet")
    front_view = next(view for view in (get_com_member(sheet, "GetViews") or []) if str(get_com_member(view, "Name")) == front_name)
    get_com_member(drawing, "ActivateView", front_name)
    empty_select_data = create_empty_dispatch_variant()
    removed = 0
    for _ in range(100):
        center_mark = first_center_mark(front_view)
        if center_mark is None:
            break
        selected = bool(get_com_member(center_mark, "Select", False, empty_select_data))
        if not selected:
            annotation = get_com_member(center_mark, "GetAnnotation")
            selected = bool(get_com_member(annotation, "Select3", False, empty_select_data))
        if not selected:
            raise RuntimeError("Cannot select default center marks to establish the write-regression precondition")
        get_com_member(drawing, "EditDelete")
        get_com_member(drawing, "ForceRebuild3", False)
        removed += 1
    if first_center_mark(front_view) is not None:
        raise RuntimeError("Readback remains nonempty after deleting default center marks")
    return removed


def run_regression(output_root: Path, *, version: int | None = None, run_id: str | None = None) -> dict:
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    part_path = output_dir / "W4-001-plate.sldprt"
    drawing_path = output_dir / "W4-001-plate.slddrw"
    pdf_path = output_dir / "W4-001-plate.pdf"
    report_path = output_dir / "W4-001-drawing-report.json"
    visible = os.environ.get("CAD_STUDIO_VISIBLE", "true").lower() not in {"0", "false", "no"}
    session = SolidWorksSession(version=version, visible=visible, wait_seconds=20)
    part_title = None
    drawing_title = None
    try:
        part = session.new_part()
        part_title = str(get_com_member(part, "GetTitle"))
        with __import__("sw_part").sketch(part, "Front Plane") as sketch_name:
            rectangle_segments = sketch_rectangle(part, 0, 0, 0.12, 0.08)
            model_dimensions = auto_dimension_sketch(part, sketch_segments=rectangle_segments)
        feature = extrude_boss(part, sketch_name, 0.012)
        if feature is None:
            raise RuntimeError("Mounting-plate extrusion failed")
        hole_evidence = create_through_hole(part, (0.0, 0.0), 0.008, name="CenterThroughHole")
        if not session.save(part, str(part_path)):
            raise RuntimeError("Mounting-plate save failed")
        # InsertModelAnnotations resolves DisplayDimension from the active model. Before drawing creation,
        # keep the saved part active and explicitly show feature dimensions rather than leaving them only in the sketch tree.
        try:
            get_com_member(part, "ShowFeatureDimensions")
            get_com_member(part, "GraphicsRedraw2")
        except Exception:
            pass
        _require_file(part_path, 'parça')

        drawing = session.new_drawing()
        drawing_title = str(get_com_member(drawing, "GetTitle"))
        sheet_setup = setup_current_sheet_as_a3(drawing, _sheet_format_candidates(), require_gbt=True)
        if sheet_setup.get("status") != "pass":
            raise RuntimeError(f"A3/GB frame setup failed: {sheet_setup}")
        layout = plan_standard_view_layout((0.12, 0.012, 0.08), paper_size="A3")
        created_views = create_adaptive_standard_views(drawing, str(part_path), layout)
        if created_views.get("status") != "pass" or created_views.get("view_count") != 3:
            raise RuntimeError(f"Adaptive A3 three-view creation failed: {created_views}")
        # Some versions expose importable model dimensions reliably only after the initial drawing save persists
        # view references. This saves a new current-run artifact and does not overwrite a previous delivery version.
        if not session.save(drawing, str(drawing_path)):
            raise RuntimeError("Initial drawing save failed")
        default_center_marks_removed = _remove_front_center_marks(drawing, created_views)
        center_marks = auto_insert_center_marks(drawing, [{
            "id": "CM-CENTER-HOLE",
            "view": "Front",
            "count": 1,
            "targets": ["holes"],
        }])
        if center_marks.get("status") != "pass":
            raise RuntimeError(f"Center-mark insertion or entity readback failed: {center_marks}")
        center_mark_requirement = center_marks["requirements"][0]
        if not (
            center_mark_requirement.get("before_count") == 0
            and center_mark_requirement.get("api_returned") is True
            and center_mark_requirement.get("after_count", 0) >= 1
        ):
            raise RuntimeError(f"Center marks lack a required write-evidence chain: {center_mark_requirement}")
        inserted_annotations = insert_dimensions(drawing)
        dimensions_inserted = bool(inserted_annotations)
        try:
            drawing.ForceRebuild3(False)
            drawing.GraphicsRedraw2()
        except Exception:
            pass
        official_arrangement = auto_arrange_drawing_dimensions(drawing, spacing_m=0.01)
        if official_arrangement.get("status") == "blocked":
            raise RuntimeError(f"Official SolidWorks dimension-arrangement interface unavailable: {official_arrangement}")
        structure = inspect_drawing_structure(
            drawing,
            paper_size_hint="A3",
            title_block_box=layout.get("title_block_box"),
        )
        if structure["status"] != "pass" or structure["view_count"] < 1:
            raise RuntimeError(f"Drawing-view review failed: {structure}")
        if not dimensions_inserted or structure.get("dimension_count", 0) < 1:
            raise RuntimeError(
                "Drawing readback found no real dimension entities inserted in this run: "
                f"inserted={dimensions_inserted}, dimension_count={structure.get('dimension_count', 0)}"
            )
        front_center_marks = [
            item for item in structure.get("professional_annotations", {}).get("center_marks", [])
            if item.get("semantic_view") == "front"
        ]
        if not front_center_marks:
            raise RuntimeError("Center marks failed the second drawing-structure readback")
        if not session.save(drawing, str(drawing_path)):
            raise RuntimeError("Drawing save failed")
        _require_file(drawing_path, 'teknik çizim')
        if not export_sheet_to_pdf(drawing, str(pdf_path), sw_app=session.sw):
            raise RuntimeError("Drawing PDF export failed")
        _require_file(pdf_path, "PDF")
        preview_paths = save_review_previews(drawing, output_dir / "previews", basename="drawing", views=("front", "top", "right"))
        previews = [inspect_bmp_preview(path) for path in preview_paths]
        if not all(item["exists"] and not item["likely_blank"] for item in previews):
            raise RuntimeError(f"Drawing preview blank or missing: {previews}")
        layout_review = review_drawing_layout(structure, preview_evidence=previews)
        if layout_review.get("status") == "blocked":
            raise RuntimeError(f"Drawing layout structural review blocked: {layout_review}")
        estimated_count = int(layout_review.get("evidence_summary", {}).get("estimated_dimension_box_count") or 0)
        if estimated_count and layout_review.get("error_code") not in {
            "DRAWING_LAYOUT_ESTIMATED_EVIDENCE_REQUIRES_VISUAL_REVIEW",
            "DRAWING_LAYOUT_ESTIMATED_COLLISION_RISK",
            "DRAWING_LAYOUT_COLLISION_DETECTED",
        }:
            raise RuntimeError(f"Estimated drawing bounds did not retain the human-review gate: {layout_review}")
        result = {
            "status": "ok",
            "run_id": run_id,
            "output_dir": str(output_dir),
            "solidworks": get_sw_version(session.sw),
            "connection": session.connection_info,
            "outputs": {"part": _require_file(part_path, 'parça'), "drawing": _require_file(drawing_path, 'teknik çizim'), "pdf": _require_file(pdf_path, "PDF")},
            "sheetSetup": sheet_setup,
            "viewLayout": layout,
            "createdViews": created_views,
            "drawingEvidence": structure,
            "drawingLayoutReview": layout_review,
            "dimensions_inserted": dimensions_inserted,
            "officialDimensionArrangement": official_arrangement,
            "centerMarks": center_marks,
            "defaultCenterMarksRemoved": default_center_marks_removed,
            "holeEvidence": hole_evidence,
            "modelDimensions": model_dimensions,
            "reviewFindings": structure.get("checks", []),
            "artifactRelations": [{"from": str(part_path), "to": str(drawing_path)}, {"from": str(drawing_path), "to": str(pdf_path)}],
            "previews": previews,
            "manual_review_required": True,
        }
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report"] = _require_file(report_path, 'Rapor')
        return result
    finally:
        if drawing_title:
            session.close(title=drawing_title)
        if part_title:
            session.close(title=part_title)
        session.quit_owned_instance()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Week 4 SolidWorks real-machine drawing regression")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "solidworks_week4_drawing_regression"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--version", type=int, help="SolidWorks year, for example 2026; defaults to the latest registered version.")
    args = parser.parse_args()
    try:
        result = run_regression(
            Path(args.output_dir).expanduser().resolve(),
            version=args.version,
            run_id=args.run_id or None,
        )
    except Exception as exc:
        result = {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
