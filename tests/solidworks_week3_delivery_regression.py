"""Week 3 real-machine SolidWorks parameter, property, and delivery regression.

Requires Windows, a supported SolidWorks version, and pywin32/comtypes. It is excluded from normal
pytest collection and must be explicitly executed manually or by Windows self-hosted CI.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sw_assembly import add_component, get_components, resolve_component  # noqa: E402
from sw_connect import get_com_member, mm  # noqa: E402
from sw_delivery import export_assembly_bom_csv, pack_and_go  # noqa: E402
from sw_document_data import set_custom_properties, update_dimension_mm  # noqa: E402
from sw_export import batch_export_formats  # noqa: E402
from sw_part import extrude_boss, sketch, sketch_rectangle  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


def _default_output_dir() -> Path:
    """@brief Return this week's default real-machine regression output root."""
    return Path(tempfile.gettempdir()) / "solidworks_week3_delivery_regression"


def _require_file(path: Path, label: str) -> dict:
    """@brief Require a nonempty artifact and return file evidence."""
    if not path.is_file():
        raise RuntimeError(f"{label} not generated: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError(f"{label} is empty: {path}")
    return {"path": str(path), "size_bytes": size}


def _assert_dimension_result(result: dict, expected_mm: float) -> None:
    """@brief Validate dimension-update state, rebuild results, and millimeter readback."""
    if not result.get("success"):
        raise RuntimeError(f"Dimension update failed: {result}")
    actual = float(result["after_mm"]["current"])
    if not math.isclose(actual, expected_mm, rel_tol=0.0, abs_tol=1e-6):
        raise RuntimeError(f"Dimension readback mismatch: actual={actual}, expected={expected_mm}")


def _create_part(
    session: SolidWorksSession,
    path: Path,
    *,
    width_mm: float,
    height_mm: float,
    initial_depth_mm: float,
    final_depth_mm: float,
    properties: dict[str, str],
) -> dict:
    """@brief Create a part, change a real extrusion dimension, and write/read custom properties."""
    model = session.new_part()
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sketch(model, "Front Plane") as sketch_name:
            sketch_rectangle(model, 0, 0, mm(width_mm), mm(height_mm))
        feature = extrude_boss(model, sketch_name, mm(initial_depth_mm))
        if feature is None:
            raise RuntimeError(f"Part extrusion failed: {path.name}")
        feature_name = str(get_com_member(feature, "Name"))
        dimension_name = f"D1@{feature_name}"
        dimension_result = update_dimension_mm(model, dimension_name, final_depth_mm)
        _assert_dimension_result(dimension_result, final_depth_mm)

        property_result = set_custom_properties(model, properties)
        if not property_result.get("success"):
            raise RuntimeError(f"Custom-property write or readback failed: {property_result}")

        if not session.save(model, str(path)):
            raise RuntimeError(f"Part save failed: {path}")
        file_evidence = _require_file(path, 'parça')
        return {
            "file": file_evidence,
            "feature": feature_name,
            "dimension": dimension_result,
            "properties": property_result,
        }
    finally:
        session.close(title=title)


def _validate_batch_export(report: dict, expected_count: int) -> list[dict]:
    """@brief Verify all batch exports are nonempty artifacts newly created in this run."""
    if not report.get("success"):
        raise RuntimeError(f"Batch export failed: {report}")
    outputs = [
        output
        for document in report.get("documents", [])
        for output in document.get("outputs", [])
    ]
    if len(outputs) != expected_count:
        raise RuntimeError(f"Batch export count mismatch: actual={len(outputs)}, expected={expected_count}")
    for output in outputs:
        if not output.get("produced_this_run") or int(output.get("size_bytes", 0)) <= 0:
            raise RuntimeError(f"Batch export lacks current-run artifact evidence: {output}")
    return outputs


def _validate_pack_and_go(report: dict, expected_sources: set[str]) -> str:
    """@brief Validate native Pack and Go or an explicitly labeled dependency-staging fallback."""
    audit = report.get("audit_matrix") or {}
    if not audit.get("rows") or not audit.get("checks"):
        raise RuntimeError(f"Pack and Go audit matrix missing: {report}")
    summary = audit.get("summary") or {}
    if int(summary.get("required_count") or 0) < len(expected_sources):
        raise RuntimeError(f"Pack and Go required-file audit count insufficient: {summary}")
    if audit.get("status") == "blocked" and not audit.get("blocking_error_codes"):
        raise RuntimeError(f"Pack and Go audit blocked without an error code: {audit}")
    if report.get("status") == "blocked" and report.get("error_code") == "SW_PACK_AND_GO_DEPENDENCY_ENUMERATION_INCOMPLETE":
        if any(code != 0 for code in report.get("status_codes", [])):
            raise RuntimeError(f"Pack and Go blocked but returned nonzero status codes: {report}")
        if not report.get("outputs") or not report.get("missing_dependencies"):
            raise RuntimeError(f"Pack and Go blocking evidence incomplete: {report}")
        return "blocked"
    if not report.get("success"):
        raise RuntimeError(f"Pack and Go failed: {report}")
    if any(code != 0 for code in report.get("status_codes", [])):
        raise RuntimeError(f"Pack and Go returned nonzero status codes: {report['status_codes']}")
    packaged_names = {Path(item["path"]).name.casefold() for item in report.get("outputs", [])}
    missing = sorted(name for name in expected_sources if name.casefold() not in packaged_names)
    if missing:
        raise RuntimeError(f"Pack and Go referenced files missing: {missing}")
    if audit.get("error_code") in {"SW_PACK_AUDIT_SOURCE_OUTPUT_MISSING", "SW_PACK_AUDIT_REQUIRED_FILE_MISSING"}:
        raise RuntimeError(f"Pack and Go audit found required files missing from package: {audit}")
    return "pilot" if report.get("status") == "pilot" else "pass"


def _close_created_documents(session: SolidWorksSession, titles: list[str]) -> None:
    """@brief Best-effort closing of script-created documents, leaving preexisting user documents untouched."""
    for title in reversed(titles):
        if not title:
            continue
        try:
            session.close(title=title)
        except Exception:
            pass


def run_regression(
    output_root: Path,
    *,
    version: int | None = None,
    visible: bool = True,
    wait_seconds: int = 20,
    run_id: str | None = None,
) -> dict:
    """@brief Run all Week 3 real SolidWorks delivery regressions."""
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    native_dir = output_dir / "native"
    export_dir = output_dir / "exports"
    package_dir = output_dir / "pack_and_go"
    review_dir = output_dir / "review"
    native_dir.mkdir()

    part_a = native_dir / "W3-PLATE-A.SLDPRT"
    part_b = native_dir / "W3-BLOCK-B.SLDPRT"
    assembly_path = native_dir / "W3-DELIVERY-ASSEMBLY.SLDASM"
    bom_path = output_dir / "W3-DELIVERY-BOM.csv"
    created_titles: list[str] = []
    session = SolidWorksSession(version=version, visible=visible, wait_seconds=wait_seconds)
    result = {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "revision": str(get_com_member(session.sw, "RevisionNumber")),
        "connection": session.connection_info,
    }

    try:
        result["parts"] = [
            _create_part(
                session,
                part_a,
                width_mm=48,
                height_mm=32,
                initial_depth_mm=8,
                final_depth_mm=12,
                properties={
                    "PartNumber": "W3-PLATE-A",
                    "Description": "Week 3 parameter-regression mounting plate",
                    "Material": "Q235B",
                },
            ),
            _create_part(
                session,
                part_b,
                width_mm=30,
                height_mm=22,
                initial_depth_mm=10,
                final_depth_mm=16,
                properties={
                    "PartNumber": "W3-BLOCK-B",
                    "Description": "Week 3 parameter-regression locating block",
                    "Material": "6061-T6",
                },
            ),
        ]

        assembly = session.new_assembly()
        assembly_title = str(get_com_member(assembly, "GetTitle"))
        created_titles.append(assembly_title)
        component_specs = (
            (part_a, 0.000),
            (part_a, 0.065),
            (part_b, 0.125),
        )
        for part_path, x in component_specs:
            component = add_component(assembly, str(part_path), x=x, y=0.0, z=0.0, sw=session.sw)
            if component is None:
                raise RuntimeError(f"Assembly-component insertion failed: {part_path}")
            resolve_component(component)

        components = get_components(assembly)
        if len(components) != len(component_specs):
            raise RuntimeError(
                f"Assembly component count mismatch: actual={len(components)}, expected={len(component_specs)}"
            )
        assembly.ForceRebuild3(False)
        if not session.save(assembly, str(assembly_path)):
            raise RuntimeError(f"Assembly save failed: {assembly_path}")
        result["assembly"] = {
            "file": _require_file(assembly_path, 'montaj'),
            "components": components,
            "component_count": len(components),
        }

        bom = export_assembly_bom_csv(assembly, bom_path)
        if not bom.get("success") or bom.get("row_count") != 2 or bom.get("quantity_total") != 3:
            raise RuntimeError(f"BOM count or artifact evidence incorrect: {bom}")
        _require_file(bom_path, "BOM")
        result["bom"] = bom

        package = pack_and_go(assembly, package_dir, flatten=True, fallback_policy="stage_dependencies")
        pack_status = _validate_pack_and_go(
            package,
            {part_a.name, part_b.name, assembly_path.name},
        )
        result["pack_and_go"] = package
        if pack_status == "blocked":
            result.setdefault("limitations", []).append(
                "Native SolidWorks Pack and Go dependency enumeration is blocked; top-level artifacts and missing-dependency evidence retained"
            )
        elif pack_status == "pilot":
            result.setdefault("limitations", []).append(
                "Native SolidWorks Pack and Go did not enumerate every dependency; a GetDependencies2 staging package was generated and still requires human review"
            )

        exports = batch_export_formats(
            session.sw,
            [part_a, part_b],
            export_dir,
            formats=(".step", ".stl"),
            overwrite=False,
            close_documents=True,
        )
        export_outputs = _validate_batch_export(exports, expected_count=4)
        result["batch_export"] = exports

        expected_outputs = [part_a, part_b, assembly_path, bom_path]
        expected_outputs.extend(Path(item["path"]) for item in package["outputs"])
        expected_outputs.extend(Path(item["path"]) for item in export_outputs)
        review, review_path = run_review(
            assembly,
            review_dir,
            basename="week3_delivery_assembly",
            views=("isometric", "front", "top", "right"),
            expected_outputs=[str(path) for path in expected_outputs],
        )
        if review.get("evaluation", {}).get("status") == "fail":
            raise RuntimeError(f"Delivery review failed: {review.get('evaluation')}")
        blank_previews = [
            item for item in review.get("previews", []) if item.get("likely_blank")
        ]
        if blank_previews:
            raise RuntimeError(f"Potentially blank previews found: {blank_previews}")
        result["review"] = {
            "report_path": str(review_path),
            "evaluation": review.get("evaluation"),
            "checks": review.get("checks"),
            "previews": review.get("previews"),
        }
        result["status"] = "pass_with_blocked" if pack_status == "blocked" else "pass_with_pilot" if pack_status == "pilot" else "ok"
        return result
    finally:
        _close_created_documents(session, created_titles)
        result["owned_instance_closed"] = bool(session.quit_owned_instance())


def parse_args() -> argparse.Namespace:
    """@brief Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Week 3 real SolidWorks delivery regression.")
    parser.add_argument(
        "--output-dir",
        default=str(_default_output_dir()),
        help="Output root; each run creates a separate timestamped directory.",
    )
    parser.add_argument("--run-id", default="", help="Current-run directory name; defaults to the current time.")
    parser.add_argument("--version", type=int, help="SolidWorks year, for example 2026; defaults to the latest registered version.")
    parser.add_argument("--hidden", action="store_true", help="Attempt to hide newly started SolidWorks windows.")
    parser.add_argument("--wait-seconds", type=int, default=20, help="Seconds to wait for SolidWorks startup.")
    return parser.parse_args()


def main() -> int:
    """@brief CLI entry point that always writes structured results."""
    args = parse_args()
    output_root = Path(args.output_dir).expanduser().resolve()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = output_root / run_id / "week3_delivery_regression_result.json"
    try:
        result = run_regression(
            output_root,
            version=args.version,
            visible=not args.hidden,
            wait_seconds=args.wait_seconds,
            run_id=run_id,
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "run_id": run_id,
            "output_dir": str(output_root / run_id),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"ok", "pass_with_blocked", "pass_with_pilot"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
