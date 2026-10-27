"""SolidWorks engineering-drawing operations."""
import math
import re
from fractions import Fraction
from pathlib import Path

try:
    from scripts.sw_preflight import import_com_dependencies
    from scripts.sw_connect import create_empty_dispatch_variant, get_com_member
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import create_empty_dispatch_variant, get_com_member

pythoncom, _win32com, VARIANT = import_com_dependencies()


PAPER_SIZES = {
    "A4": {"code": 5, "width_m": 0.297, "height_m": 0.210},
    "A3": {"code": 6, "width_m": 0.420, "height_m": 0.297},
    "A2": {"code": 7, "width_m": 0.594, "height_m": 0.420},
    "A1": {"code": 8, "width_m": 0.841, "height_m": 0.594},
    "A0": {"code": 9, "width_m": 1.189, "height_m": 0.841},
}

STANDARD_DRAWING_SCALES = (10.0, 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01)

# SolidWorks.Interop.swconst.swAlignDimensionType_e, confirmed through SW2026 Interop reflection.
ALIGN_DIMENSION_TYPES = {
    "auto_arrange": 0,
    "space_evenly": 1,
    "colinear": 2,
    "stagger": 3,
    "top_align_text": 4,
    "bottom_align_text": 5,
    "left_align_text": 6,
    "right_align_text": 7,
}

# SolidWorks.Interop.swconst.swAutoInsertCenterMarkTypes_e
# Cross-checked against SW2026 Interop reflection and official API help.
AUTO_CENTER_MARK_TARGETS = {
    "holes": 1,
    "fillets": 2,
    "slots": 4,
}


def _safe_member(obj, name, *args, default=None):
    """Read a drawing COM member, returning the default value on failure."""
    if obj is None:
        return default
    try:
        value = get_com_member(obj, name, *args)
        return default if value is None else value
    except Exception:
        return default


def _as_sequence(value):
    """Normalize COM arrays, tuples, and single-object results."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _normalise_box(value):
    """Normalize COM Outline/GetBox arrays into two-dimensional bounds."""
    if isinstance(value, dict) and {"left", "bottom", "right", "top"} <= set(value):
        try:
            x1, y1, x2, y2 = (float(value[key]) for key in ("left", "bottom", "right", "top"))
        except (TypeError, ValueError):
            return None
        return {"left": min(x1, x2), "bottom": min(y1, y2), "right": max(x1, x2), "top": max(y1, y2)}
    values = _as_sequence(value)
    try:
        if len(values) >= 6:
            x1, y1, x2, y2 = float(values[0]), float(values[1]), float(values[3]), float(values[4])
        elif len(values) >= 4:
            x1, y1, x2, y2 = map(float, values[:4])
        else:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "left": min(x1, x2),
        "bottom": min(y1, y2),
        "right": max(x1, x2),
        "top": max(y1, y2),
    }


def _annotation_box(owner):
    """Read two-dimensional bounds of dimension, note, or table annotations."""
    annotation = _safe_member(owner, "GetAnnotation") or owner
    return _normalise_box(_safe_member(annotation, "GetBox"))


def _view_display_dimensions(view):
    """Return real DisplayDimension objects from a view using array or linked-list interfaces."""
    dimensions = _as_sequence(_safe_member(view, "GetDisplayDimensions", default=[]))
    if dimensions:
        return dimensions
    current = _safe_member(view, "GetFirstDisplayDimension5") or _safe_member(view, "GetFirstDisplayDimension")
    while current is not None:
        dimensions.append(current)
        current = _safe_member(view, "GetNextDisplayDimension", current)
    return dimensions


def auto_arrange_drawing_dimensions(drawing_model, *, spacing_m=0.01, mode="auto_arrange") -> dict:
    """Automatically arrange each view's dimensions with SolidWorks AlignDimensions. This API controls native dimension layout but provides no dimension-text bounds and cannot prove that the final drawing has no overlap. Export PDF/BMP and perform a visual review afterward."""
    spacing, spacing_valid = _finite_positive(spacing_m, 0.01)
    if not spacing_valid or spacing > 0.1:
        raise ValueError("spacing_m, metre cinsinden (0, 0.1] aralığında sonlu bir sayı olmalıdır.")
    if mode not in ALIGN_DIMENSION_TYPES:
        raise ValueError(f"Bilinmeyen ölçü düzenleme modu: {mode}")
    extension = _safe_member(drawing_model, "Extension")
    if extension is None or not hasattr(extension, "AlignDimensions"):
        return {
            "status": "blocked",
            "stage": "arrange",
            "method": "IModelDocExtension.AlignDimensions",
            "mode": mode,
            "spacing_m": spacing,
            "views": [],
            "selected_dimension_count": 0,
            "manual_review_required": True,
            "retryable": False,
            "error_code": "DRAWING_ALIGN_DIMENSIONS_API_UNAVAILABLE",
        }

    results = []
    total_selected = 0
    sheets = _as_sequence(_safe_member(drawing_model, "GetSheetNames", default=[]))
    for sheet_name in sheets or [""]:
        sheet = _safe_member(drawing_model, "GetSheet", sheet_name) or _safe_member(drawing_model, "GetCurrentSheet")
        for view in _as_sequence(_safe_member(sheet, "GetViews", default=[])):
            dimensions = _view_display_dimensions(view)
            _safe_member(drawing_model, "ClearSelection2", True)
            selected = 0
            for dimension in dimensions:
                annotation = _safe_member(dimension, "GetAnnotation")
                if annotation is None:
                    continue
                selected_ok = _safe_member(annotation, "Select2", selected > 0, 0, default=False)
                if not selected_ok:
                    selected_ok = _safe_member(annotation, "Select", selected > 0, default=False)
                if selected_ok:
                    selected += 1
            attempted = selected >= 2
            aligned = False
            error = None
            if attempted:
                try:
                    aligned = bool(get_com_member(extension, "AlignDimensions", ALIGN_DIMENSION_TYPES[mode], spacing))
                except Exception as exc:
                    error = str(exc)
            results.append({
                "sheet": str(sheet_name),
                "view": str(_safe_member(view, "Name", default="") or ""),
                "dimension_count": len(dimensions),
                "selected_count": selected,
                "attempted": attempted,
                "aligned": aligned,
                "error": error,
            })
            total_selected += selected
    _safe_member(drawing_model, "ClearSelection2", True)
    _safe_member(drawing_model, "ForceRebuild3", False)
    _safe_member(drawing_model, "GraphicsRedraw2")
    attempted_results = [item for item in results if item["attempted"]]
    failed_results = [item for item in attempted_results if not item["aligned"]]
    if not attempted_results:
        status = "review_required"
        error_code = "DRAWING_ALIGN_DIMENSIONS_NOT_ENOUGH_PER_VIEW"
    elif failed_results:
        status = "review_required"
        error_code = "DRAWING_ALIGN_DIMENSIONS_PARTIAL"
    else:
        status = "pass"
        error_code = None
    return {
        "status": status,
        "stage": "arrange",
        "method": "IModelDocExtension.AlignDimensions",
        "mode": mode,
        "enum_value": ALIGN_DIMENSION_TYPES[mode],
        "spacing_m": spacing,
        "views": results,
        "selected_dimension_count": total_selected,
        "aligned_view_count": sum(1 for item in results if item["aligned"]),
        "manual_review_required": True,
        "retryable": bool(failed_results),
        "error_code": error_code,
        "limitations": ["Resmî hizalama API'si metin sınırlarını döndürmez; düzenlemeden sonra PDF/BMP görsel incelemesi gerekir."],
    }


def _finite_positive(value, default):
    """Convert a COM value to a finite positive number, otherwise use a conservative default."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default), False
    if not math.isfinite(number) or number <= 0:
        return float(default), False
    return number, True


def _dimension_text_evidence(display_dimension) -> dict:
    """Collect dimension text fragments without fabricating SolidWorks' final formatted text."""
    parts = []
    for index, label in ((0, "all"), (1, "prefix"), (2, "suffix"), (3, "callout_above"), (4, "callout_below")):
        value = str(_safe_member(display_dimension, "GetText", index, default="") or "")
        if value:
            parts.append({"index": index, "kind": label, "text": value})
    all_text = next((item["text"] for item in parts if item["kind"] == "all"), "")
    if all_text:
        lines = all_text.splitlines() or [all_text]
        source = "display_dimension_get_text_all"
        rendered_value_available = True
    else:
        explicit = [item["text"] for item in parts if item["kind"] != "all"]
        # In SW2026, GetText() often returns only user prefixes/suffixes rather than the formatted main dimension.
        # Use eight fixed-width characters as the main-value placeholder so an empty string is not estimated as zero width.
        lines = ["".join(explicit) + "0000.000"]
        source = "explicit_parts_plus_conservative_value_placeholder" if explicit else "conservative_value_placeholder"
        rendered_value_available = False
    return {
        "parts": parts,
        "estimation_lines": lines,
        "source": source,
        "rendered_value_available": rendered_value_available,
    }


