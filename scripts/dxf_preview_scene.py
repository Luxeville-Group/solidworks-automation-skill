"""@file dxf_preview_scene.py
@brief Convert DXF read-only into browser-safe PreviewScene JSON.

Do not execute AutoLISP, parse DWG or modify the source. Record entities outside
the allowlist as limitations rather than executing them or claiming complete display.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


MAX_DXF_BYTES = 50 * 1024 * 1024
MAX_ENTITIES = 200_000
SUPPORTED_TYPES = {"LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE", "TEXT", "MTEXT", "DIMENSION"}
LAYER_COLORS = {
    "OUTLINE": "#25312f",
    "HOLES": "#176c65",
    "CENTER": "#8a9a95",
    "DIMENSION": "#b36b22",
    "FRAME": "#25312f",
    "TITLE": "#4f7770",
    "TEXT": "#42514e",
}


def _point(value: Any) -> list[float]:
    """@brief Convert ezdxf Vec3 or a two-element sequence to finite 2D coordinates."""
    x = float(value.x if hasattr(value, "x") else value[0])
    y = float(value.y if hasattr(value, "y") else value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("DXF sonlu olmayan koordinatlar içeriyor")
    return [x, y]


def _circle_points(center: Any, radius: float, start: float = 0.0, end: float = 360.0) -> list[list[float]]:
    """@brief Discretize circles/arcs into stable browser polylines."""
    cx, cy = _point(center)
    sweep = (end - start) % 360.0 or 360.0
    segments = max(12, min(96, int(math.ceil(sweep / 6.0))))
    return [
        [cx + math.cos(math.radians(start + sweep * index / segments)) * radius, cy + math.sin(math.radians(start + sweep * index / segments)) * radius]
        for index in range(segments + 1)
    ]


def _dimension_points(entity: Any) -> list[list[float]]:
    """@brief Extract actual DIMENSION definition points independently of render-block internals."""
    points = []
    for name in ("defpoint2", "defpoint3", "defpoint", "text_midpoint"):
        if entity.dxf.hasattr(name):
            try:
                points.append(_point(entity.dxf.get(name)))
            except (TypeError, ValueError):
                continue
    return points


def _entity_payload(entity: Any) -> dict[str, Any] | None:
    """@brief Convert allowed DXF entities into PreviewScene entities."""
    kind = entity.dxftype()
    layer = str(entity.dxf.get("layer", "0"))
    handle = str(entity.dxf.get("handle", "")) or f"{kind.lower()}-{id(entity)}"
    base: dict[str, Any] = {
        "id": handle,
        "kind": kind.lower(),
        "layer": layer,
        "color": LAYER_COLORS.get(layer.upper(), "#42514e"),
        "evidenceRefs": [f"dxf:{handle}", f"layer:{layer}"],
    }
    if kind == "LINE":
        base["points"] = [_point(entity.dxf.start), _point(entity.dxf.end)]
    elif kind == "CIRCLE":
        base["kind"] = "circle"
        base["points"] = _circle_points(entity.dxf.center, float(entity.dxf.radius))
    elif kind == "ARC":
        base["kind"] = "arc"
        base["points"] = _circle_points(entity.dxf.center, float(entity.dxf.radius), float(entity.dxf.start_angle), float(entity.dxf.end_angle))
    elif kind == "LWPOLYLINE":
        points = [[float(x), float(y)] for x, y in entity.get_points("xy")]
        if entity.closed and points:
            points.append(points[0])
        base["kind"] = "polyline"
        base["points"] = points
    elif kind == "POLYLINE":
        points = [_point(vertex.dxf.location) for vertex in entity.vertices]
        if entity.is_closed and points:
            points.append(points[0])
        base["kind"] = "polyline"
        base["points"] = points
    elif kind in {"TEXT", "MTEXT"}:
        base["kind"] = "text"
        base["text"] = str(entity.plain_text() if kind == "MTEXT" else entity.dxf.get("text", ""))[:4096]
        base["points"] = [_point(entity.dxf.insert)]
    elif kind == "DIMENSION":
        base["kind"] = "dimension"
        try:
            measurement = float(entity.get_measurement())
            base["text"] = f"{measurement:g}" if math.isfinite(measurement) else "DIM"
        except (TypeError, ValueError, AttributeError):
            base["text"] = str(entity.dxf.get("text", "DIM"))[:256]
        base["points"] = _dimension_points(entity)
    else:
        return None
    if not base.get("points"):
        return None
    return base


def _bounds(entities: Iterable[dict[str, Any]]) -> dict[str, float]:
    """@brief Compute the scene 2D bounding box."""
    points = [point for entity in entities for point in entity.get("points", [])]
    if not points:
        return {"minX": 0.0, "minY": 0.0, "maxX": 1.0, "maxY": 1.0}
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}


def dxf_to_preview_scene(source: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    """@brief Parse DXF read-only and return, optionally write, PreviewScene 1.0."""
    import ezdxf

    source_path = Path(source).expanduser().resolve()
    if source_path.suffix.lower() != ".dxf":
        raise ValueError("PreviewScene dönüştürme yalnızca DXF kabul eder")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path.stat().st_size > MAX_DXF_BYTES:
        raise ValueError(f"DXF şu sınırı aşıyor: {MAX_DXF_BYTES // 1024 // 1024} MB")
    document = ezdxf.readfile(source_path)
    modelspace = document.modelspace()
    entities = []
    unsupported = Counter()
    for index, entity in enumerate(modelspace):
        if index >= MAX_ENTITIES:
            raise ValueError(f"DXF varlık sayısı şu sınırı aşıyor: {MAX_ENTITIES} güvenlik sınırı")
        if entity.dxftype() not in SUPPORTED_TYPES:
            unsupported[entity.dxftype()] += 1
            continue
        payload = _entity_payload(entity)
        if payload:
            entities.append(payload)
    layer_counts = Counter(str(entity.get("layer") or "0") for entity in entities)
    layers = [
        {"name": name, "color": LAYER_COLORS.get(name.upper(), "#42514e"), "count": count, "visible": True}
        for name, count in sorted(layer_counts.items())
    ]
    warnings = [f"Gösterilmeyen: {kind}: {count}" for kind, count in sorted(unsupported.items())]
    scene = {
        "schemaVersion": "1.0",
        "kind": "dxf-scene",
        "sourceArtifact": source_path.name,
        "units": "mm" if int(document.header.get("$INSUNITS", 0)) == 4 else "unitless",
        "bounds": _bounds(entities),
        "entities": entities,
        "layers": layers,
        "warnings": warnings,
        "limitations": ["Salt okunur PreviewScene; DXF değişmez", *warnings],
    }
    if output is not None:
        target = Path(output).expanduser().resolve()
        if target.suffix.lower() != ".json" or not target.name.lower().endswith(".scene.json"):
            raise ValueError("PreviewScene çıktısı .scene.json uzantısı kullanmalıdır")
        if target.exists():
            raise FileExistsError(f"Mevcut PreviewScene üzerine yazma reddedildi: {target.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    return scene


def main(argv: list[str] | None = None) -> int:
    """@brief Command-line entry point."""
    parser = argparse.ArgumentParser(description="DXF dosyasını güvenli PreviewScene JSON biçimine dönüştür")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    scene = dxf_to_preview_scene(args.source, args.output)
    print(json.dumps({"status": "pass", "output": str(args.output), "entities": len(scene["entities"]), "layers": len(scene["layers"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
