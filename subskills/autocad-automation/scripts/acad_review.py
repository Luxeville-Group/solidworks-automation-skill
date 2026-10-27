# -*- coding: utf-8 -*-
"""@file acad_review.py
@brief Review AutoCAD drawing entities, layers, and bounding boxes.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from acad_session import AutoCADSession, point_tuple


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """@brief Read a COM property safely."""
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _entity_bbox(entity: Any) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """@brief Get an entity bounding box; return None when unsupported."""
    try:
        min_pt, max_pt = entity.GetBoundingBox()
        return point_tuple(min_pt), point_tuple(max_pt)
    except Exception:
        return None


def _merge_bbox(
    current: Optional[List[List[float]]],
    bbox: Tuple[Tuple[float, float, float], Tuple[float, float, float]],
) -> List[List[float]]:
    """@brief Merge global bounding boxes."""
    min_pt, max_pt = bbox
    if current is None:
        return [list(min_pt), list(max_pt)]
    for i in range(3):
        current[0][i] = min(current[0][i], min_pt[i])
        current[1][i] = max(current[1][i], max_pt[i])
    return current


def review_active(session: AutoCADSession) -> Dict[str, Any]:
    """@brief Review the active document."""
    doc = session.active_document()
    type_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    bbox_global: Optional[List[List[float]]] = None
    bbox_failures = 0

    for entity in session.iter_model_entities():
        object_name = str(_safe_getattr(entity, "ObjectName", "Unknown"))
        layer_name = str(_safe_getattr(entity, "Layer", "Unknown"))
        type_counts[object_name] += 1
        layer_counts[layer_name] += 1
        bbox = _entity_bbox(entity)
        if bbox is None:
            bbox_failures += 1
        else:
            bbox_global = _merge_bbox(bbox_global, bbox)

    full_name = str(_safe_getattr(doc, "FullName", ""))
    file_exists = bool(full_name and Path(full_name).exists())
    file_size = Path(full_name).stat().st_size if file_exists else None

    return {
        "status": "ok",
        "document": str(_safe_getattr(doc, "Name", "")),
        "full_name": full_name,
        "file_exists": file_exists,
        "file_size": file_size,
        "modelspace_entity_count": sum(type_counts.values()),
        "type_counts": dict(type_counts),
        "layer_counts": dict(layer_counts),
        "bbox": bbox_global,
        "bbox_failures": bbox_failures,
    }


def main() -> int:
    """@brief CLI entry point."""
    parser = argparse.ArgumentParser(description="Review the active or specified AutoCAD drawing")
    parser.add_argument("target", nargs="?", help="Optional DWG/DXF to open and review")
    parser.add_argument("--launch", action="store_true", help="Allow starting AutoCAD")
    parser.add_argument("--json", help="Save the review report as JSON")
    args = parser.parse_args()

    session = AutoCADSession(create_if_missing=args.launch, visible=True).connect()
    if args.target:
        session.open_document(args.target, read_only=True)
    report = review_active(session)
    session.zoom_extents()

    if args.json:
        out = Path(args.json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(out)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