def estimate_dimension_text_box(display_dimension, *, padding_m=None) -> dict:
    """Conservatively estimate dimension-text bounds from the IAnnotation anchor and ITextFormat. SW2026 has no native dimension-text bounding-box API. Return an axis-aligned enclosing square covering any rotation and explicitly mark source=estimated; this is not native geometry evidence."""
    annotation = _safe_member(display_dimension, "GetAnnotation")
    position = _as_sequence(_safe_member(annotation, "GetPosition", default=[]))
    try:
        x, y = float(position[0]), float(position[1])
        position_available = math.isfinite(x) and math.isfinite(y)
    except (IndexError, TypeError, ValueError):
        x = y = 0.0
        position_available = False

    text_format = _safe_member(annotation, "GetTextFormat", 0)
    format_source = "IAnnotation.GetTextFormat(0)"
    if text_format is None:
        text_format = _safe_member(display_dimension, "GetTextFormat")
        format_source = "IDisplayDimension.GetTextFormat()"
    char_height, char_height_available = _finite_positive(
        _safe_member(text_format, "CharHeight"),
        0.0035,
    )
    width_factor, width_factor_available = _finite_positive(
        _safe_member(text_format, "WidthFactor"),
        1.0,
    )
    spacing_factor, spacing_factor_available = _finite_positive(
        _safe_member(text_format, "CharSpacingFactor"),
        1.0,
    )
    text = _dimension_text_evidence(display_dimension)
    lines = text["estimation_lines"] or ["0000.000"]

    def line_units(line):
        """Estimate one line's width, counting CJK and full-width characters as one character-height wide."""
        units = 0.0
        for character in line or " ":
            units += 1.0 if ord(character) > 0xFF else 0.62
        return max(units, 0.62)

    max_units = max(line_units(line) for line in lines)
    line_count = max(1, len(lines))
    estimated_width = max_units * char_height * width_factor * spacing_factor
    estimated_height = line_count * char_height * 1.25
    padding = max(0.001, char_height * 0.4) if padding_m is None else max(0.0, float(padding_m))
    # The API does not expose the text angle; use the rectangle diagonal as a square envelope covering any rotation.
    half_extent = math.hypot(estimated_width, estimated_height) / 2.0 + padding
    box = None
    if position_available:
        box = {
            "left": x - half_extent,
            "bottom": y - half_extent,
            "right": x + half_extent,
            "top": y + half_extent,
        }

    available_fields = sum((position_available, char_height_available, width_factor_available, spacing_factor_available))
    if position_available and available_fields == 4 and text["rendered_value_available"]:
        confidence = "medium"
    elif position_available:
        confidence = "low"
    else:
        confidence = "unavailable"
    return {
        "box": box,
        "source": "estimated",
        "confidence": confidence,
        "method": "annotation_position_text_format_arbitrary_rotation_envelope",
        "native_bounding_box_available": False,
        "position_m": [x, y] if position_available else None,
        "text_evidence": text,
        "text_format": {
            "source": format_source if text_format is not None else "conservative_defaults",
            "char_height_m": char_height,
            "width_factor": width_factor,
            "char_spacing_factor": spacing_factor,
            "char_height_available": char_height_available,
            "width_factor_available": width_factor_available,
            "char_spacing_factor_available": spacing_factor_available,
        },
        "estimated_unrotated_size_m": {"width": estimated_width, "height": estimated_height},
        "padding_m": padding,
        "orientation_assumption": "unknown_angle_conservative_square_envelope",
        "limitations": [
            "SolidWorks 2026 IAnnotation, ölçü metni için özgün bounding box sağlamaz",
            "GetText biçimlendirilmiş ana ölçü değerini döndürmeyebilir; eksikse korumacı bir yer tutucu genişlik kullanılır",
            "Tahmin yalnızca çakışma riski taramasıdır; son teslim için PDF/BMP görsel incelemesi gerekir",
        ],
    }


def select_drawing_template(candidates, *, paper_size="A3", require_gbt=True) -> dict:
    """Select a locally available sheet-format template matching the paper size and GB/T naming. Treat filename/extension matching as candidate evidence only, not proof of compliant template content."""
    paper_size = str(paper_size).upper()
    if paper_size not in PAPER_SIZES:
        raise ValueError(f"Desteklenmeyen pafta boyutu: {paper_size}")
    inspected = []
    for raw_path in candidates or []:
        path = Path(raw_path).expanduser().resolve()
        name = path.stem.casefold()
        compact_name = re.sub(r"[^a-z0-9çğıöşü\u4e00-\u9fff]", "", name)
        is_format = path.suffix.casefold() == ".slddrt"
        paper_match = paper_size.casefold() in name
        gbt_match = (
            "gbt" in compact_name
            or "\u56fd\u6807" in compact_name
            or bool(re.search(r"(?:^|[^a-z0-9])gb(?:t)?(?:[^a-z0-9]|$)", name, re.IGNORECASE))
        )
        path_text = str(path).casefold()
        localized_candidate = any(token in path_text for token in ("chinese-simplified", "chinese_simplified", "\u7b80\u4f53\u4e2d\u6587"))
        score = int(path.is_file()) * 8 + int(is_format) * 4 + int(paper_match) * 2 + int(gbt_match) + int(localized_candidate) * 2
        inspected.append({
            "path": str(path),
            "exists": path.is_file(),
            "is_sheet_format": is_format,
            "paper_match": paper_match,
            "gbt_candidate": gbt_match,
            "localized_candidate": localized_candidate,
            "score": score,
        })
    eligible = [item for item in inspected if item["exists"] and item["is_sheet_format"] and item["paper_match"]]
    if require_gbt:
        eligible = [item for item in eligible if item["gbt_candidate"]]
    selected = max(eligible, key=lambda item: (item["score"], item["path"].casefold()), default=None)
    return {
        "status": "pass" if selected else "blocked",
        "paper_size": paper_size,
        "selected": selected["path"] if selected else None,
        "candidates": inspected,
        "gbt_content_verified": False,
        "manual_review_required": True,
        "error_code": None if selected else "DRAWING_GBT_TEMPLATE_MISSING" if require_gbt else "DRAWING_TEMPLATE_MISSING",
    }


def plan_standard_view_layout(
    model_size_m,
    *,
    paper_size="A3",
    projection="third_angle",
    requested_scale=None,
    margin_m=0.012,
    gap_m=0.018,
    title_block_width_m=0.180,
    title_block_height_m=0.055,
) -> dict:
    """Calculate an adaptive or explicit-scale three-view layout that avoids the title block."""
    paper_size = str(paper_size).upper()
    projection = str(projection).lower()
    if projection not in {"first_angle", "third_angle"}:
        raise ValueError("projection \u5fc5\u987b\u662f first_angle \u6216 third_angle")
    spec = PAPER_SIZES.get(paper_size)
    if spec is None:
        raise ValueError(f"Desteklenmeyen pafta boyutu: {paper_size}")
    try:
        width, height, depth = (float(item) for item in model_size_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("model_size_m metre cinsinden üç dış ölçü içermelidir") from exc
    if min(width, height, depth) <= 0 or not all(math.isfinite(item) for item in (width, height, depth)):
        raise ValueError("Modelin dış ölçüleri sonlu ve pozitif olmalıdır")

    sheet_width = spec["width_m"]
    sheet_height = spec["height_m"]
    working_left = margin_m
    working_bottom = margin_m + title_block_height_m + gap_m
    working_right = sheet_width - margin_m
    working_top = sheet_height - margin_m
    available_width = working_right - working_left
    available_height = working_top - working_bottom
    raw_scale = min(
        (available_width - gap_m) / (width + depth),
        (available_height - gap_m) / (height + depth),
    )
    if raw_scale <= 0:
        return {
            "status": "blocked",
            "paper_size": paper_size,
            "sheet": {"width_m": sheet_width, "height_m": sheet_height},
            "views": [],
            "manual_review_required": True,
            "retryable": True,
            "error_code": "DRAWING_LAYOUT_WORKING_AREA_INVALID",
        }
    if requested_scale is None:
        scale = next((item for item in STANDARD_DRAWING_SCALES if item <= raw_scale + 1e-12), raw_scale)
    else:
        try:
            if isinstance(requested_scale, str):
                numerator_text, denominator_text = requested_scale.split(":", 1)
                scale = float(numerator_text.strip()) / float(denominator_text.strip())
            else:
                scale = float(requested_scale)
        except (TypeError, ValueError, ZeroDivisionError):
            return {
                "status": "blocked",
                "paper_size": paper_size,
                "views": [],
                "manual_review_required": True,
                "retryable": False,
                "error_code": "DRAWING_SCALE_INVALID",
            }
        if scale <= 0 or not math.isfinite(scale):
            return {
                "status": "blocked",
                "paper_size": paper_size,
                "views": [],
                "manual_review_required": True,
                "retryable": False,
                "error_code": "DRAWING_SCALE_INVALID",
            }
        if scale > raw_scale + 1e-12:
            return {
                "status": "blocked",
                "paper_size": paper_size,
                "requested_scale": requested_scale,
                "maximum_fit_scale": raw_scale,
                "views": [],
                "manual_review_required": True,
                "retryable": True,
                "error_code": "DRAWING_SCALE_DOES_NOT_FIT",
            }

    front_w, front_h = width * scale, height * scale
    top_w, top_h = width * scale, depth * scale
    right_w, right_h = depth * scale, height * scale
    layout_w = front_w + gap_m + right_w
    layout_h = front_h + gap_m + top_h
    origin_x = working_left + max(0.0, (available_width - layout_w) / 2.0)
    origin_y = working_bottom + max(0.0, (available_height - layout_h) / 2.0)

    def view_record(name, left, bottom, view_width, view_height):
        """Create a record of one view's center and bounding box."""
        return {
            "name": name,
            "center": [left + view_width / 2.0, bottom + view_height / 2.0],
            "box": {"left": left, "bottom": bottom, "right": left + view_width, "top": bottom + view_height},
        }

    if projection == "first_angle":
        # GB/T first-angle projection: top view below front, right view to the left of front.
        views = [
            view_record("*Front", origin_x + right_w + gap_m, origin_y + top_h + gap_m, front_w, front_h),
            view_record("*Top", origin_x + right_w + gap_m, origin_y, top_w, top_h),
            view_record("*Right", origin_x, origin_y + top_h + gap_m, right_w, right_h),
        ]
    else:
        views = [
            view_record("*Front", origin_x, origin_y, front_w, front_h),
            view_record("*Top", origin_x, origin_y + front_h + gap_m, top_w, top_h),
            view_record("*Right", origin_x + front_w + gap_m, origin_y, right_w, right_h),
        ]
    title_box = {
        "left": sheet_width - margin_m - title_block_width_m,
        "bottom": margin_m,
        "right": sheet_width - margin_m,
        "top": margin_m + title_block_height_m,
    }
    return {
        "status": "pass",
        "paper_size": paper_size,
        "projection": projection,
        "gap_m": gap_m,
        "sheet": {"width_m": sheet_width, "height_m": sheet_height},
        "working_area": {"left": working_left, "bottom": working_bottom, "right": working_right, "top": working_top},
        "title_block_box": title_box,
        "scale": scale,
        "scale_ratio": list(_scale_ratio(scale)),
        "views": views,
        "manual_review_required": True,
    }


def _scale_ratio(scale):
    """Convert a floating-point scale into an integer ratio accepted by SolidWorks."""
    ratio = Fraction(float(scale)).limit_denominator(1000)
    return ratio.numerator, ratio.denominator


def _apply_view_layout(view, item, numerator, denominator) -> dict:
    """Move created views to planned centers and set their independent scales."""
    center = [float(item["center"][0]), float(item["center"][1])]
    if hasattr(view, "UseParentScale"):
        view.UseParentScale = False
    if hasattr(view, "PositionLocked"):
        view.PositionLocked = False
    view.ScaleRatio = (int(numerator), int(denominator))
    position = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, center)
    method = getattr(view, "SetViewPosition", None)
    if method is not None:
        moved = bool(get_com_member(view, "SetViewPosition", position, False))
        if not moved:
            raise RuntimeError(f"SetViewPosition başarısız: {center}")
    else:
        view.Position = position
    actual_position = _view_position(view)
    position_verified = bool(
        actual_position
        and abs(actual_position[0] - center[0]) <= 1e-5
        and abs(actual_position[1] - center[1]) <= 1e-5
    )
    if not position_verified:
        raise RuntimeError(f"Görünüş konumunun geri okuması tutarsız: requested={center}, actual={actual_position}")
    return {
        "name": item["name"],
        "actual_name": str(_safe_member(view, "Name", default="")),
        "orientation": str(_safe_member(view, "GetOrientationName", default="")),
        "center": center,
        "actual_center": list(actual_position),
        "position_verified": True,
        "scale_ratio": [int(numerator), int(denominator)],
    }


