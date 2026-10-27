"""
Design-spec executor: idempotently build validated design specifications as SolidWorks parts.

The executor provides:
- Idempotency: identical specifications produce comparable, repeatable feature-tree structures.
- Traceability: record actual feature names and read-back dimensions for every step.
- Built-in validation: read back bounding box, hole count and mass and compare with verify.

Specifications use millimeters; convert to meters before calling the SolidWorks API.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

try:
    from .sw_connect import get_com_member, mm
    from .sw_part import (
        SketchSelectionRef,
        extrude_boss,
        fillet,
        sketch_circle,
        sketch_corner_rectangle,
        sketch,
    )
    from .sw_hole_features import (
        create_blind_hole,
        create_counterbore_hole,
        create_countersink_hole,
        create_through_hole,
    )
    from .sw_edge_select import select_edges
    from . import sw_measure
    from .design_spec import compare_verification
except ImportError:  # When scripts/ is directly on sys.path
    from sw_connect import get_com_member, mm
    from sw_part import (
        SketchSelectionRef,
        extrude_boss,
        fillet,
        sketch_circle,
        sketch_corner_rectangle,
        sketch,
    )
    from sw_hole_features import (
        create_blind_hole,
        create_counterbore_hole,
        create_countersink_hole,
        create_through_hole,
    )
    from sw_edge_select import select_edges
    import sw_measure
    from design_spec import compare_verification


def _safe(obj, name, *args, default=None):
    """@brief Safely read a COM member."""
    try:
        member = getattr(obj, name)
        value = member(*args) if args or callable(member) else member
    except Exception:
        return default
    return default if value is None else value


def _feature_name(feature, fallback):
    """@brief Read a feature name with a fallback on failure."""
    name = _safe(feature, "Name")
    return str(name) if name else fallback


def _rotate_point(x_mm, y_mm, angle_deg):
    """@brief Rotate a 2D point around the origin for circular hole-pattern coordinates."""
    radians = math.radians(angle_deg)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return (x_mm * cos_a - y_mm * sin_a, x_mm * sin_a + y_mm * cos_a)


def expand_hole_patterns(holes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Expand hole pattern definitions.

    A hole may contain a circular pattern with type=circular, count=6, radius=30,
    start_angle=0, or a linear pattern with type=linear, count=4, dx=20, dy=0.
    Expand these into individual definitions, each with a traceable id.

    Args:
        holes: Normalized hole list.

    Returns:
        Expanded holes; replace each patterned seed with count holes.
    """
    expanded: List[Dict[str, Any]] = []
    for hole in holes:
        pattern = hole.get("pattern")
        if not pattern:
            expanded.append(dict(hole))
            continue

        kind = str(pattern.get("type", "")).strip().lower()
        try:
            count = int(pattern.get("count", 1))
        except (TypeError, ValueError):
            count = 1
        if count < 1 or count > 200:
            count = max(1, min(count, 200))

        base_position = list(hole.get("position_mm") or [0.0, 0.0, 0.0])
        for index in range(count):
            variant = dict(hole)
            variant.pop("pattern", None)
            if kind == "circular":
                radius = float(pattern.get("radius", 0.0) or 0.0)
                start = float(pattern.get("start_angle", 0.0) or 0.0)
                step = 360.0 / count
                x_mm, y_mm = _rotate_point(radius, 0.0, start + step * index)
                variant["position_mm"] = [
                    round(base_position[0] + x_mm, 6),
                    round(base_position[1] + y_mm, 6),
                    base_position[2],
                ]
            elif kind == "linear":
                dx = float(pattern.get("dx", 0.0) or 0.0)
                dy = float(pattern.get("dy", 0.0) or 0.0)
                dz = float(pattern.get("dz", 0.0) or 0.0)
                variant["position_mm"] = [
                    round(base_position[0] + dx * index, 6),
                    round(base_position[1] + dy * index, 6),
                    round(base_position[2] + dz * index, 6),
                ]
            else:
                # Unknown pattern: preserve the seed and let the caller explain it in warnings.
                expanded.append(dict(hole))
                break
            variant["id"] = f"{hole.get('id', 'H')}_{index + 1}"
            expanded.append(variant)

    return expanded


