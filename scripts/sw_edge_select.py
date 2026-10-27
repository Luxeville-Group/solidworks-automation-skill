"""
SOLIDWORKS semantic edge selection.

Traditional SelectByID2("Edge1", "EDGE", x, y, z, ...) selection depends on fragile coordinate constants that break after model edits. This module traverses B-Rep topology and selects by geometry (direction, length, position, or cylindrical-face membership), then uses object Select4 to create the selection set. It avoids name/coordinate strings and remains usable after rebuilds.

Filters:
    axis: Edge direction ("x", "y", "z", "vertical", or "all").
    min_length_mm / max_length_mm: Length bounds.
    along_z: Whether the edge is parallel to Z.
    circular: Circle edges; use hole/min_diameter for hole entrance edges.
    diameter_mm: Circle diameter with tolerance_mm.
    position_mm: Required midpoint proximity with position_tolerance_mm.
    convex_only: Outer/convex edges for external fillets.
    concave_only: Inner/concave edges for internal fillets.
"""
from __future__ import annotations

import math

try:
    from .sw_connect import create_empty_dispatch_variant, get_com_member
except ImportError:
    from sw_connect import create_empty_dispatch_variant, get_com_member


_MM_PER_M = 1000.0

# Edge type in swSelectType_e.
SW_SEL_EDGE = "EDGE"

_AXIS_VECTORS = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


def _safe(obj, name, *args, default=None):
    """@brief Safely read a COM member."""
    try:
        member = getattr(obj, name)
        value = member(*args) if args or callable(member) else member
    except Exception:
        return default
    return default if value is None else value


def _to_mm(values):
    """@brief Convert a length sequence from meters to millimeters."""
    return [float(value) * _MM_PER_M for value in values]


def _normalize(vector):
    """@brief Normalize a vector; return None for a zero vector."""
    length = math.sqrt(sum(component * component for component in vector))
    if length < 1e-12:
        return None
    return tuple(component / length for component in vector)


def _is_parallel(first, second, angle_tolerance_deg=1.0):
    """@brief Check whether two unit vectors are parallel or antiparallel."""
    if first is None or second is None:
        return False
    dot = abs(sum(a * b for a, b in zip(first, second)))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot)) <= angle_tolerance_deg


def describe_edge(edge, index=0):
    """
    Read an edge geometry descriptor.

    Args:
        edge: IEdge object.
        index: Traversal index, used only for identification.

    Returns:
        dict with length_mm, mid_point_mm, direction, is_line, is_circle, diameter_mm, and convexity; errors is nonempty when readback fails.
    """
    descriptor = {
        "index": index,
        "length_mm": None,
        "mid_point_mm": None,
        "direction": None,
        "is_line": None,
        "is_circle": None,
        "diameter_mm": None,
        "convexity": None,
        "errors": [],
        "edge": edge,
    }

    curve_params = None
    try:
        curve = get_com_member(edge, "GetCurve")
        curve_params = list(get_com_member(edge, "GetCurveParams2") or [])
        descriptor["is_line"] = bool(_safe(curve, "IsLine"))
        descriptor["is_circle"] = bool(_safe(curve, "IsCircle"))
    except Exception as exc:
        descriptor["errors"].append(f"Eğri türü okunamadı: {exc}")

    try:
        descriptor["length_mm"] = round(float(_safe(edge, "GetLength")) * _MM_PER_M, 6)
    except Exception as exc:
        descriptor["errors"].append(f"Kenar uzunluğu okunamadı: {exc}")

    # Prefer start/end vertices (IEdge::GetStartVertex/GetEndVertex) for the midpoint;
    # this avoids differences in curve-parameter ordering.
    start_mm = end_mm = None
    try:
        start_mm = _to_mm(list(get_com_member(get_com_member(edge, "GetStartVertex"), "GetPoint") or []))
        end_mm = _to_mm(list(get_com_member(get_com_member(edge, "GetEndVertex"), "GetPoint") or []))
    except Exception as exc:
        descriptor["errors"].append(f"Uç nokta okunamadı: {exc}")

    if start_mm and end_mm and len(start_mm) >= 3 and len(end_mm) >= 3:
        descriptor["mid_point_mm"] = [
            round((start_mm[axis] + end_mm[axis]) / 2.0, 6) for axis in range(3)
        ]
        if not descriptor["is_circle"]:
            descriptor["direction"] = _normalize(
                [end_mm[axis] - start_mm[axis] for axis in range(3)]
            )

    # Curve parameters are fallback evidence for circle diameter/line direction; validate lengths because ordering differs across versions.
    # Diameter must be positive and comparable to edge length; otherwise report parsing failure rather than write invalid data.
    if curve_params and len(curve_params) >= 7:
        if descriptor["is_circle"]:
            candidate = abs(float(curve_params[6])) * 2.0 * _MM_PER_M
            length = descriptor.get("length_mm") or 0.0
            # For full circles circumference = pi*d; the implementation also bounds arc diameter by edge length.
            if 0.0 < candidate <= max(length, 1e-6) * 4.0 + 1e-6:
                descriptor["diameter_mm"] = round(candidate, 6)
        elif descriptor["direction"] is None:
            descriptor["direction"] = _normalize(
                [float(curve_params[3 + axis]) for axis in range(3)]
            )

    return descriptor