def _normalise_orientation(value):
    """Normalize SolidWorks standard-view orientations to front/top/right keys."""
    compact = re.sub(r"[^a-zçğıöşü\u4e00-\u9fff]", "", str(value or "").casefold())
    aliases = {
        "front": "front",
        "top": "top",
        "right": "right",
        "frontview": "front", "ön": "front", "öngörünüş": "front",
        "topview": "top", "üst": "top", "üstgörünüş": "top",
        "rightview": "right", "sağ": "right", "sağgörünüş": "right",
        "\u524d\u89c6": "front",
        "\u4e3b\u89c6": "front",
        "\u4e0a\u89c6": "top",
        "\u4fef\u89c6": "top",
        "\u53f3\u89c6": "right",
    }
    return aliases.get(compact)


def _view_position(view):
    """Read a drawing view's center position."""
    values = _as_sequence(_safe_member(view, "Position", default=[]))
    try:
        if len(values) < 2:
            return None
        return float(values[0]), float(values[1])
    except (IndexError, TypeError, ValueError):
        return None


def _set_view_center(view, center) -> list[float]:
    """Move a view and read back its center for reuse during layout from actual bounds."""
    target = [float(center[0]), float(center[1])]
    position = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, target)
    method = getattr(view, "SetViewPosition", None)
    if method is not None:
        moved = bool(get_com_member(view, "SetViewPosition", position, False))
        if not moved:
            raise RuntimeError(f"SetViewPosition başarısız: {target}")
    else:
        view.Position = position
    actual = _view_position(view)
    if actual is None or abs(actual[0] - target[0]) > 1e-5 or abs(actual[1] - target[1]) > 1e-5:
        raise RuntimeError(f"Görünüş konumunun geri okuması tutarsız: requested={target}, actual={actual}")
    return [float(actual[0]), float(actual[1])]


def _refine_standard_view_spacing(view_objects, view_records, projection, gap_m=0.018) -> dict:
    """Remove confirmed three-view overlaps using actual SolidWorks view bounds."""
    required = {"front", "top", "right"}
    if set(view_objects) < required:
        return {"status": "review_required", "method": "native_outline", "adjustments": [], "error_code": "DRAWING_VIEW_OUTLINES_INCOMPLETE"}
    boxes = {key: _normalise_box(_safe_member(view, "GetOutline")) for key, view in view_objects.items()}
    if any(box is None for box in boxes.values()):
        return {"status": "review_required", "method": "native_outline", "adjustments": [], "error_code": "DRAWING_VIEW_OUTLINES_INCOMPLETE"}
    try:
        gap = max(0.001, float(gap_m))
    except (TypeError, ValueError):
        gap = 0.018
    records = {item["name"]: item for item in view_records}
    names = {"front": "*Front", "top": "*Top", "right": "*Right"}
    adjustments = []

    def move_if_needed(axis, orientation, target_value):
        current_box = boxes[orientation]
        current_center = _view_position(view_objects[orientation])
        if current_center is None:
            return
        delta = float(target_value) - current_center[axis]
        if abs(delta) <= 1e-7:
            return
        new_center = list(current_center)
        new_center[axis] = float(target_value)
        actual_center = _set_view_center(view_objects[orientation], new_center)
        moved_box = _normalise_box(_safe_member(view_objects[orientation], "GetOutline"))
        boxes[orientation] = moved_box or current_box
        record = records.get(names[orientation])
        if record is not None:
            record["center"] = list(actual_center)
            record["actual_center"] = list(actual_center)
            record["layout_refined_from_native_outline"] = True
        adjustments.append({"view": names[orientation], "axis": "x" if axis == 0 else "y", "delta_m": delta, "center": list(actual_center)})

    front = boxes["front"]
    right = boxes["right"]
    top = boxes["top"]
    right_width = right["right"] - right["left"]
    top_height = top["top"] - top["bottom"]
    if projection == "first_angle":
        right_target_x = front["left"] - gap - right_width / 2.0
        top_target_y = front["bottom"] - gap - top_height / 2.0
    else:
        right_target_x = front["right"] + gap + right_width / 2.0
        top_target_y = front["top"] + gap + top_height / 2.0
    move_if_needed(0, "right", right_target_x)
    move_if_needed(1, "top", top_target_y)
    return {
        "status": "pass",
        "method": "native_outline",
        "projection": projection,
        "gap_m": gap,
        "adjustments": adjustments,
        "error_code": None,
        "manual_review_required": True,
    }


def _collect_drawing_views(drawing_model):
    """Read actual model views through both Sheet.GetViews and the GetFirstView chain."""
    sheet = _safe_member(drawing_model, "GetCurrentSheet")
    views = _as_sequence(_safe_member(sheet, "GetViews", default=[]))
    if len(views) >= 3:
        return views
    traversed = []
    sheet_view = _safe_member(drawing_model, "GetFirstView")
    current = _safe_member(sheet_view, "GetNextView")
    guard = 0
    while current is not None and guard < 1000:
        traversed.append(current)
        current = _safe_member(current, "GetNextView")
        guard += 1
    return traversed if len(traversed) >= len(views) else views


def _map_native_standard_views(views):
    """Map third-angle views using orientation names, base-view relationships, and original positions."""
    by_orientation = {}
    diagnostics = []
    for view in views:
        orientation_name = str(_safe_member(view, "GetOrientationName", default=""))
        orientation = _normalise_orientation(orientation_name)
        base_view = _safe_member(view, "GetBaseView")
        position = _view_position(view)
        diagnostics.append({
            "name": str(_safe_member(view, "Name", default="")),
            "orientation": orientation_name,
            "position": list(position) if position else None,
            "has_base_view": base_view is not None,
            "referenced_model": str(_safe_member(view, "GetReferencedModelName", default="")),
        })
        if orientation and orientation not in by_orientation:
            by_orientation[orientation] = view
    if set(by_orientation) >= {"front", "top", "right"}:
        return by_orientation, diagnostics, "orientation_name"

    positioned = [(view, _view_position(view), _safe_member(view, "GetBaseView")) for view in views]
    positioned = [item for item in positioned if item[1] is not None]
    if len(positioned) >= 3:
        base_candidates = [item for item in positioned if item[2] is None]
        front = min(base_candidates or positioned, key=lambda item: item[1][0] + item[1][1])
        remaining = [item for item in positioned if item[0] is not front[0]]
        top = max(remaining, key=lambda item: item[1][1] - front[1][1])
        right_candidates = [item for item in remaining if item[0] is not top[0]]
        if right_candidates:
            right = max(right_candidates, key=lambda item: item[1][0] - front[1][0])
            return {"front": front[0], "top": top[0], "right": right[0]}, diagnostics, "base_and_position"
    return by_orientation, diagnostics, "unresolved"


def _map_standard_views_from_sheet_views(sheet_views):
    """Filter and map front, top, and right standard views from all sheet views."""
    oriented_fronts = [
        view for view in sheet_views
        if _normalise_orientation(_safe_member(view, "GetOrientationName", default="")) == "front"
    ]
    base_candidates = oriented_fronts or [
        view for view in sheet_views
        if _safe_member(view, "Type", default=None) == 7 and _safe_member(view, "GetBaseView") is None
    ]
    standard_candidates = [*base_candidates, *[
        view for view in sheet_views if _safe_member(view, "Type", default=None) == 4
    ]]
    return _map_native_standard_views(standard_candidates)