def _create_base(model, base):
    """
    Create the base solid and return (feature, plane_name, errors).

    Coordinate convention: the plate lower-left corner is at the origin, its face
    lies in the first XY quadrant, and extrusion follows +Z. Hole coordinates can
    therefore use drawing offsets from the left and bottom edges directly without
    a centered-coordinate conversion.
    """
    base_type = base.get("type")
    if base_type == "rect_plate":
        width_mm = base["width_mm"]
        height_mm = base["height_mm"]
        thickness_mm = base["thickness_mm"]
        with sketch(model, "Front Plane") as sketch_ref:
            sketch_corner_rectangle(model, 0.0, 0.0, mm(width_mm), mm(height_mm))
        feature = extrude_boss(model, sketch_ref, mm(thickness_mm))
        return feature, "Front Plane", []

    if base_type == "cylinder":
        diameter_mm = base["diameter_mm"]
        height_mm = base["height_mm"]
        with sketch(model, "Front Plane") as sketch_ref:
            sketch_circle(model, 0.0, 0.0, mm(diameter_mm / 2.0))
        feature = extrude_boss(model, sketch_ref, mm(height_mm))
        return feature, "Front Plane", []

    if base_type == "none":
        return None, "Front Plane", []

    return None, "Front Plane", [f"Desteklenmeyen base.type={base_type!r}"]


def validate_holes_inside_base(holes, base):
    """
    Check that hole centers lie within the base solid.

    SolidWorks can silently reject cuts whose sketch is entirely outside the body,
    appearing successful without a feature. Report coordinate errors explicitly
    before modeling so users can distinguish them from API failures.
    """
    problems = []
    base = base or {}
    if base.get("type") == "rect_plate":
        width = base["width_mm"]
        height = base["height_mm"]
        for hole in holes:
            x_mm, y_mm = hole["position_mm"][0], hole["position_mm"][1]
            radius = hole["diameter_mm"] / 2.0
            if x_mm - radius < -1e-6 or y_mm - radius < -1e-6 or x_mm + radius > width + 1e-6 or y_mm + radius > height + 1e-6:
                problems.append(
                    f"Delik {hole.get('id')} konumu ({x_mm}, {y_mm}), çapı {hole['diameter_mm']}mm, "
                    f" levha sınırlarını aşıyor: {width}x{height} mm (origin sol alt köşede)."
                )
    elif base.get("type") == "cylinder":
        diameter = base["diameter_mm"]
        radius_base = diameter / 2.0
        for hole in holes:
            x_mm, y_mm = hole["position_mm"][0], hole["position_mm"][1]
            distance = math.hypot(x_mm, y_mm)
            if distance + hole["diameter_mm"] / 2.0 > radius_base + 1e-6:
                problems.append(
                    f"Delik {hole.get('id')} merkezinin eksene uzaklığı {distance:.3f} mm; silindir yarıçapını aşıyor: {radius_base}mm."
                )
    return problems


def _hole_center_m(hole):
    """Convert hole-center millimeters from the specification to SolidWorks API meters."""
    return (mm(hole["position_mm"][0]), mm(hole["position_mm"][1]))


_SUPPORTED_HOLE_TYPES = frozenset({"through", "blind", "counterbore", "countersink"})


def _create_hole(model, hole):
    """
    Dispatch hole types to sw_hole_features creation functions.

    These functions expect lengths in meters while specifications use millimeters.
    Convert explicitly: raw millimeters create a sketch 1000 times too large and
    can make SolidWorks silently reject the cut. One observed 100 mm plate expanded
    to 13300 mm.

    Resolve functions through this module at call time rather than binding them
    during import, enabling isolated tests and avoiding import-order dependencies.
    """
    hole_type = hole.get("type")
    hole_name = hole.get("id", "Delik")

    if hole_type == "through":
        return create_through_hole(
            model,
            center=_hole_center_m(hole),
            diameter=mm(hole["diameter_mm"]),
            name=hole.get("id", "Through hole"),
        )
    if hole_type == "blind":
        return create_blind_hole(
            model,
            center=_hole_center_m(hole),
            diameter=mm(hole["diameter_mm"]),
            depth=mm(hole["depth_mm"]),
            name=hole_name,
        )
    if hole_type == "counterbore":
        return create_counterbore_hole(
            model,
            center=_hole_center_m(hole),
            hole_diameter=mm(hole["diameter_mm"]),
            counterbore_diameter=mm(hole["counterbore_diameter_mm"]),
            counterbore_depth=mm(hole["counterbore_depth_mm"]),
            name=hole_name,
        )
    if hole_type == "countersink":
        return create_countersink_hole(
            model,
            center=_hole_center_m(hole),
            hole_diameter=mm(hole["diameter_mm"]),
            countersink_diameter=mm(hole["countersink_diameter_mm"]),
            included_angle_deg=hole.get("angle_deg", 90.0),
            name=hole_name,
        )
    raise ValueError(f"Desteklenmeyen delik türü: {hole_type!r}")


