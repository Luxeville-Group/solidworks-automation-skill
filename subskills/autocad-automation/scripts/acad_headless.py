"""@file acad_headless.py
@brief Read-only DXF inspection with ezdxf and optional headless PNG preview.

This backend neither reads nor writes DWG, executes AutoLISP, nor modifies source DXF. Final DWG/PDF
delivery still requires AutoCAD COM and native open-and-review.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DIMENSION_TYPES = {
    "DIMENSION",
    "ARC_DIMENSION",
    "LARGE_RADIAL_DIMENSION",
}
TEXT_TYPES = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}
TITLE_KEYWORDS = {
    "drawing_number": ("DRAWING NO", "RESİM NO", "\u56fe\u53f7"),
    "name": ("NAME", "PARÇA ADI", "\u540d\u79f0"),
    "material": ("MATERIAL", "MALZEME", "\u6750\u6599"),
    "scale": ("SCALE", "ÖLÇEK", "\u6bd4\u4f8b"),
    "units": ("UNITS", "BİRİM", "\u5355\u4f4d"),
    "design": ("DESIGN", "TASARIM", "\u8bbe\u8ba1"),
    "review": ("REVIEW", "KONTROL", "\u5ba1\u6838"),
    "cad_studio": ("CAD STUDIO",),
}  # Count each field once; escaped aliases preserve recognition of imported legacy drawings.
LAYER_GROUPS = {
    "outline": {"OUTLINE", "OBJECT", "VISIBLE", "KONTUR", "GÖRÜNÜR", "\u7c97\u5b9e\u7ebf", "\u8f6e\u5ed3"},
    "center": {"CENTER", "CENTRE", "CENTERLINE", "MERKEZ", "EKSEN", "\u4e2d\u5fc3\u7ebf"},
    "hidden": {"HIDDEN", "HIDE", "GİZLİ", "GIZLI", "\u865a\u7ebf"},
    "dimension": {"DIM", "DIMS", "DIMENSION", "ÖLÇÜ", "OLCU", "\u5c3a\u5bf8"},
    "text": {"TEXT", "NOTE", "ANNOTATION", "METİN", "METIN", "YAZI", "\u6587\u5b57"},
    "frame": {"FRAME", "BORDER", "TITLEBLOCK", "TITLE_BLOCK", "ÇERÇEVE", "CERCEVE", "ANTET", "\u56fe\u6846", "\u6807\u9898\u680f"},
}


def _layer_details(document) -> list[dict[str, Any]]:
    """@brief Collect layer display, plotting, color, and linetype evidence."""
    details = []
    for layer in document.layers:
        details.append({
            "name": str(layer.dxf.name),
            "color": int(layer.color),
            "linetype": str(layer.dxf.linetype),
            "off": bool(layer.is_off()),
            "frozen": bool(layer.is_frozen()),
            "locked": bool(layer.is_locked()),
            "plot": bool(layer.dxf.get("plot", 1)),
        })
    return details


def _entity_text(entity) -> str:
    """@brief Read TEXT/MTEXT/attribute text; return an empty string on failure."""
    try:
        if entity.dxftype() == "MTEXT":
            return str(entity.plain_text())
        return str(entity.dxf.get("text", ""))
    except Exception:
        return ""


def _dimension_evidence(entity) -> dict[str, Any]:
    """@brief Extract auditable fields from real DXF dimension entities."""
    measurement = None
    try:
        measurement = float(entity.get_measurement())
    except Exception:
        pass
    return {
        "type": entity.dxftype(),
        "layer": str(entity.dxf.layer),
        "measurement": measurement,
        "dimstyle": str(entity.dxf.get("dimstyle", "")),
        "textOverride": str(entity.dxf.get("text", "")),
    }


def _hole_evidence(entity) -> dict[str, Any]:
    """@brief Extract circular-hole centers, diameters, and layer evidence."""
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    return {
        "layer": str(entity.dxf.layer),
        "center": [float(center.x), float(center.y)],
        "radius": radius,
        "diameter": radius * 2.0,
    }


def _frame_candidates(modelspace) -> list[dict[str, Any]]:
    """@brief Find closed lightweight polylines with common drawing-sheet aspect ratios."""
    candidates = []
    paper_ratios = (420 / 297, 297 / 210)
    for entity in modelspace.query("LWPOLYLINE"):
        if not bool(entity.closed):
            continue
        points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
        if len(points) < 4:
            continue
        xs = [item[0] for item in points]
        ys = [item[1] for item in points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if min(width, height) < 120:
            continue
        ratio = max(width, height) / max(1e-9, min(width, height))
        if min(abs(ratio - expected) for expected in paper_ratios) > 0.15:
            continue
        candidates.append({
            "layer": str(entity.dxf.layer),
            "width": width,
            "height": height,
            "bbox": [[min(xs), min(ys)], [max(xs), max(ys)]],
        })
    return candidates


def _layer_group_checks(layer_names: list[str]) -> dict[str, bool]:
    """@brief Check key mechanical drawing layers using English, Turkish, and legacy aliases."""
    normalized = {name.strip().upper() for name in layer_names}
    return {
        group: any(alias.upper() in normalized for alias in aliases)
        for group, aliases in LAYER_GROUPS.items()
    }


def _engineering_evaluation(
    *,
    layer_checks: dict[str, bool],
    dimension_count: int,
    frame_count: int,
    title_keywords: list[str],
    hole_count: int,
) -> dict[str, Any]:
    """@brief Derive drawing review status and issue codes from structured evidence."""
    issues = []
    if not layer_checks["outline"]:
        issues.append({"code": "drawing-layer-outline", "message": "Outline/thick continuous-line layer missing"})
    if not layer_checks["dimension"] or dimension_count == 0:
        issues.append({"code": "drawing-true-dimensions", "message": "DIM layer or real DIMENSION entities missing"})
    if not layer_checks["frame"] or frame_count == 0:
        issues.append({"code": "drawing-frame", "message": "Frame layer or standard-sheet closed border missing"})
    if len(title_keywords) < 3:
        issues.append({"code": "drawing-title-block", "message": "Insufficient title-block field evidence"})
    if hole_count and not layer_checks["center"]:
        issues.append({"code": "drawing-hole-centers", "message": "Circular holes detected without a centerline layer"})
    return {
        "status": "pass" if not issues else "warn",
        "issues": issues,
        "manualReviewRequired": True,
    }


def inspect_dxf(source: str | Path) -> dict[str, Any]:
    """@brief Inspect DXF layers, dimensions, frames, hole positions, and bounds without modifying it."""
    try:
        import ezdxf
        from ezdxf import bbox
    except ImportError as exc:
        raise RuntimeError("Optional dependency ezdxf missing; run: python -m pip install ezdxf") from exc

    path = Path(source).expanduser().resolve()
    if path.suffix.lower() != ".dxf":
        raise ValueError("The headless backend accepts DXF only; open DWG read-only through AutoCAD COM")
    if not path.is_file():
        raise FileNotFoundError(path)
    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    type_counts = Counter(entity.dxftype() for entity in modelspace)
    layer_counts = Counter(str(entity.dxf.layer) for entity in modelspace)
    dimensions = [
        _dimension_evidence(entity)
        for entity in modelspace
        if entity.dxftype() in DIMENSION_TYPES
    ]
    holes = [
        _hole_evidence(entity)
        for entity in modelspace
        if entity.dxftype() == "CIRCLE"
    ]
    text_values = [
        _entity_text(entity).strip()
        for entity in modelspace
        if entity.dxftype() in TEXT_TYPES and _entity_text(entity).strip()
    ]
    keyword_matches = sorted({
        keyword
        for keyword, aliases in TITLE_KEYWORDS.items()
        if any(
            alias.casefold().replace("\u0307", "").replace("ı", "i")
            in text.casefold().replace("\u0307", "").replace("ı", "i")
            for alias in aliases for text in text_values
        )
    })
    layer_details = _layer_details(document)
    layer_checks = _layer_group_checks([item["name"] for item in layer_details])
    frames = _frame_candidates(modelspace)
    extents = bbox.extents(modelspace, fast=True)
    bbox_value = None
    if extents.has_data:
        bbox_value = [list(extents.extmin), list(extents.extmax)]
    return {
        "schemaVersion": "2.0",
        "status": "ok",
        "backend": "ezdxf-readonly",
        "source": path.name,
        "fileSize": path.stat().st_size,
        "dxfVersion": document.dxfversion,
        "units": int(document.header.get("$INSUNITS", 0)),
        "entityCount": sum(type_counts.values()),
        "typeCounts": dict(type_counts),
        "layerCounts": dict(layer_counts),
        "layers": [item["name"] for item in layer_details],
        "layerDetails": layer_details,
        "bbox": bbox_value,
        "dimensionEvidence": dimensions,
        "trueDimensionEntityCount": len(dimensions),
        "holeEvidence": holes,
        "frameCandidates": frames,
        "titleTextKeywords": keyword_matches,
        "engineeringChecks": {
            "layerGroups": layer_checks,
            "hasTrueDimensions": bool(dimensions),
            "hasFrameCandidate": bool(frames),
            "hasTitleBlockEvidence": len(keyword_matches) >= 3,
            "hasHoleCenters": not holes or layer_checks["center"],
        },
        "evaluation": _engineering_evaluation(
            layer_checks=layer_checks,
            dimension_count=len(dimensions),
            frame_count=len(frames),
            title_keywords=keyword_matches,
            hole_count=len(holes),
        ),
        "limitations": ["Read-only DXF inspection", "Does not replace native AutoCAD DWG/PDF review"],
    }


def render_dxf(source: str | Path, output: str | Path) -> dict[str, Any]:
    """@brief Render a read-only PNG preview with ezdxf/matplotlib."""
    try:
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("PNG preview requires ezdxf and matplotlib") from exc

    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if source_path.suffix.lower() != ".dxf" or output_path.suffix.lower() != ".png":
        raise ValueError("Preview input must be DXF and output must be PNG")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = ezdxf.readfile(source_path)
    figure = plt.figure(figsize=(12, 8), dpi=140)
    axes = figure.add_axes([0.02, 0.02, 0.96, 0.96])
    axes.set_aspect("equal")
    axes.axis("off")
    context = RenderContext(document)
    Frontend(context, MatplotlibBackend(axes)).draw_layout(document.modelspace(), finalize=True)
    figure.savefig(output_path, facecolor="white", bbox_inches="tight", pad_inches=0.05)
    plt.close(figure)
    pixel_check: dict[str, Any] = {}
    try:
        from PIL import Image

        with Image.open(output_path) as image:
            rgb = image.convert("RGB")
            sampled = rgb.resize((96, 64))
            unique_colors = len(set(sampled.getdata()))
            pixel_check = {
                "width": image.width,
                "height": image.height,
                "uniqueSampleColors": unique_colors,
                "likelyBlank": unique_colors < 8,
            }
    except Exception as exc:
        pixel_check = {"error": str(exc), "likelyBlank": None}
    return {
        "status": "ok" if not pixel_check.get("likelyBlank") else "warn",
        "backend": "ezdxf-matplotlib",
        "path": output_path.name,
        "size": output_path.stat().st_size,
        "pixelCheck": pixel_check,
    }


def main(argv: list[str] | None = None) -> int:
    """@brief CLI entry point."""
    parser = argparse.ArgumentParser(description="Read-only DXF inspection/preview with ezdxf")
    parser.add_argument("source", type=Path)
    parser.add_argument("--preview", type=Path, help="Optional PNG preview output")
    parser.add_argument("--json", type=Path, help="Optional JSON report output")
    args = parser.parse_args(argv)
    report = inspect_dxf(args.source)
    if args.preview:
        report["preview"] = render_dxf(args.source, args.preview)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
