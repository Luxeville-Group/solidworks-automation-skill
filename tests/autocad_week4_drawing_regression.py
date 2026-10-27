"""Week 4 real-machine regression for AutoCAD drawings, dimensions, DXF, and native previews.

Requires Windows + AutoCAD 2024 + pywin32; excluded from normal pytest collection.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
ACAD_SCRIPTS = ROOT / "subskills" / "autocad-automation" / "scripts"
sys.path.insert(0, str(ACAD_SCRIPTS))

from acad_headless import inspect_dxf, render_dxf  # noqa: E402
from acad_review import review_active  # noqa: E402
from acad_session import AutoCADSession  # noqa: E402
from acad_preview import convert_bmp_to_png  # noqa: E402


def _default_output_dir() -> Path:
    """@brief Return the default Week 4 AutoCAD regression directory."""
    return Path(tempfile.gettempdir()) / "autocad_week4_drawing_regression"


def _require_file(path: Path, label: str) -> dict:
    """@brief Require a nonempty file and return its evidence."""
    if not path.is_file():
        raise RuntimeError(f"{label} not generated: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError(f"{label} is empty: {path}")
    return {"path": str(path), "size_bytes": size}


def _draw_frame(session: AutoCADSession) -> None:
    """@brief Draw an A3 landscape neutral GB/T-style frame and title block."""
    session.create_layer("FRAME", color=7)
    session.create_layer("OUTLINE", color=7)
    session.create_layer("CENTER", color=1, linetype="CENTER")
    session.create_layer("HOLE", color=1)
    session.create_layer("DIM", color=2)
    session.create_layer("TEXT", color=3)

    # A3 landscape: 420 x 297 mm; 25 mm left binding margin, 5 mm other margins.
    session.add_rectangle((0, 0), 420, 297, layer="FRAME")
    session.add_rectangle((25, 5), 390, 287, layer="FRAME")
    # Lower-right title block: 180 wide, 35 high, divided with real line segments.
    x0, y0, width, height = 235, 5, 180, 35
    session.add_rectangle((x0, y0), width, height, layer="FRAME")
    for x in (x0 + 60, x0 + 120):
        session.add_line((x, y0), (x, y0 + height), layer="FRAME")
    session.add_line((x0, y0 + 17.5), (x0 + width, y0 + 17.5), layer="FRAME")
    for text, point in (
        ("CAD STUDIO", (x0 + 5, y0 + 23)),
        ("Drawing No W4-001", (x0 + 65, y0 + 23)),
        ("Name Mounting plate", (x0 + 125, y0 + 23)),
        ("Material Q235B", (x0 + 5, y0 + 7)),
        ("Scale 1:1", (x0 + 65, y0 + 7)),
        ("Units mm", (x0 + 125, y0 + 7)),
    ):
        session.add_text(text, (*point, 0), 3, layer="TEXT")


def _draw_plate(session: AutoCADSession) -> None:
    """@brief Draw mounting-plate geometry, centerlines, holes, and real dimensions."""
    left, bottom, width, height = 70.0, 105.0, 120.0, 80.0
    session.add_rectangle((left, bottom), width, height, layer="OUTLINE")
    hole_radius = 4.5
    hole_margin = 15.0
    hole_points = [
        (left + hole_margin, bottom + hole_margin),
        (left + width - hole_margin, bottom + hole_margin),
        (left + width - hole_margin, bottom + height - hole_margin),
        (left + hole_margin, bottom + height - hole_margin),
    ]
    for x, y in hole_points:
        session.add_circle((x, y, 0), hole_radius, layer="HOLE")
        session.add_line((x - 8, y), (x + 8, y), layer="CENTER")
        session.add_line((x, y - 8), (x, y + 8), layer="CENTER")

    session.add_dim_aligned(
        (left, bottom, 0),
        (left + width, bottom, 0),
        (left + width / 2, bottom - 24, 0),
    )
    session.add_dim_rotated(
        (left, bottom, 0),
        (left, bottom + height, 0),
        (left - 20, bottom + height / 2, 0),
        90,
    )
    session.add_dim_aligned(
        (left, bottom, 0),
        (left + hole_margin, bottom, 0),
        (left + hole_margin / 2, bottom - 7, 0),
    )
    session.add_dim_aligned(
        (*hole_points[0], 0),
        (*hole_points[1], 0),
        ((hole_points[0][0] + hole_points[1][0]) / 2, bottom - 12, 0),
    )
    session.add_dim_rotated(
        (*hole_points[0], 0),
        (*hole_points[3], 0),
        (left - 10, (hole_points[0][1] + hole_points[3][1]) / 2, 0),
        90,
    )
    session.add_dim_diametric(hole_points[0], hole_radius, angle_degrees=35, leader_length=12)
    session.add_text("4x Ø9 through holes, 90 x 50 center spacing, 15 from datum edges", (left, bottom - 28, 0), 3, layer="TEXT")
    session.add_text("Mounting plate 120 x 80 x 12; verify hole positions and dimensions against geometry", (left, bottom + height + 12, 0), 3, layer="TEXT")


def run_regression(output_root: Path, *, run_id: str | None = None) -> dict:
    """@brief Run the AutoCAD Week 4 golden drawing regression."""
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    dwg_path = output_dir / "W4-001-mounting-plate.dwg"
    dxf_path = output_dir / "W4-001-mounting-plate.dxf"
    bmp_path = output_dir / "W4-001-mounting-plate.bmp"
    png_path = output_dir / "W4-001-mounting-plate.png"
    dxf_png_path = output_dir / "W4-001-mounting-plate-headless.png"
    report_path = output_dir / "W4-001-drawing-report.json"

    session = AutoCADSession(create_if_missing=True, visible=True).connect()
    owned_instance = session.started_by_session
    result = None
    created_document = False
    # An instance started by this task owns its default drawing; attach to user instances only with a new isolated drawing.
    if session.started_by_session:
        if session.doc is None:
            session.new_document()
        created_document = True
    else:
        session.new_document()
        created_document = True
    try:
        _draw_frame(session)
        _draw_plate(session)
        session.regen()
        session.zoom_extents()
        dwg = session.save_as(dwg_path)
        _require_file(dwg, "DWG")
        dxf = session.export_dxf(dxf_path)
        _require_file(dxf, "DXF")
        bmp = session.export_bmp_preview(bmp_path)
        _require_file(bmp, "AutoCAD native BMP")
        png_result = convert_bmp_to_png(bmp, png_path)
        if png_result.get("status") != "ok":
            raise RuntimeError(f"BMP to PNG conversion failed: {png_result}")
        _require_file(png_path, "AutoCAD native PNG")

        native_review = review_active(session)
        if native_review["modelspace_entity_count"] < 20:
            raise RuntimeError(f"Too few AutoCAD entities: {native_review}")
        dxf_review = inspect_dxf(dxf)
        if dxf_review["evaluation"]["status"] != "pass":
            raise RuntimeError(f"DXF engineering drawing review failed: {dxf_review['evaluation']}")
        measurements = [
            float(item["measurement"])
            for item in dxf_review.get("dimensionEvidence", [])
            if item.get("measurement") is not None
        ]
        missing_measurements = [
            expected
            for expected in (120.0, 80.0, 90.0, 50.0, 15.0, 9.0)
            if not any(abs(actual - expected) <= 0.01 for actual in measurements)
        ]
        if missing_measurements:
            raise RuntimeError(
                f"DXF critical dimension entities missing or measurements incorrect: missing={missing_measurements}, actual={measurements}"
            )
        headless_render = render_dxf(dxf, dxf_png_path)
        _require_file(dxf_png_path, "DXF headless PNG")
        if headless_render.get("pixelCheck", {}).get("likelyBlank"):
            raise RuntimeError(f"DXF headless preview appears blank: {headless_render}")

        result = {
            "status": "ok",
            "run_id": run_id,
            "output_dir": str(output_dir),
            "assumptions": {
                "units": "mm",
                "drawing_standard": "Neutral GB/T-style A3 landscape; does not replace company templates",
                "source": "task-owned AutoCAD document",
            },
            "started_by_cad_studio": session.started_by_session,
            "outputs": {
                "dwg": _require_file(dwg, "DWG"),
                "dxf": _require_file(dxf, "DXF"),
                "bmp": _require_file(bmp, "AutoCAD native BMP"),
                "png": _require_file(png_path, "AutoCAD native PNG"),
                "headless_png": _require_file(dxf_png_path, "DXF headless PNG"),
            },
            "native_review": native_review,
            "dxf_review": dxf_review,
            "headless_render": headless_render,
            "manual_review_required": [
                "Company frames, fonts, lineweights, printers, and scale still require engineer confirmation",
                "This regression does not automatically assess BOM, technical requirements, or manufacturability",
            ],
        }
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report"] = _require_file(report_path, "JSON report")
        return result
    finally:
        if created_document:
            session.close_document(save_changes=False)
        owned_instance_closed = session.quit_owned_instance()
        if result is not None:
            result["cleanup"] = {
                "owned_instance_closed": owned_instance_closed if owned_instance else None,
                **session.last_cleanup,
            }
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            result["report"] = _require_file(report_path, "JSON report")
        if owned_instance and not owned_instance_closed and sys.exc_info()[0] is None:
            raise RuntimeError("The task-started AutoCAD instance did not exit before timeout")


def parse_args() -> argparse.Namespace:
    """@brief Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run AutoCAD Week 4 real-machine drawing regression")
    parser.add_argument("--output-dir", default=str(_default_output_dir()))
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


def main() -> int:
    '@brief Command-line entry point.'
    args = parse_args()
    output_root = Path(args.output_dir).expanduser().resolve()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        result = run_regression(output_root, run_id=run_id)
    except Exception as exc:
        result_path = output_root / run_id / "W4-001-drawing-report.json"
        result = {}
        if result_path.is_file():
            try:
                loaded = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    result = loaded
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        result.update({
            "status": "failed",
            "run_id": run_id,
            "output_dir": str(output_root / run_id),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
