"""SolidWorks 2026 native sheet-metal specimen, flat-pattern DXF, and reopen regression."""
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
from sw_export import export_flat_pattern_dxf  # noqa: E402
from sw_part import sketch, sketch_line  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_sheet_metal import BaseFlangeSpec, create_base_flange, sheet_metal_evidence  # noqa: E402


def _validate_evidence(evidence: dict, *, stage: str) -> None:
    """@brief Reject specimens lacking native sheet-metal semantics or body markers."""
    if not evidence.get("has_base_flange"):
        raise RuntimeError(f"{stage}: native BaseFlange feature not detected")
    if not evidence.get("has_sheet_metal_feature"):
        raise RuntimeError(f"{stage}: parent SheetMetal feature not detected")
    if not evidence.get("all_solid_bodies_are_sheet_metal"):
        raise RuntimeError(f"{stage}: SolidWorks does not mark the solid as a sheet-metal body")


def _validate_dxf(path: Path) -> dict:
    """@brief Read DXF structure; count entities/layers when ezdxf is installed."""
    if not path.is_file() or path.stat().st_size < 256:
        raise RuntimeError("Flat-pattern DXF missing or too small")
    result = {"path": str(path), "size_bytes": path.stat().st_size}
    try:
        import ezdxf

        document = ezdxf.readfile(path)
        entities = list(document.modelspace())
        result.update({
            "parser": "ezdxf",
            "entity_count": len(entities),
            "layers": sorted({str(entity.dxf.layer) for entity in entities}),
        })
        if not entities:
            raise RuntimeError("Flat-pattern DXF contains no model-space entities")
    except ImportError:
        text = path.read_text(encoding="latin-1", errors="ignore")
        if "SECTION" not in text or "ENTITIES" not in text:
            raise RuntimeError("Flat-pattern file is not valid ASCII DXF")
        result["parser"] = "header-check"
    return result


def run_regression(output_dir: Path, *, visible: bool = True, wait_seconds: int = 12) -> dict:
    """@brief Create U-shaped sheet metal with two bends and verify save, flattening, and reopening."""
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / "u_channel_sheet_metal.SLDPRT"
    dxf_path = output_dir / "u_channel_flat_pattern.dxf"
    review_dir = output_dir / "review"
    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    revision = str(get_com_member(sw, "RevisionNumber") or "")
    try:
        sw.CloseDoc(part_path.name)
    except Exception:
        pass
    for target in (part_path, dxf_path):
        if target.exists():
            target.unlink()

    model = new_document(sw, "part")
    with sketch(model, "Front Plane") as profile:
        # 60 mm base + 25 mm flanges on both sides; BaseFlange creates two real bends from an open profile.
        sketch_line(model, -mm(30), mm(25), -mm(30), 0.0)
        sketch_line(model, -mm(30), 0.0, mm(30), 0.0)
        sketch_line(model, mm(30), 0.0, mm(30), mm(25))

    feature = create_base_flange(
        model,
        profile,
        BaseFlangeSpec(
            thickness=mm(2.0),
            bend_radius=mm(2.5),
            depth=mm(100.0),
            k_factor=0.42,
            relief_ratio=0.5,
        ),
    )
    model.ForceRebuild3(False)
    native = sheet_metal_evidence(model)
    _validate_evidence(native, stage="after creation")
    feature_name = str(get_com_member(feature, "Name") or "")

    if not save_document(model, str(part_path)):
        raise RuntimeError("Sheet-metal SLDPRT save failed")
    if not export_flat_pattern_dxf(model, str(dxf_path), include_bend_lines=True):
        raise RuntimeError("Sheet-metal flat-pattern DXF export failed")
    dxf = _validate_dxf(dxf_path)

    report, report_path = run_review(
        model,
        str(review_dir),
        basename="u_channel_sheet_metal",
        expected_outputs=[str(part_path), str(dxf_path)],
    )

    title = str(get_com_member(model, "GetTitle") or part_path.name)
    sw.CloseDoc(title)
    reopened = open_document(sw, str(part_path), silent=True, raise_on_error=True)
    reopened_evidence = sheet_metal_evidence(reopened)
    _validate_evidence(reopened_evidence, stage="after reopen")

    created_parameters = native["base_flange_parameters"][0]
    reopened_parameters = reopened_evidence["base_flange_parameters"][0]
    for key, expected in (("thickness_m", mm(2.0)), ("bend_radius_m", mm(2.5)), ("depth_m", mm(100.0))):
        if abs(float(reopened_parameters[key]) - expected) > 1e-7:
            raise RuntimeError(f"Reopened parameter mismatch: {key}={reopened_parameters[key]}")

    return {
        "status": "ok",
        "revision": revision,
        "feature_name": feature_name,
        "artifacts": {
            "sldprt": {"path": str(part_path), "size_bytes": part_path.stat().st_size},
            "dxf": dxf,
            "review_report": str(report_path),
        },
        "created_evidence": native,
        "reopened_evidence": reopened_evidence,
        "parameter_roundtrip": {"created": created_parameters, "reopened": reopened_parameters},
        "review_evaluation": report.get("evaluation"),
    }


def main() -> int:
    '@brief Command-line entry point.'
    parser = argparse.ArgumentParser(description="Run real SolidWorks sheet-metal regression.")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "solidworks_sheet_metal_regression"))
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=12)
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result_path = output_dir / "sheet_metal_regression_result.json"
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