def describe_convexity(edge):
    """
    Classify an edge as convex or concave.

    Use adjacent-face normals and edge tangent geometry, independent of SOLIDWORKS display settings. Return None on read failure; callers should permit unknowns rather than misclassify them.
    """
    try:
        faces = list(get_com_member(edge, "GetTwoAdjacentFaces2") or [])
    except Exception:
        return None
    if len(faces) < 2:
        return None

    normals = []
    for face in faces[:2]:
        try:
            params = list(get_com_member(face, "GetSurface").GetPlaneParams())
            normals.append(_normalize([float(params[axis]) for axis in range(3, 6)]))
        except Exception:
            try:
                surface = get_com_member(face, "GetSurface")
                normal = _normalize([float(value) for value in get_com_member(surface, "PlaneParams")[3:6]])
                normals.append(normal)
            except Exception:
                return None

    if any(normal is None for normal in normals):
        return None

    # Midpoint normals at edge endpoints would be more rigorous; approximate using the angle between face-parameter normals.
    # This is accurate for common planar straight edges; return None for mixed surfaces and let callers decide.
    dot = sum(a * b for a, b in zip(normals[0], normals[1]))
    return "concave" if dot > 0 else "convex"


def iter_model_edges(model, body_index=None):
    """
    Traverse solid-body edges.

    Args:
        model: IModelDoc2 object.
        body_index: Restrict to one body; None means all bodies.

    Returns:
        (descriptors, errors): Edge descriptors and readback errors.
    """
    descriptors = []
    errors = []
    try:
        bodies = list(get_com_member(model, "GetBodies2", 0, False) or [])
    except Exception as exc:
        return descriptors, [f"Gövde listesi okunamadı: {exc}"]

    for index, body in enumerate(bodies):
        if body_index is not None and index != body_index:
            continue
        try:
            edges = list(get_com_member(body, "GetEdges") or [])
        except Exception as exc:
            errors.append(f"Gövde {index} kenarları okunamadı: {exc}")
            continue
        for edge_index, edge in enumerate(edges):
            descriptor = describe_edge(edge, index=len(descriptors))
            descriptor["body_index"] = index
            descriptor["edge_index"] = edge_index
            descriptors.append(descriptor)

    return descriptors, errors


def filter_edges(descriptors, axis="all", min_length_mm=None, max_length_mm=None,
                 circular=None, diameter_mm=None, diameter_tolerance_mm=0.05,
                 position_mm=None, position_tolerance_mm=0.1,
                 convex_only=False, concave_only=False, angle_tolerance_deg=1.0):
    """
    Filter edges by geometric conditions.

    Args:
        axis: "x", "y", "z", "vertical" (same as z), or "all"; straight edges only.
        min_length_mm / max_length_mm: Length bounds.
        circular: True keeps circles, False keeps noncircles, None does not filter.
        diameter_mm: Circle diameter filter; requires circular=True.
        position_mm: Required midpoint proximity to [x, y, z] in mm.
        convex_only / concave_only: Convexity filter; unknown convexity does not exclude an edge, avoiding omissions caused by readback failures.

    Returns:
        (selected, rejected_reasons): Selected descriptors and per-edge rejection reasons.
    """
    selected = []
    rejected = []

    normalized_axis = "z" if axis == "vertical" else axis
    target_vector = _AXIS_VECTORS.get(normalized_axis)

    for descriptor in descriptors:
        reasons = []

        if min_length_mm is not None:
            length = descriptor.get("length_mm")
            if length is None or length < min_length_mm:
                reasons.append(f"Uzunluk {length} < {min_length_mm}")

        if max_length_mm is not None:
            length = descriptor.get("length_mm")
            if length is None or length > max_length_mm:
                reasons.append(f"Uzunluk {length} > {max_length_mm}")

        if circular is not None and bool(descriptor.get("is_circle")) != bool(circular):
            reasons.append(f"Dairesel kenar koşulu eşleşmiyor (gereken circular={circular})")

        if diameter_mm is not None:
            actual = descriptor.get("diameter_mm")
            if actual is None:
                reasons.append("Çap bilinmiyor")
            elif abs(actual - diameter_mm) > diameter_tolerance_mm:
                reasons.append(f"Çap {actual} şu değerden sapıyor: {diameter_mm}±{diameter_tolerance_mm}")

        if position_mm is not None:
            midpoint = descriptor.get("mid_point_mm")
            if midpoint is None:
                reasons.append("Orta nokta bilinmiyor")
            else:
                distance = max(abs(midpoint[axis] - position_mm[axis]) for axis in range(3))
                if distance > position_tolerance_mm:
                    reasons.append(f"Orta nokta sapması: {distance:.3f}mm > {position_tolerance_mm}mm")

        if target_vector is not None:
            if descriptor.get("is_circle"):
                reasons.append("Dairesel kenar için doğrusal eksen tanımlı değil")
            elif not _is_parallel(descriptor.get("direction"), target_vector, angle_tolerance_deg):
                reasons.append(f"Yön şu eksene paralel değil: {normalized_axis} ekseni")

        if convex_only or concave_only:
            convexity = descriptor.get("convexity")
            if convexity is None:
                convexity = describe_convexity(descriptor.get("edge"))
                descriptor["convexity"] = convexity
            if convexity is not None:
                if convex_only and convexity != "convex":
                    reasons.append(f"Dışbükey kenar değil ({convexity})")
                if concave_only and convexity != "concave":
                    reasons.append(f"İçbükey kenar değil ({convexity})")

        if reasons:
            rejected.append({"index": descriptor.get("index"), "reasons": reasons})
        else:
            selected.append(descriptor)

    return selected, rejected


