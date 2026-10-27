#!/usr/bin/env python
"""SolidWorks foreign STEP/IGES import regression."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from sw_connect import get_com_member, mm  # noqa: E402
from sw_part import extrude_midplane, sketch, sketch_rectangle  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


def parse_args() -> argparse.Namespace:
    """@brief Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(Path(tempfile.gettempdir()) / "solidworks_loadfile4_import_regression"),
        help="Test output directory.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Preserve existing files in the output directory.",
    )
    return parser.parse_args()


def close_if_open(session: SolidWorksSession, *paths: Path) -> None:
    """@brief Close possibly open test documents by filename."""
    for path in paths:
        try:
            session.sw.CloseDoc(path.name)
        except Exception:
            pass


def main() -> int:
    """@brief Create a block STEP, import through LoadFile4(..., 'r', ...), and save SLDPRT."""
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and not args.keep:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_part = output_dir / "loadfile4_source.SLDPRT"
    step_path = output_dir / "loadfile4_source.step"
    imported_part = output_dir / "loadfile4_imported.SLDPRT"
    review_dir = output_dir / "review"

    session = SolidWorksSession(visible=True)
    close_if_open(session, source_part, imported_part)

    source_model = session.new_part()
    source_title = ""
    imported_title = ""
    try:
        source_title = str(get_com_member(source_model, "GetTitle") or "")
        with sketch(source_model, "Front Plane") as sketch_ref:
            sketch_rectangle(source_model, 0, 0, mm(60), mm(28))
        if extrude_midplane(source_model, sketch_ref, mm(18)) is None:
            raise AssertionError("Test-block extrusion failed")
        source_model.ForceRebuild3(False)
        if not session.save(source_model, source_part):
            raise AssertionError("Source SLDPRT save failed")
        if not session.export(source_model, step_path):
            raise AssertionError("Source STEP export failed")
        session.close(model=source_model)

        imported_model = session.open(step_path, silent=True, raise_on_error=True)
        imported_title = str(get_com_member(imported_model, "GetTitle") or "")
        imported_model.ForceRebuild3(False)
        bodies = get_com_member(imported_model, "GetBodies2", 0, False) or []
        if len(bodies) < 1:
            raise AssertionError("No bodies after import")
        if not session.save(imported_model, imported_part):
            raise AssertionError("Imported SLDPRT save failed")

        review, review_report_path = run_review(
            imported_model,
            review_dir,
            basename="loadfile4_imported",
            views=("isometric", "front", "top", "right"),
            expected_outputs=[imported_part, step_path],
        )
        result = {
            "status": "pass",
            "source_part": str(source_part),
            "source_step": str(step_path),
            "imported_part": str(imported_part),
            "body_count": len(bodies),
            "review_report": str(review_report_path),
            "review_evaluation": review.get("evaluation", {}),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        if imported_title:
            session.sw.CloseDoc(imported_title)
        if source_title:
            session.sw.CloseDoc(source_title)
        close_if_open(session, source_part, imported_part)


if __name__ == "__main__":
    raise SystemExit(main())