def create_adaptive_standard_views(drawing_model, part_path, layout) -> dict:
    """Create actual front, top, and right drawing views from the precomputed layout."""
    created = []
    view_objects = {}
    numerator, denominator = layout.get("scale_ratio") or _scale_ratio(layout["scale"])
    for item in layout.get("views", []):
        center = item["center"]
        view = drawing_model.CreateDrawViewFromModelView3(part_path, item["name"], center[0], center[1], 0)
        if view is None:
            if not created:
                projection = str(layout.get("projection", "third_angle")).lower()
                # Some SolidWorks versions, including the current SW2026 COM proxy, lack
                # CreateFirstAngleViews2. First create views using the available native three-view API,
                # then reposition them according to DrawingSpec first-/third-angle layout and read back the positions.
                method_candidates = (
                    ("CreateFirstAngleViews2", "Create3rdAngleViews2")
                    if projection == "first_angle"
                    else ("Create3rdAngleViews2",)
                )
                native_created = False
                method_name = None
                for candidate in method_candidates:
                    if bool(_safe_member(drawing_model, candidate, str(part_path), default=False)):
                        native_created = True
                        method_name = candidate
                        break
                if native_created:
                    _safe_member(drawing_model, "ForceRebuild3", False)
                    _safe_member(drawing_model, "GraphicsRedraw2")
                    native_views = _collect_drawing_views(drawing_model)
                    by_orientation, diagnostics, mapping_method = _map_native_standard_views(native_views)
                    expected = {"front": "*Front", "top": "*Top", "right": "*Right"}
                    if set(by_orientation) >= set(expected):
                        layout_by_name = {entry["name"]: entry for entry in layout.get("views", [])}
                        try:
                            for orientation in ("front", "top", "right"):
                                view_objects[orientation] = by_orientation[orientation]
                                created.append(
                                    _apply_view_layout(
                                        by_orientation[orientation],
                                        layout_by_name[expected[orientation]],
                                        numerator,
                                        denominator,
                                    )
                                )
                        except Exception as exc:
                            return {
                                "status": "failed",
                                "stage": "layout",
                                "backend": f"native_{projection}",
                                "views": created,
                                "native_view_diagnostics": diagnostics,
                                "retryable": True,
                                "error_code": "DRAWING_VIEW_POSITION_FAILED",
                                "error": str(exc),
                            }
                        refinement = _refine_standard_view_spacing(
                            view_objects,
                            created,
                            projection,
                            layout.get("gap_m", 0.018),
                        )
                        backend = (
                            "native_3rd_angle"
                            if projection == "third_angle"
                            else "native_first_angle"
                            if method_name == "CreateFirstAngleViews2"
                            else "native_first_angle_via_3rd_angle"
                        )
                        return {
                            "status": "pass",
                            "stage": "create",
                            "backend": backend,
                            "creation_method": method_name,
                            "mapping_method": mapping_method,
                            "native_view_diagnostics": diagnostics,
                            "layout_refinement": refinement,
                            "views": created,
                            "view_count": len(created),
                            "retryable": False,
                            "error_code": None,
                            "manual_review_required": True,
                        }
                    return {
                        "status": "failed",
                        "stage": "map",
                        "backend": f"native_{projection}",
                        "views": [],
                        "orientations_found": sorted(by_orientation),
                        "mapping_method": mapping_method,
                        "native_view_diagnostics": diagnostics,
                        "retryable": True,
                        "error_code": "DRAWING_VIEW_ORIENTATION_MAP_FAILED",
                    }
            return {
                "status": "failed",
                "stage": "create",
                "views": created,
                "retryable": True,
                "error_code": "DRAWING_VIEW_CREATE_FAILED",
            }
        try:
            orientation = _normalise_orientation(item["name"])
            if orientation:
                view_objects[orientation] = view
            created.append(_apply_view_layout(view, item, numerator, denominator))
        except Exception as exc:
            return {
                "status": "failed",
                "stage": "layout",
                "backend": "individual_model_views",
                "views": created,
                "retryable": True,
                "error_code": "DRAWING_VIEW_POSITION_FAILED",
                "error": str(exc),
            }
    refinement = _refine_standard_view_spacing(
        view_objects,
        created,
        str(layout.get("projection", "third_angle")).lower(),
        layout.get("gap_m", 0.018),
    )
    return {
        "status": "pass",
        "stage": "create",
        "backend": "individual_model_views",
        "views": created,
        "layout_refinement": refinement,
        "view_count": len(created),
        "retryable": False,
        "error_code": None,
        "manual_review_required": True,
    }


def create_standard_views(drawing_model, part_path):
    """Create standard third-angle views. drawing_model is IDrawingDoc; part_path is the part-file path."""
    return drawing_model.Create3rdAngleViews2(part_path)


def create_standard_views_with_projection(drawing_model, part_path, projection="first_angle"):
    """Create native three-view projections using the specified method and return explicit failure states."""
    projection = str(projection).lower()
    if projection not in {"first_angle", "third_angle"}:
        raise ValueError("projection \u5fc5\u987b\u662f first_angle \u6216 third_angle")
    method_name = "CreateFirstAngleViews2" if projection == "first_angle" else "Create3rdAngleViews2"
    method = getattr(drawing_model, method_name, None)
    if method is None:
        return {
            "status": "blocked",
            "projection": projection,
            "method": method_name,
            "error_code": "DRAWING_PROJECTION_API_UNAVAILABLE",
            "manual_review_required": True,
        }
    created = bool(method(part_path))
    return {
        "status": "pass" if created else "failed",
        "projection": projection,
        "method": method_name,
        "created": created,
        "error_code": None if created else "DRAWING_STANDARD_VIEWS_CREATE_FAILED",
        "manual_review_required": True,
    }


def add_view(drawing_model, part_path, view_name, x, y, scale=None):
    """Add a view. view_name accepts *Front, *Back, *Top, *Bottom, *Left, *Right, *Isometric, *Trimetric, or *Dimetric. x/y are placement coordinates in meters. scale is a ratio (0.5 means 1:2); None uses the sheet default."""
    view = drawing_model.CreateDrawViewFromModelView3(
        part_path, view_name, x, y, 0
    )
    if view and scale:
        view.ScaleRatio = (1.0, 1.0 / scale)
    return view


def add_section_view(drawing_model, x, y):
    """Create a section view at the currently selected cutting line."""
    return drawing_model.CreateSectionViewAt5(x, y, 0, "", 0, None, 0)


def add_detail_view(drawing_model, x, y, scale=2.0):
    """Create a magnified detail view."""
    return drawing_model.CreateDetailViewAt4(x, y, 0, 0, scale, 0, "")


def insert_dimensions(drawing_model, view=None):
    """Insert automatic dimensions from model items. view is the target view object; None annotates all views."""
    # SolidWorks 2024 added InsertModelAnnotations4, which returns the inserted IAnnotation
    # array. Older versions/dynamic proxies may expose only InsertModelAnnotations3. Prefer 4,
    # then fall back to 3; a True return value alone does not prove that dimensions were inserted.
    # SW2024 swInsertAnnotation_e: 32768 means model dimensions marked for drawing.
    # 8 is the general dimension type; 524288 means unmarked dimensions. This SW2024 installation silently
    # returns None for their combination, while 32768 returns actual IAnnotation objects.
    args4 = (
        0,          # swImportModelItemsFromEntireModel
        32768,      # swInsertDimensionsMarkedForDrawing
        True, False, False, False,
        False, False,
    )
    args3 = args4[:6]
    # The official API example first activates a drawing view; SW2024 silently returns empty results without activation.
    try:
        sheet = _safe_member(drawing_model, "GetCurrentSheet")
        views = _as_sequence(_safe_member(sheet, "GetViews", default=[]))
        if views:
            # The first three-view item is usually front; use the known order if reading Name fails,
            # but still require SelectByID2/ActivateView to return success.
            first_view = views[0]
            name = _safe_member(first_view, "Name", default="")
            if name:
                extension = getattr(drawing_model, "Extension", None)
                if extension is not None:
                    get_com_member(
                        extension, "SelectByID2",
                        name, "DRAWINGVIEW", 0, 0, 0, False, 0,
                        create_empty_dispatch_variant(), 0,
                    )
                get_com_member(drawing_model, "ActivateView", name)
    except Exception:
        # Continue after activation failure and let structural review determine whether actual dimension evidence exists.
        pass
    owners = (drawing_model, getattr(drawing_model, "Extension", None))
    for owner in owners:
        if owner is None:
            continue
        try:
            method4 = getattr(owner, "InsertModelAnnotations4", None)
            if method4 is not None:
                inserted = get_com_member(owner, "InsertModelAnnotations4", *args4)
                if inserted is not None:
                    return inserted
            method3 = getattr(owner, "InsertModelAnnotations3", None)
            if method3 is not None:
                return get_com_member(owner, "InsertModelAnnotations3", *args3)
        except (AttributeError, TypeError, pythoncom.com_error):
            continue
    # After creating views, SW2024 may not yet have an importable view cache. Force a rebuild and retry
    # once. Marked-for-drawing and deduplication semantics prevent repeated calls from creating duplicate dimensions.
    try:
        get_com_member(drawing_model, "ForceRebuild3", False)
        get_com_member(drawing_model, "GraphicsRedraw2")
        for owner in owners:
            if owner is not None and getattr(owner, "InsertModelAnnotations4", None) is not None:
                inserted = get_com_member(owner, "InsertModelAnnotations4", *args4)
                if inserted is not None:
                    return inserted
    except (AttributeError, TypeError, pythoncom.com_error):
        pass
    # The caller may continue structural review but must report missing actual dimension evidence as warning.
    return False


def _note_text(note):
    """Read actual INote text, including dynamic COM proxies that omit member names."""
    text = _safe_member(note, "GetText")
    if isinstance(text, str):
        return text
    ole_object = getattr(note, "_oleobj_", None)
    if ole_object is None:
        return ""
    try:
        # SW2026 sldworks.tlb: INote.GetText has DISPID 2 and returns BSTR.
        return str(ole_object.InvokeTypes(2, 0, 1, (8, 0), ()) or "")
    except Exception:
        return ""


def _note_annotation(note):
    """Get the INote IAnnotation, invoking the type-library member when dynamic COM does not expose it."""
    annotation = _safe_member(note, "GetAnnotation")
    if annotation is not None:
        return annotation
    ole_object = getattr(note, "_oleobj_", None)
    if ole_object is None:
        return None
    try:
        # SW2026 sldworks.tlb: INote.GetAnnotation has DISPID 85.
        from win32com.client.dynamic import Dispatch

        return Dispatch(ole_object.InvokeTypes(85, 0, 1, (9, 0), ()))
    except Exception:
        return None