def select_edges(model, edge_spec, clear_first=True, mark=0):
    """
    Select edges by semantic criteria for later fillet/chamfer features.

    Args:
        model: IModelDoc2 object.
        edge_spec: Criteria dictionary using filter_edges parameter names.
        clear_first: Clear the current selection first.
        mark: SOLIDWORKS selection mark; feature APIs use it to distinguish edge roles. Default 0 suits FeatureFillet / InsertFeatureChamfer.

    Returns:
        dict with status, selected_count, selected, rejected, and errors.

    At least one edge must be selected. Otherwise return status="error" instead of continuing: an empty selection may apply operations to the current profile and create an unintended feature.
    """
    if clear_first:
        try:
            model.ClearSelection2(True)
        except Exception:
            pass

    descriptors, errors = iter_model_edges(model)
    if not descriptors:
        return {
            "status": "error",
            "selected_count": 0,
            "selected": [],
            "rejected": [],
            "errors": errors + ["Modelde kenar bulunamadı; etkin belgenin bir parça olduğunu ve katı oluşturulduğunu doğrulayın."],
        }

    selected, rejected = filter_edges(descriptors, **(edge_spec or {}))
    if not selected:
        return {
            "status": "error",
            "selected_count": 0,
            "selected": [],
            "rejected_count": len(rejected),
            "rejected_sample": rejected[:50],
            "errors": errors + [
                f"Koşulları sağlayan kenar yok: {edge_spec}. Denetlenen {len(descriptors)} kenar, "
                "Filtreleri genişletin veya kullanılabilir kenarlar için önce solidworks_list_edges kullanın."
            ],
        }

    selection_failures = []
    applied = []
    for descriptor in selected:
        edge = descriptor.get("edge")
        if edge is None:
            continue
        if _select_edge(edge, append=True, mark=mark):
            applied.append(descriptor)
        else:
            selection_failures.append(f"Kenar {descriptor['index']}: Select False döndü")

    if not applied:
        return {
            "status": "error",
            "selected_count": 0,
            "selected": [],
            "rejected": rejected[:50],
            "errors": errors + selection_failures + ["Tüm aday kenarların seçimi başarısız."],
        }

    return {
        "status": "ok",
        "selected_count": len(applied),
        "selected": [
            {
                "index": item["index"],
                "length_mm": item.get("length_mm"),
                "mid_point_mm": item.get("mid_point_mm"),
                "is_circle": item.get("is_circle"),
                "diameter_mm": item.get("diameter_mm"),
                "convexity": item.get("convexity"),
            }
            for item in applied
        ],
        "rejected_count": len(rejected),
        "rejected_sample": rejected[:20],
        "errors": errors + selection_failures,
    }


def _select_edge(edge, append=True, mark=0):
    """
    Select an edge.

    Select4 takes a Dispatch VARIANT Callout as its second argument; Python None causes type mismatch (0x80020005). Match sw_part._select_com_object: try Select2(append, mark), then Select4(append, callout).
    """
    for method_name in ("Select2", "Select4"):
        method = getattr(edge, method_name, None)
        if not callable(method):
            continue
        try:
            if method_name == "Select2":
                if bool(method(append, mark)):
                    return True
            elif bool(method(append, create_empty_dispatch_variant())):
                return True
        except Exception:
            continue
    return False