def build_from_spec(model, spec: Dict[str, Any], apply_fillets=True, verify_geometry=True):
    """
    Build a part from a design specification.

    Args:
        model: Newly created empty IModelDoc2 part document.
        spec: Normalized specification already accepted by validate_design_spec
            (the validation result's normalized field).
        apply_fillets: Execute the fillets section. Fillet/chamfer failures add
            warnings without rolling back the body; existing geometry helps users
            diagnose parameter-related failures.
        verify_geometry: Read geometry back and compare with the verify section.

    Returns:
        Dictionary: status / steps / warnings / errors / verification / measurements.
    """
    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    errors: List[str] = []

    # ---- Base solid ----
    feature, plane_name, base_errors = _create_base(model, spec.get("base") or {})
    errors.extend(base_errors)
    if feature is None and not base_errors and (spec.get("base") or {}).get("type") != "none":
        errors.append("Temel katı oluşturulamadı: feature oluşmadı. Template kullanılabilirliğini denetleyin.")
    steps.append({
        "step": "base",
        "type": (spec.get("base") or {}).get("type"),
        "feature": _feature_name(feature, "Base") if feature else None,
        "ok": feature is not None or (spec.get("base") or {}).get("type") == "none",
    })

    if errors:
        return {
            "status": "error",
            "steps": steps,
            "warnings": warnings,
            "errors": errors,
            "verification": {"status": "skipped", "checks": []},
        }

    if feature is not None:
        try:
            model.ForceRebuild3(False)
        except Exception:
            pass

    # ---- Holes ----
    holes = expand_hole_patterns(spec.get("holes") or [])
    created_holes: List[Dict[str, Any]] = []

    for problem in validate_holes_inside_base(holes, spec.get("base") or {}):
        errors.append(problem)

    if errors:
        # Out-of-bounds holes are specification errors; continuing would produce misleading feature-not-created messages.
        steps.append({"step": "holes", "ok": False, "reason": "Delik konumu sınır dışında; delik oluşturma atlandı"})
        return {
            "status": "error",
            "steps": steps,
            "warnings": warnings,
            "errors": errors,
            "verification": {"status": "skipped", "checks": []},
        }

    for hole in holes:
        hole_type = hole.get("type")
        if hole_type not in _SUPPORTED_HOLE_TYPES:
            errors.append(f"Delik {hole.get('id')}: desteklenmeyen delik türü {hole_type!r}")
            continue
        try:
            result = _create_hole(model, hole)
        except Exception as exc:
            errors.append(f"Delik {hole.get('id')} oluşturulamadı: {exc}")
            steps.append({"step": "hole", "id": hole.get("id"), "type": hole_type, "ok": False})
            continue

        # HoleFeatureEvidence.to_dict() exposes feature_names as a tuple,
        # not status; successful feature creation produces a nonempty tuple.
        feature_names = (result or {}).get("feature_names") or ()
        ok = bool(feature_names) and not any(name is None for name in feature_names)
        created_holes.append({"id": hole.get("id"), "type": hole_type, "result": result, "ok": ok})
        steps.append({
            "step": "hole",
            "id": hole.get("id"),
            "type": hole_type,
            "position_mm": hole.get("position_mm"),
            "diameter_mm": hole.get("diameter_mm"),
            "ok": ok,
            "feature": feature_names[0] if feature_names else None,
        })
        if not ok:
            errors.append(
                f"Delik {hole.get('id')} oluşturulamadı (SOLIDWORKS özellik adı döndürmedi)."
                "Yaygın nedenler: delik konumu katı dışında veya önceki delikle çakışıyor."
            )

    # ---- Fillets ----
    # Name the loop variable fillet_spec: fillet would shadow the imported function,
    # causing fillet(model, radius) to call a dictionary, which is not callable.
    fillet_results = []
    if apply_fillets and spec.get("fillets"):
        for index, fillet_spec in enumerate(spec["fillets"]):
            radius_mm = fillet_spec.get("radius_mm")
            if radius_mm is None:
                continue
            edge_spec = {
                "axis": fillet_spec.get("axis", "z"),
                "convex_only": bool(fillet_spec.get("convex_only")),
                "concave_only": bool(fillet_spec.get("concave_only")),
            }
            selection = select_edges(model, edge_spec)
            entry = {
                "step": "fillet",
                "index": index,
                "radius_mm": radius_mm,
                "selected_count": selection.get("selected_count", 0),
                "ok": False,
            }
            if selection.get("status") != "ok":
                warnings.append(
                    f"Fillet {index}: kenar seçilmedi (koşul {edge_spec}); bu Fillet atlandı."
                    f"Model kenarlarını solidworks_list_edges ile görüntüleyebilirsiniz."
                )
                fillet_results.append(entry)
                steps.append(entry)
                try:
                    model.ClearSelection2(True)
                except Exception:
                    pass
                continue
            try:
                created = fillet(model, mm(radius_mm))
                entry["ok"] = created is not None
                entry["feature"] = _feature_name(created, f"Fillet{index + 1}")
                if created is None:
                    warnings.append(f"Fillet {index}: seçilen kenar sayısı {entry['selected_count']}; ancak özellik oluşturulmadı, "
                                    "Genellikle aşırı yarıçap nedeniyle kendiyle kesişme oluşur.")
            except Exception as exc:
                entry["error"] = str(exc)
                warnings.append(f"Fillet {index} başarısız: {exc}")
            finally:
                try:
                    model.ClearSelection2(True)
                except Exception:
                    pass
            fillet_results.append(entry)
            steps.append(entry)

    # ---- Read-back and verification ----
    measurements: Dict[str, Any] = {}
    verification: Dict[str, Any] = {"status": "skipped", "checks": []}
    if verify_geometry:
        try:
            model.ForceRebuild3(False)
        except Exception:
            pass
        try:
            bounding = sw_measure.collect_bounding_box(model)
        except Exception as exc:
            bounding = {"errors": [f"Bounding box readback başarısız: {exc}"]}
        try:
            mass = sw_measure.collect_mass_properties(model)
        except Exception as exc:
            mass = {"errors": [f"Kütle özellikleri readback başarısız: {exc}"]}

        measurements = {
            "bounding_box": {key: value for key, value in bounding.items() if key != "errors"},
            "mass_properties": {
                key: value for key, value in mass.items()
                if key in {"mass_g", "volume_mm3", "surface_area_mm2", "material", "material_assigned"}
            },
            "errors": list(bounding.get("errors") or []) + list(mass.get("errors") or []),
        }

        actual = {
            "envelope_mm": bounding.get("size_mm"),
            "hole_count": len([item for item in created_holes if item["ok"]]),
            "mass_g": mass.get("mass_g"),
        }
        verification = compare_verification(actual, spec.get("verify") or {})
        for error in measurements["errors"]:
            warnings.append(error)

    # Cross-check feature count and measured holes: a reported success without a feature is a silent failure,
    # detectable only by comparing read-back counts.
    actual_hole_count = len([item for item in created_holes if item["ok"]])
    if holes and actual_hole_count < len(holes):
        errors.append(
            f"Spesifikasyondaki delik sayısı {len(holes)}; başarıyla oluşturulan {actual_hole_count}; başarısız delik tanımlarını denetleyin."
        )

    status = "ok"
    if errors:
        status = "error"
    elif warnings:
        status = "warn"

    return {
        "status": status,
        "steps": steps,
        "hole_count_requested": len(holes),
        "hole_count_created": actual_hole_count,
        "fillet_results": fillet_results,
        "warnings": warnings,
        "errors": errors,
        "measurements": measurements,
        "verification": verification,
    }