def _set_annotation_position(annotation, x, y, z=0.0):
    """Set IAnnotation sheet coordinates and return the SolidWorks boolean result."""
    try:
        result = get_com_member(annotation, "SetPosition2", x, y, z)
        if isinstance(result, bool):
            return result
    except Exception:
        pass
    ole_object = getattr(annotation, "_oleobj_", None)
    if ole_object is None:
        return False
    try:
        # SW2026 sldworks.tlb: IAnnotation.SetPosition2 has DISPID 91.
        return bool(ole_object.InvokeTypes(91, 0, 1, (11, 0), ((5, 1), (5, 1), (5, 1)), x, y, z))
    except Exception:
        return False


def _annotation_position(annotation):
    """Read back IAnnotation sheet coordinates; return None when unavailable."""
    position = _safe_member(annotation, "GetPosition")
    values = _as_sequence(position)
    try:
        x, y = float(values[0]), float(values[1])
    except (IndexError, TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return [x, y, float(values[2]) if len(values) > 2 else 0.0]


def _note_box(note, annotation):
    """Prefer INote sheet-space extents, falling back to generic annotation bounds."""
    extent = _safe_member(note, "GetExtent")
    if extent is None:
        ole_object = getattr(note, "_oleobj_", None)
        if ole_object is not None:
            try:
                # SW2026 sldworks.tlb: INote.GetExtent has DISPID 22.
                extent = ole_object.InvokeTypes(22, 0, 1, (12, 0), ())
            except Exception:
                extent = None
    return _normalise_box(extent) or _annotation_box(annotation)


def _note_evidence(note):
    """Collect note text, positions, and bounds as drawing structural evidence."""
    annotation = _note_annotation(note)
    return {
        "text": _note_text(note),
        "position_m": _annotation_position(annotation),
        "box": _note_box(note, annotation),
    }


def add_note(drawing_model, x, y, text):
    """Create and verify a drawing text note. drawing_model is an IModelDoc2 drawing; x/y are anchor coordinates in meters; text must be nonempty. Return auditable COM read-back text, coordinates, and bounds."""
    expected_text = str(text)
    if not expected_text.strip() or not all(math.isfinite(float(value)) for value in (x, y)):
        return {
            "text": expected_text,
            "created": False,
            "status": "failed",
            "error_code": "DRAWING_NOTE_INPUT_INVALID",
        }
    note = _safe_member(drawing_model, "InsertNote", expected_text)
    if note is None:
        return {
            "text": expected_text,
            "created": False,
            "status": "failed",
            "error_code": "DRAWING_NOTE_INSERT_FAILED",
        }
    annotation = _note_annotation(note)
    positioned = _set_annotation_position(annotation, float(x), float(y)) if annotation is not None else False
    if positioned:
        # Refresh text and coordinates; bounds must still be read during structural review after re-enumerating views.
        _safe_member(drawing_model, "ForceRebuild3", False)
    evidence = _note_evidence(note)
    position = evidence.get("position_m") or []
    text_matches = evidence.get("text") == expected_text
    position_matches = (
        len(position) >= 2
        and math.isclose(position[0], float(x), abs_tol=1e-6)
        and math.isclose(position[1], float(y), abs_tol=1e-6)
    )
    verified = bool(positioned and text_matches and position_matches)
    return {
        "text": expected_text,
        "created": True,
        "position_requested_m": [float(x), float(y), 0.0],
        "positioned": positioned,
        "text_evidence": evidence.get("text"),
        "position_evidence_m": position,
        "box": None,
        "box_source": "deferred_to_structure_inspection",
        "verified": verified,
        "status": "pass" if verified else "failed",
        "error_code": None if verified else "DRAWING_NOTE_COM_EVIDENCE_MISSING",
    }


def insert_bom_table(drawing_model, template_path, x, y, bom_type=1, config_name=""):
    """Insert a BOM table. template_path is a .sldbomtbt template; x/y are placement coordinates in meters. bom_type: 1=top-level, 2=parts-only, 3=indented. config_name specifies the configuration."""
    return drawing_model.InsertBomTable4(
        template_path, x, y, bom_type, config_name, "", False
    )


def set_sheet_format(drawing_model, format_path):
    """Set the sheet format (drawing frame). format_path points to a .slddrt file."""
    sheet = drawing_model.GetCurrentSheet()
    return sheet.SetTemplateName(format_path)


def add_sheet(drawing_model, paper_size=7, template_path="", first_angle=True):
    """Add a sheet. paper_size: 0=A, 1=B, 2=C, 3=D, 4=E, 5=A4, 6=A3, 7=A2, 8=A1, 9=A0. template_path points to a sheet-format template."""
    return drawing_model.NewSheet4(
        "", paper_size, 12, 1.0, 1.0, bool(first_angle), template_path, 0, 0, "", 0, 0, 0, 0, 0, 0
    )


def add_a3_sheet(drawing_model, template_candidates, *, require_gbt=True, projection="first_angle") -> dict:
    """Select a local A3 sheet format and create a landscape A3 drawing sheet."""
    selection = select_drawing_template(template_candidates, paper_size="A3", require_gbt=require_gbt)
    if selection["selected"] is None:
        return {
            **selection,
            "stage": "preflight",
            "retryable": True,
            "created": False,
        }
    created = bool(add_sheet(
        drawing_model,
        paper_size=PAPER_SIZES["A3"]["code"],
        template_path=selection["selected"],
        first_angle=str(projection).lower() == "first_angle",
    ))
    return {
        **selection,
        "status": "pass" if created else "failed",
        "stage": "create",
        "retryable": not created,
        "created": created,
        "projection": str(projection).lower(),
        "error_code": None if created else "DRAWING_A3_SHEET_CREATE_FAILED",
    }


def setup_current_sheet_as_a3(drawing_model, template_candidates, *, require_gbt=True, projection="first_angle") -> dict:
    """Set the current sheet to landscape A3 using IDrawingDoc.SetupSheet6."""
    selection = select_drawing_template(template_candidates, paper_size="A3", require_gbt=require_gbt)
    if selection["selected"] is None:
        return {
            **selection,
            "stage": "preflight",
            "retryable": True,
            "configured": False,
        }
    sheet = _safe_member(drawing_model, "GetCurrentSheet")
    sheet_name = str(_safe_member(sheet, "GetName", default="") or "")
    if not sheet_name:
        return {
            **selection,
            "status": "blocked",
            "stage": "preflight",
            "retryable": True,
            "configured": False,
            "error_code": "DRAWING_CURRENT_SHEET_MISSING",
        }
    projection = str(projection).lower()
    if projection not in {"first_angle", "third_angle"}:
        raise ValueError("projection \u5fc5\u987b\u662f first_angle \u6216 third_angle")
    try:
        configured = bool(get_com_member(
            drawing_model,
            "SetupSheet6",
            sheet_name,
            PAPER_SIZES["A3"]["code"],
            12,
            1.0,
            1.0,
            projection == "first_angle",
            selection["selected"],
            0.0,
            0.0,
            "",
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            0,
        ))
    except Exception as exc:
        return {
            **selection,
            "status": "failed",
            "stage": "create",
            "retryable": True,
            "configured": False,
            "error_code": "DRAWING_A3_SETUP_FAILED",
            "error": str(exc),
        }
    return {
        **selection,
        "status": "pass" if configured else "failed",
        "stage": "create",
        "retryable": not configured,
        "configured": configured,
        "sheet_name": sheet_name,
        "projection": projection,
        "error_code": None if configured else "DRAWING_A3_SETUP_FAILED",
    }


def get_all_views(drawing_model):
    """Get all views on the current sheet."""
    sheet = get_com_member(drawing_model, "GetCurrentSheet")
    views = get_com_member(sheet, "GetViews")
    result = []
    if views:
        for view in views:
            result.append({
                "name": view.Name,
                "type": view.Type,
                "scale": view.ScaleRatio,
            })
    return result


def _paper_size_from_template(template_path):
    """Infer a standard paper size from the template filename, returning None when unknown."""
    name = Path(str(template_path or "")).stem.upper()
    for paper_size in PAPER_SIZES:
        if re.search(rf"(?:^|[^A-Z0-9]){paper_size}(?:[^A-Z0-9]|$)", name):
            return paper_size
    return None


TABLE_ANNOTATION_KINDS = {
    0: "general",
    1: "hole_chart",
    2: "bom",
    3: "revision",
    4: "weldment_cut_list",
    5: "title_block",
    6: "general_tolerance",
}


def _table_cell_text(table, row, column):
    """Read displayed table text, preferring newer interfaces with older ones as fallback."""
    for member, args in (
        ("DisplayedText2", (row, column, False)),
        ("DisplayedText", (row, column)),
        ("Text2", (row, column, False)),
        ("Text", (row, column)),
    ):
        value = _safe_member(table, member, *args, default=None)
        if value is not None:
            return str(value)
    return ""


def _table_evidence(table, sheet_name):
    """Read back table type, data rows, cells, and BOM configuration evidence."""
    table_type = _safe_member(table, "Type", default=None)
    try:
        normalized_type = int(table_type)
    except (TypeError, ValueError):
        normalized_type = table_type
    try:
        row_count = int(_safe_member(table, "RowCount", default=0) or 0)
        column_count = int(_safe_member(table, "ColumnCount", default=0) or 0)
    except (TypeError, ValueError):
        row_count, column_count = 0, 0
    cells = []
    if 0 < row_count <= 500 and 0 < column_count <= 100 and row_count * column_count <= 5000:
        cells = [
            [_table_cell_text(table, row, column) for column in range(column_count)]
            for row in range(row_count)
        ]
    configuration = ""
    if normalized_type == 2:
        bom_feature = _safe_member(table, "BomFeature", default=None)
        configuration = str(_safe_member(bom_feature, "Configuration", default="") or "")
    return {
        "sheet": str(sheet_name),
        "type": normalized_type,
        "kind": TABLE_ANNOTATION_KINDS.get(normalized_type, "unknown"),
        "title": str(_safe_member(table, "Title", default="") or ""),
        "row_count": row_count,
        "column_count": column_count,
        "configuration": configuration,
        "cells": cells,
        "box": _annotation_box(table),
    }


def _annotation_text_parts(annotation_owner):
    """Read visible professional-annotation text fragments in their original order."""
    try:
        count = int(_safe_member(annotation_owner, "GetTextCount", default=0) or 0)
    except (TypeError, ValueError):
        count = 0
    if not 0 <= count <= 1000:
        count = 0
    parts = []
    for index in range(count):
        text = str(_safe_member(annotation_owner, "GetTextAtIndex", index, default="") or "")
        if text:
            parts.append(text)
    return parts


def _professional_annotation_record(owner, kind, view_record):
    """Build professional-annotation evidence with owning view, text, and bounds."""
    return {
        "kind": kind,
        "sheet": view_record["sheet"],
        "view": view_record["name"],
        "semantic_view": view_record.get("semantic_view") or "",
        "text_parts": _annotation_text_parts(owner),
        "box": _annotation_box(owner),
    }


def first_center_mark(view):
    """Fall back to older interfaces only for missing members; propagate actual call errors."""
    for name in ("GetFirstCenterMark2", "GetFirstCenterMark"):
        value = get_com_member(view, name, default=None)
        if value is not None:
            return value
    return None


def _view_center_marks(view):
    """Iterate view center marks, supporting read-back interfaces older than SW2025 SP1."""
    current = first_center_mark(view)
    marks = []
    seen = set()
    while current is not None and len(marks) < 10000:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        marks.append(current)
        current = _safe_member(current, "GetNext")
    if marks:
        return marks
    # GetCenterMarks cannot return annotation-based center marks; use it only as a legacy fallback.
    return _as_sequence(_safe_member(view, "GetCenterMarks", default=[]))


def _collect_view_professional_annotations(view, view_record):
    """Collect professional annotations using IView read-back interfaces confirmed through SW2026 Interop reflection."""
    result = {
        "center_marks": [],
        "center_lines": [],
        "datum_tags": [],
        "geometric_tolerances": [],
        "surface_finish_symbols": [],
        "weld_symbols": [],
    }
    for owner in _view_center_marks(view):
        record = _professional_annotation_record(owner, "center_mark", view_record)
        record.update({
            "size_m": _safe_member(owner, "Size", default=None),
            "show_lines": _safe_member(owner, "ShowLines", default=None),
            "style": _safe_member(owner, "Style", default=None),
        })
        result["center_marks"].append(record)
    for owner in _as_sequence(_safe_member(view, "GetCenterLines", default=[])):
        result["center_lines"].append(_professional_annotation_record(owner, "center_line", view_record))
    for owner in _as_sequence(_safe_member(view, "GetDatumTags", default=[])):
        record = _professional_annotation_record(owner, "datum", view_record)
        record["label"] = str(_safe_member(owner, "GetLabel", default="") or "")
        result["datum_tags"].append(record)
    for owner in _as_sequence(_safe_member(view, "GetGTols", default=[])):
        record = _professional_annotation_record(owner, "geometric_tolerance", view_record)
        try:
            frame_count = int(_safe_member(owner, "GetFrameCount", default=0) or 0)
        except (TypeError, ValueError):
            frame_count = 0
        frame_count = frame_count if 0 <= frame_count <= 100 else 0
        record["datum_identifier"] = str(_safe_member(owner, "GetDatumIdentifier", default="") or "")
        record["frames"] = [
            {
                "index": index,
                "symbols": _as_sequence(_safe_member(owner, "GetFrameSymbols3", index, default=[])),
                "values": _as_sequence(_safe_member(owner, "GetFrameValues", index, default=[])),
            }
            for index in range(frame_count)
        ]
        result["geometric_tolerances"].append(record)
    for owner in _as_sequence(_safe_member(view, "GetSFSymbols", default=[])):
        record = _professional_annotation_record(owner, "surface_finish", view_record)
        record.update({
            "symbol_type": _safe_member(owner, "GetSymbolType", default=None),
            "symbol": _safe_member(owner, "GetSymbol", default=None),
            "direction_of_lay": _safe_member(owner, "GetDirectionOfLay", default=None),
        })
        result["surface_finish_symbols"].append(record)
    for owner in _as_sequence(_safe_member(view, "GetWeldSymbols", default=[])):
        result["weld_symbols"].append(_professional_annotation_record(owner, "weld_symbol", view_record))
    return result


def inspect_drawing_structure(drawing_model, *, paper_size_hint=None, title_block_box=None) -> dict:
    """Read drawing structure and return an auditable report without modifying the document."""
    sheets = _as_sequence(_safe_member(drawing_model, "GetSheetNames", default=[]))
    if not sheets:
        current_sheet = _safe_member(drawing_model, "GetCurrentSheet")
        current_name = _safe_member(current_sheet, "GetName", default="")
        if current_name:
            sheets = [current_name]
    views = []
    dimensions = []
    notes = []
    tables = []
    professional_annotations = {
        "center_marks": [],
        "center_lines": [],
        "hole_callouts": [],
        "datum_tags": [],
        "geometric_tolerances": [],
        "surface_finish_symbols": [],
        "weld_symbols": [],
    }
    for sheet_name in sheets or [""]:
        sheet = _safe_member(drawing_model, "GetSheet", sheet_name) or _safe_member(drawing_model, "GetCurrentSheet")
        sheet_views = _as_sequence(_safe_member(sheet, "GetViews", default=[]))
        mapped_views, _, _ = _map_standard_views_from_sheet_views(sheet_views)
        semantic_by_object = {id(view): name for name, view in mapped_views.items()}
        for view in sheet_views:
            view_record = {
                "sheet": str(sheet_name),
                "name": _safe_member(view, "Name", default=""),
                "type": _safe_member(view, "Type", default=None),
                "orientation": _safe_member(view, "GetOrientationName", default=""),
                "semantic_view": semantic_by_object.get(id(view), ""),
                "scale": _safe_member(view, "ScaleRatio", default=None),
                "box": _normalise_box(_safe_member(view, "GetOutline")),
            }
            views.append(view_record)
            view_annotations = _collect_view_professional_annotations(view, view_record)
            for key, records in view_annotations.items():
                professional_annotations[key].extend(records)
            view_dimensions = _view_display_dimensions(view)
            for dimension in view_dimensions:
                native_box = _annotation_box(dimension)
                estimated_box_evidence = estimate_dimension_text_box(dimension) if native_box is None else None
                dimension_record = {
                    "sheet": str(sheet_name),
                    "view": _safe_member(view, "Name", default=""),
                    "semantic_view": view_record["semantic_view"],
                    "name": (
                        _safe_member(dimension, "Name", default="")
                        or _safe_member(dimension, "GetNameForSelection", default="")
                        or _safe_member(_safe_member(dimension, "GetDimension"), "FullName", default="")
                    ),
                    "type": _safe_member(dimension, "Type", default=None),
                    "text": _safe_member(dimension, "GetText", 0, default=""),
                    "box": native_box or estimated_box_evidence.get("box"),
                    "box_source": "native" if native_box else estimated_box_evidence.get("source"),
                    "box_confidence": "high" if native_box else estimated_box_evidence.get("confidence"),
                    "box_evidence": {
                        "box": native_box,
                        "source": "native",
                        "confidence": "high",
                        "method": "annotation_get_box",
                    } if native_box else estimated_box_evidence,
                    "is_hole_callout": bool(_safe_member(dimension, "IsHoleCallout", default=False)),
                    "hole_callout_variables": _as_sequence(_safe_member(dimension, "GetHoleCalloutVariables", default=[])),
                }
                dimensions.append(dimension_record)
                if dimension_record["is_hole_callout"]:
                    professional_annotations["hole_callouts"].append({
                        "kind": "hole_callout",
                        "sheet": dimension_record["sheet"],
                        "view": dimension_record["view"],
                        "semantic_view": dimension_record["semantic_view"],
                        "name": dimension_record["name"],
                        "text_parts": [dimension_record["text"]] if dimension_record["text"] else [],
                        "variables": dimension_record["hole_callout_variables"],
                        "box": dimension_record["box"],
                    })
            for note in _as_sequence(_safe_member(view, "GetNotes", default=[])):
                note_evidence = _note_evidence(note)
                note_text = str(note_evidence.get("text") or "").strip()
                owner_view_type = view_record["type"]
                notes.append({
                    "sheet": str(sheet_name),
                    "owner_view": view_record["name"],
                    "owner_view_type": owner_view_type,
                    "note_kind": "view_label" if owner_view_type in {2, 3} and not note_text else "note",
                    **note_evidence,
                })
            for table in _as_sequence(_safe_member(view, "GetTableAnnotations", default=[])):
                tables.append(_table_evidence(table, sheet_name))
    current_sheet = _safe_member(drawing_model, "GetCurrentSheet")
    template = _safe_member(current_sheet, "GetTemplateName", default="")
    paper_size = str(paper_size_hint or _paper_size_from_template(template) or "").upper() or None
    spec = PAPER_SIZES.get(paper_size)
    inferred_title_box = title_block_box
    if inferred_title_box is None and spec is not None:
        inferred_title_box = {
            "left": spec["width_m"] - 0.012 - 0.180,
            "bottom": 0.012,
            "right": spec["width_m"] - 0.012,
            "top": 0.067,
        }
    compact_template_name = re.sub(r"[^a-z0-9çğıöşü\u4e00-\u9fff]", "", Path(str(template or "")).stem.casefold())
    template_name = Path(str(template or "")).stem.casefold()
    gbt_candidate = (
        "gbt" in compact_template_name
        or "\u56fd\u6807" in compact_template_name
        or bool(re.search(r"(?:^|[^a-z0-9])gb(?:t)?(?:[^a-z0-9]|$)", template_name, re.IGNORECASE))
    )
    outline_count = sum(item.get("box") is not None for item in views)
    dimension_box_count = sum(item.get("box") is not None for item in dimensions)
    native_dimension_box_count = sum(item.get("box_source") == "native" for item in dimensions)
    estimated_dimension_box_count = sum(item.get("box_source") == "estimated" and item.get("box") is not None for item in dimensions)
    low_confidence_dimension_box_count = sum(item.get("box_confidence") in {"low", "unavailable"} for item in dimensions)
    result = {
        "status": "pass" if views else "blocked",
        "stage": "review",
        "sheets": [str(item) for item in sheets],
        "views": views,
        "dimensions": dimensions,
        "notes": notes,
        "tables": tables,
        "professional_annotations": professional_annotations,
        "template_path": str(template or ""),
        "paper_size": paper_size,
        "sheet_size": {"width_m": spec["width_m"], "height_m": spec["height_m"]} if spec else None,
        "title_block": {
            "candidate": bool(template),
            "gbt_candidate": gbt_candidate,
            "content_verified": any(item.get("kind") == "title_block" and item.get("row_count", 0) > 0 for item in tables),
            "fields": {},
            "box": _normalise_box(title_block_box) if title_block_box is not None else inferred_title_box,
        },
        "view_count": len(views),
        "dimension_count": len(dimensions),
        "table_count": len(tables),
        "view_outline_count": outline_count,
        "dimension_box_count": dimension_box_count,
        "native_dimension_box_count": native_dimension_box_count,
        "estimated_dimension_box_count": estimated_dimension_box_count,
        "low_confidence_dimension_box_count": low_confidence_dimension_box_count,
        "manual_review_required": True,
        "retryable": not bool(views),
        "error_code": None if views else "DRAWING_VIEWS_MISSING",
        "checks": [
            {"id": "drawing-views", "status": "pass" if views else "fail", "message": "Çizimde görünüşler mevcut" if views else "Çizim görünüşleri okunamadı"},
            {"id": "drawing-template", "status": "pass" if template else "warning", "message": "Çizim çerçevesi şablonu okundu" if template else "Çizim çerçevesi şablonu insan tarafından doğrulanmalıdır"},
            {"id": "drawing-a3-sheet", "status": "pass" if paper_size == "A3" else "warning", "message": "Mevcut pafta boyutu A3 olarak tanındı" if paper_size == "A3" else "Mevcut pafta boyutu A3 değil veya tanınamadı"},
            {"id": "drawing-gbt-template", "status": "pass" if gbt_candidate else "warning", "message": "Şablon adı GB/T adayı; içerik yine de görsel olarak incelenmelidir" if gbt_candidate else "GB/T çizim çerçevesi adayı bulunamadı"},
            {"id": "drawing-dimensions", "status": "pass" if dimensions else "warning", "message": "Gerçek ölçü nesneleri okundu" if dimensions else "Ölçü nesneleri okunamadı"},
            {"id": "drawing-view-outlines", "status": "pass" if views and outline_count == len(views) else "warning", "message": "Tüm görünüş sınırları okundu" if views and outline_count == len(views) else "Bazı görünüş sınırları eksik; çakışmalar tam olarak kontrol edilemiyor"},
            {
                "id": "drawing-dimension-boxes",
                "status": "pass" if dimensions and native_dimension_box_count == len(dimensions) else "warning",
                "message": (
                    "Tüm ölçü metinlerinin özgün sınırları okundu"
                    if dimensions and native_dimension_box_count == len(dimensions)
                    else f"Özgün sınırlar: {native_dimension_box_count}/{len(dimensions)}; korumacı tahmin: {estimated_dimension_box_count}/{len(dimensions)}; tahmin özgün kanıt değildir"
                ),
            },
        ],
    }
    return result


def auto_insert_center_marks(drawing_model, requirements) -> dict:
    """Automatically insert center marks by view and verify success through read-back entity counts."""
    requested = list(requirements or [])
    if not requested:
        return {
            "status": "not_requested",
            "requested": False,
            "requirements": [],
            "manual_review_required": False,
            "error_code": None,
        }

    sheet = _safe_member(drawing_model, "GetCurrentSheet")
    sheet_views = _as_sequence(_safe_member(sheet, "GetViews", default=[]))
    mapped_views, diagnostics, mapping_method = _map_standard_views_from_sheet_views(sheet_views)
    drawing_path = str(_safe_member(drawing_model, "GetPathName", default="") or "")
    results = []
    for requirement in requested:
        requirement_id = str(requirement.get("id") or "")
        orientation = _normalise_orientation(requirement.get("view"))
        expected_count = int(requirement.get("count") or 0)
        targets = list(requirement.get("targets") or [])
        insert_type = 0
        for target in targets:
            insert_type |= AUTO_CENTER_MARK_TARGETS.get(str(target), 0)
        view = mapped_views.get(orientation)
        if view is None or not orientation or insert_type == 0 or expected_count <= 0:
            results.append({
                "id": requirement_id,
                "status": "failed",
                "view": orientation or str(requirement.get("view") or ""),
                "targets": targets,
                "expected_count": expected_count,
                "before_count": 0,
                "after_count": 0,
                "created_count": 0,
                "api_returned": None,
                "error_code": "DRAWING_CENTER_MARK_REQUIREMENT_UNRESOLVED",
            })
            continue

        before_count = len(_view_center_marks(view))
        api_returned = None
        error = None
        if before_count < expected_count:
            view_name = str(_safe_member(view, "Name", default="") or "")
            if view_name:
                _safe_member(drawing_model, "ActivateView", view_name)
            try:
                api_returned = bool(get_com_member(
                    view,
                    "AutoInsertCenterMarks2",
                    insert_type,
                    0,      # swCenterMarkConnectionLine_None
                    True,   # Use the slot center for linear slots.
                    True,   # Use the slot center for arc slots.
                    True,   # Use document defaults for size and gap.
                    0.0,
                    0.0,
                    False,
                    True,
                    0.0,
                ))
            except Exception as exc:
                error = str(exc)
            _safe_member(drawing_model, "ForceRebuild3", False)
            _safe_member(drawing_model, "GraphicsRedraw2")
        after_count = len(_view_center_marks(view))
        passed = after_count >= expected_count
        failure_code = None
        if not passed:
            failure_code = (
                "DRAWING_CENTER_MARK_DRAWING_SAVE_REQUIRED"
                if api_returned is True and not drawing_path
                else "DRAWING_CENTER_MARK_INSERT_OR_READBACK_FAILED"
            )
        results.append({
            "id": requirement_id,
            "status": "pass" if passed else "failed",
            "view": orientation,
            "actual_view": str(_safe_member(view, "Name", default="") or ""),
            "targets": targets,
            "insert_type": insert_type,
            "expected_count": expected_count,
            "before_count": before_count,
            "after_count": after_count,
            "created_count": max(0, after_count - before_count),
            "api_returned": api_returned,
            "error": error,
            "error_code": failure_code,
        })

    failed = [item for item in results if item["status"] != "pass"]
    aggregate_error = None
    if failed:
        aggregate_error = (
            "DRAWING_CENTER_MARK_DRAWING_SAVE_REQUIRED"
            if all(item.get("error_code") == "DRAWING_CENTER_MARK_DRAWING_SAVE_REQUIRED" for item in failed)
            else "DRAWING_CENTER_MARK_INSERT_OR_READBACK_FAILED"
        )
    return {
        "status": "failed" if failed else "pass",
        "requested": True,
        "requirements": results,
        "mapping_method": mapping_method,
        "mapping_diagnostics": diagnostics,
        "drawing_path": drawing_path,
        "manual_review_required": True,
        "retryable": aggregate_error == "DRAWING_CENTER_MARK_DRAWING_SAVE_REQUIRED",
        "error_code": aggregate_error,
    }


def export_sheet_to_pdf(model, output_path, sheet_names=None, sw_app=None):
    """Export a drawing to PDF. model is an IModelDoc2 drawing; output_path is the PDF destination; sheet_names is a list or None for all sheets. Optional sw_app is SldWorks.Application; supplying it avoids SW2024 dynamic IModelDoc2 proxies that do not expose GetSldWorksObject."""
    sw = sw_app
    if sw is None:
        for prog_id in ("SldWorks.Application.32", "SldWorks.Application"):
            try:
                sw = _win32com.GetActiveObject(prog_id)
                break
            except Exception:
                continue
    if sw is None:
        return False
    try:
        pdf_data = get_com_member(sw, "GetExportFileData", 1)  # 1 = swExportPDFData
    except Exception:
        return False

    if sheet_names is None:
        drawing = model
        sheet_names = get_com_member(drawing, "GetSheetNames")

    try:
        pdf_data.SetSheets(0, sheet_names)  # 0 = swExportData_ExportSpecifiedSheets
    except Exception:
        return False

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    success = model.Extension.SaveAs(output_path, 0, 1, pdf_data, errors, warnings)

    if success:
        print(f"PDF dışa aktarıldı: {output_path}")
    else:
        print(f"PDF dışa aktarılamadı; hata kodu: {errors.value}")
    return success


def setup_current_sheet(drawing_model, template_candidates, *, paper_size="A3", projection="first_angle", require_gbt=True) -> dict:
    """Configure the current sheet from DrawingSpec and read back basic configuration evidence."""
    paper_size = str(paper_size).upper()
    projection = str(projection).lower()
    if paper_size not in PAPER_SIZES:
        raise ValueError(f"Desteklenmeyen pafta boyutu: {paper_size}")
    if projection not in {"first_angle", "third_angle"}:
        raise ValueError("projection \u5fc5\u987b\u662f first_angle \u6216 third_angle")
    selection = select_drawing_template(template_candidates, paper_size=paper_size, require_gbt=require_gbt)
    if not selection["selected"]:
        return {**selection, "status": "blocked", "stage": "preflight", "configured": False, "retryable": True}
    sheet = _safe_member(drawing_model, "GetCurrentSheet")
    sheet_name = str(_safe_member(sheet, "GetName", default="") or "")
    if not sheet_name:
        return {**selection, "status": "blocked", "stage": "preflight", "configured": False, "error_code": "DRAWING_CURRENT_SHEET_MISSING"}
    try:
        configured = bool(get_com_member(
            drawing_model,
            "SetupSheet6",
            sheet_name,
            PAPER_SIZES[paper_size]["code"],
            12,
            1.0,
            1.0,
            projection == "first_angle",
            selection["selected"],
            0.0,
            0.0,
            "",
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            0,
        ))
    except Exception as exc:
        return {**selection, "status": "failed", "stage": "create", "configured": False, "projection": projection, "error_code": "DRAWING_SHEET_SETUP_FAILED", "error": str(exc)}
    return {
        **selection,
        "status": "pass" if configured else "failed",
        "stage": "create",
        "configured": configured,
        "paper_size": paper_size,
        "projection": projection,
        "sheet_name": sheet_name,
        "error_code": None if configured else "DRAWING_SHEET_SETUP_FAILED",
        "manual_review_required": True,
    }


def validate_generic_drawing_generation(spec) -> dict:
    """Declare DrawingSpec fields the generic generator cannot reliably execute before modifying the document."""
    issues = []
    views = dict(spec.get("views") or {})
    standard_views = {name for name in ("front", "top", "right") if name in views}
    if standard_views != {"front", "top", "right"}:
        issues.append({
            "code": "DRAWING_STANDARD_VIEW_SET_UNSUPPORTED",
            "path": "views",
            "message": "Genel üretici şu anda yalnızca front/top/right üç görünüşünü birlikte oluşturabilir.",
        })
    unsupported_views = [name for name in ("bottom", "left", "isometric") if name in views]
    unsupported_views.extend(name for name in ("sections", "details") if views.get(name))
    if unsupported_views:
        issues.append({
            "code": "DRAWING_REQUESTED_VIEWS_UNSUPPORTED",
            "path": "views",
            "views": unsupported_views,
            "message": "Genel üretici istenen yardımcı, izometrik, kesit veya detay görünüşlerini henüz oluşturamaz.",
        })
    configured_views = [name for name in ("front", "top", "right") if views.get(name)]
    if configured_views:
        issues.append({
            "code": "DRAWING_VIEW_OPTIONS_UNSUPPORTED",
            "path": "views",
            "views": configured_views,
            "message": "Genel üretici standart görünüş nesnelerindeki ad, yön veya konum seçeneklerini henüz uygulayamaz.",
        })
    if spec.get("requiredDimensions"):
        issues.append({
            "code": "DRAWING_REQUIRED_DIMENSIONS_UNSUPPORTED",
            "path": "requiredDimensions",
            "message": "Genel üretici yalnızca model ölçülerini içe aktarabilir; belirli ID, görünüş ve anlam ile ölçü oluşturup bağlayamaz.",
        })
    if spec.get("holeRequirements"):
        issues.append({
            "code": "DRAWING_HOLE_REQUIREMENTS_UNSUPPORTED",
            "path": "holeRequirements",
            "message": "Genel üretici delik açıklamaları veya delik tablolarını henüz oluşturamaz; özel betikler kullanıp kanıtları geri okuyun.",
        })
    professional_annotations = dict(spec.get("professionalAnnotations") or {})
    unsupported_professional_fields = sorted(
        name for name, values in professional_annotations.items()
        if name != "centerMarks" and values
    )
    if unsupported_professional_fields:
        issues.append({
            "code": "DRAWING_PROFESSIONAL_ANNOTATIONS_UNSUPPORTED",
            "path": "professionalAnnotations",
            "fields": unsupported_professional_fields,
            "message": "Genel üretici yalnızca geri okunarak doğrulanmış otomatik merkez işaretlerini destekler; diğer profesyonel açıklamalar için özel betikler gerekir.",
        })
    title_fields = sorted(set((spec.get("titleBlock") or {})) - {"required", "format"})
    if title_fields:
        issues.append({
            "code": "DRAWING_TITLE_BLOCK_FIELDS_UNSUPPORTED",
            "path": "titleBlock",
            "fields": title_fields,
            "message": "Genel üretici antetin iş alanlarını henüz bağlayamaz.",
        })
    if spec.get("sheetMetal"):
        issues.append({
            "code": "DRAWING_SHEET_METAL_OPTIONS_UNSUPPORTED",
            "path": "sheetMetal",
            "message": "Genel üretici açınım, büküm tablosu veya saca özgü seçenekleri henüz uygulayamaz.",
        })
    return {
        "status": "blocked" if issues else "pass",
        "stage": "capability_preflight",
        "issues": issues,
        "error_code": "DRAWING_SPEC_CAPABILITY_UNSUPPORTED" if issues else None,
        "manual_review_required": bool(issues),
    }


def generate_drawing_from_spec(drawing_model, spec, source_model_path, template_candidates=None) -> dict:
    """Create the standard drawing structure and manufacturing-annotation entrypoint from a validated DrawingSpec."""
    capability = validate_generic_drawing_generation(spec)
    if capability["status"] != "pass":
        return capability
    paper_size = str(spec.get("paperSize", "A3")).upper()
    projection = str(spec.get("projection", "first_angle")).lower()
    model_size_mm = spec.get("modelSizeMm")
    if not isinstance(model_size_mm, (list, tuple)) or len(model_size_mm) != 3:
        return {
            "status": "blocked",
            "stage": "planning",
            "error_code": "DRAWING_MODEL_SIZE_MISSING",
            "message": "DrawingSpec, modelSizeMm sağlamalıdır; çizim ölçeği ve görünüş yerleşimi tahmin edilmemelidir.",
            "manual_review_required": True,
        }
    candidates = list(template_candidates or spec.get("templateCandidates") or [])
    sheet_setup = setup_current_sheet(
        drawing_model,
        candidates,
        paper_size=paper_size,
        projection=projection,
        require_gbt=spec.get("standard") == "GB_T",
    )
    if sheet_setup.get("status") != "pass":
        return {"status": sheet_setup.get("status", "blocked"), "stage": "sheet", "sheetSetup": sheet_setup, "error_code": sheet_setup.get("error_code"), "manual_review_required": True}
    model_size_m = tuple(float(value) / 1000.0 for value in model_size_mm)
    layout = plan_standard_view_layout(
        model_size_m,
        paper_size=paper_size,
        projection=projection,
        requested_scale=spec.get("scale"),
    )
    if layout.get("status") != "pass":
        return {"status": "blocked", "stage": "layout", "sheetSetup": sheet_setup, "layout": layout, "error_code": layout.get("error_code"), "manual_review_required": True}
    views = create_adaptive_standard_views(drawing_model, str(source_model_path), layout)
    if views.get("status") != "pass":
        return {"status": "failed", "stage": "views", "sheetSetup": sheet_setup, "layout": layout, "views": views, "error_code": views.get("error_code"), "manual_review_required": True}
    professional_annotations = dict(spec.get("professionalAnnotations") or {})
    center_marks = auto_insert_center_marks(drawing_model, professional_annotations.get("centerMarks"))
    if center_marks.get("status") == "failed":
        save_required = center_marks.get("error_code") == "DRAWING_CENTER_MARK_DRAWING_SAVE_REQUIRED"
        return {
            "status": "blocked" if save_required else "failed",
            "stage": "professional_annotations",
            "professionalAnnotations": {"centerMarks": center_marks},
            "sheetSetup": sheet_setup,
            "layout": layout,
            "views": views,
            "error_code": center_marks.get("error_code"),
            "retryable": bool(center_marks.get("retryable")),
            "manual_review_required": True,
        }
    dimension_result = insert_dimensions(drawing_model) if spec.get("requiredDimensions") or spec.get("insertModelDimensions", True) else False
    arrangement = auto_arrange_drawing_dimensions(drawing_model) if dimension_result else {"status": "review_required", "error_code": "DRAWING_DIMENSIONS_NOT_REQUESTED"}
    bom_spec = spec.get("bom") or {}
    bom_requested = bool(bom_spec.get("required")) or spec.get("documentType") == "assembly"
    bom_result = {"requested": bom_requested, "created": False, "status": "not_requested"}
    if bom_requested:
        template_path = str(bom_spec.get("templatePath") or "")
        if not template_path or not Path(template_path).expanduser().is_file():
            return {"status": "blocked", "stage": "bom", "error_code": "DRAWING_BOM_TEMPLATE_MISSING", "message": "BOM istendi ancak şablon yok; teslim için sahte tablo oluşturulamaz.", "sheetSetup": sheet_setup, "layout": layout, "views": views, "manual_review_required": True}
        position = bom_spec.get("positionMm") or [250.0, 45.0]
        bom_table = insert_bom_table(drawing_model, template_path, float(position[0]) / 1000.0, float(position[1]) / 1000.0, int(bom_spec.get("bomType", 1)), str(bom_spec.get("configuration", "")))
        bom_result = {"requested": True, "created": bom_table is not None, "status": "pass" if bom_table is not None else "failed", "template_path": template_path, "position_mm": position, "error_code": None if bom_table is not None else "DRAWING_BOM_INSERT_FAILED"}
        if bom_table is None:
            return {"status": "failed", "stage": "bom", "bom": bom_result, "sheetSetup": sheet_setup, "layout": layout, "views": views, "manual_review_required": True}
    notes = []
    for index, note_text in enumerate(spec.get("notes") or []):
        note_result = add_note(drawing_model, 0.02, 0.02 + index * 0.006, str(note_text))
        notes.append(note_result)
        if note_result.get("status") != "pass":
            return {
                "status": "failed",
                "stage": "notes",
                "error_code": note_result.get("error_code") or "DRAWING_NOTE_COM_EVIDENCE_MISSING",
                "notes": notes,
                "sheetSetup": sheet_setup,
                "layout": layout,
                "views": views,
                "manual_review_required": True,
            }
    structure = inspect_drawing_structure(
        drawing_model,
        paper_size_hint=paper_size,
        title_block_box=layout.get("title_block_box"),
    )
    status = "pass" if structure.get("status") == "pass" and dimension_result else "review_required"
    return {
        "status": status,
        "stage": "review",
        "source_model": str(source_model_path),
        "standard": spec.get("standard"),
        "projection": projection,
        "sheetSetup": sheet_setup,
        "layout": layout,
        "views": views,
        "professionalAnnotations": {"centerMarks": center_marks},
        "dimensions": {"inserted": bool(dimension_result), "arrangement": arrangement},
        "bom": bom_result,
        "notes": notes,
        "structure": structure,
        "manual_review_required": True,
        "error_code": None if status == "pass" else "DRAWING_GENERATION_REVIEW_REQUIRED",
    }
