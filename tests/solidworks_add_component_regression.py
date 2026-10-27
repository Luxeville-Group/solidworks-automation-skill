"""
Real SolidWorks assembly AddComponent regression.

Covers `AddComponent4()` returning None with Chinese-language SW2024 + pywin32.
Pass criteria:
1. Generate and save a minimal part.
2. Create an assembly.
3. Add the component successfully through `sw_assembly.add_component()`.
4. Read the component from the feature tree/component list and save .SLDASM.
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
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sw_assembly import add_component, get_components, resolve_component  # noqa: E402
from sw_connect import connect_solidworks, get_com_member, mm, new_document, save_document  # noqa: E402
from sw_part import extrude_boss, sketch, sketch_rectangle  # noqa: E402
from sw_review import run_review  # noqa: E402


def _default_output_dir() -> Path:
    """Return the default output directory."""
    return Path(tempfile.gettempdir()) / "solidworks_add_component_regression"


def create_probe_part(sw, part_path: Path):
    """Create a minimal test part."""
    try:
        sw.CloseDoc(part_path.name)
    except Exception:
        pass
    model = new_document(sw, "part")
    with sketch(model, "Front Plane") as sketch_name:
        sketch_rectangle(model, 0, 0, mm(24), mm(14))
    feature = extrude_boss(model, sketch_name, mm(8))
    if feature is None:
        raise RuntimeError("Test-part extrusion failed")
    model.ForceRebuild3(False)
    if not save_document(model, str(part_path)):
        raise RuntimeError(f"Test-part save failed: {part_path}")
    title = get_com_member(model, "GetTitle")
    sw.CloseDoc(title)
    return part_path


def run_regression(
    output_dir: Path,
    visible: bool = True,
    wait_seconds: int = 12,
    run_id: str | None = None,
) -> dict:
    """Run a real AddComponent regression."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    part_path = output_dir / f"add_component_probe_block_{run_id}.SLDPRT"
    asm_path = output_dir / f"add_component_probe_assembly_{run_id}.SLDASM"
    review_dir = output_dir / "review"
    result = {
        "output_dir": str(output_dir),
        "run_id": run_id,
        "part_path": str(part_path),
        "asm_path": str(asm_path),
    }

    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    result["revision"] = get_com_member(sw, "RevisionNumber")

    create_probe_part(sw, part_path)
    result["part_exists"] = part_path.exists()
    result["part_size"] = part_path.stat().st_size if part_path.exists() else 0

    try:
        sw.CloseDoc(asm_path.name)
    except Exception:
        pass
    asm = new_document(sw, "assembly")
    result["asm_title"] = get_com_member(asm, "GetTitle")
    result["asm_type"] = get_com_member(asm, "GetType")

    component = add_component(asm, str(part_path), x=0.0, y=0.0, z=0.0, sw=sw)
    if component is None:
        raise RuntimeError("sw_assembly.add_component returned None")
    resolve_component(component)
    result["component_name"] = get_com_member(component, "Name2")
    result["component_path"] = get_com_member(component, "GetPathName")
    result["components"] = get_components(asm)
    result["component_count"] = len(result["components"])
    if result["component_count"] < 1:
        raise RuntimeError("Assembly component list is empty")

    asm.ForceRebuild3(False)
    if not save_document(asm, str(asm_path)):
        raise RuntimeError(f"Assembly save failed: {asm_path}")
    result["asm_exists"] = asm_path.exists()
    result["asm_size"] = asm_path.stat().st_size if asm_path.exists() else 0

    report, report_path = run_review(
        asm,
        str(review_dir),
        basename="add_component_probe_assembly",
        expected_outputs=[str(asm_path), str(part_path)],
    )
    result["review_report"] = str(report_path)
    result["review_evaluation"] = report.get("evaluation")
    result["review_checks"] = report.get("checks")
    return result


def parse_args() -> argparse.Namespace:
    'Parse command-line arguments.'
    parser = argparse.ArgumentParser(description="Run real SolidWorks AddComponent regression.")
    parser.add_argument(
        "--output-dir",
        default=str(_default_output_dir()),
        help="Output directory; defaults to the system temporary directory.",
    )
    parser.add_argument("--hidden", action="store_true", help="Attempt to hide the SolidWorks window.")
    parser.add_argument("--wait-seconds", type=int, default=12, help="Seconds to wait after starting SolidWorks.")
    parser.add_argument("--run-id", default="", help="Output filename suffix; defaults to the current time.")
    return parser.parse_args()


def main() -> int:
    'CLI entry point.'
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    result_path = output_dir / "add_component_regression_result.json"
    try:
        result = run_regression(
            output_dir,
            visible=not args.hidden,
            wait_seconds=args.wait_seconds,
            run_id=args.run_id or None,
        )
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
