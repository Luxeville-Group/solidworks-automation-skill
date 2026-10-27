"""@brief Adapt native pattern parameters/selections using existing B-Rep edge selection; no new user entry point."""
from __future__ import annotations

import math

try:
    from .sw_connect import create_empty_dispatch_variant, get_com_member
    from .sw_edge_select import iter_model_edges
except ImportError:
    from sw_connect import create_empty_dispatch_variant, get_com_member
    from sw_edge_select import iter_model_edges


def _unit(vector):
    """@brief Validate and normalize direction; direction is not a length."""
    values = tuple(float(value) for value in vector)
    if len(values) != 3:
        raise ValueError("Pattern yönü üç bileşen içermeli")
    length = math.sqrt(sum(value * value for value in values))
    if not all(math.isfinite(value) for value in values) or length < 1e-12:
        raise ValueError("Pattern yönü sıfır olmayan sonlu bir vektör olmalı")
    return tuple(value / length for value in values)


def _seed(model, name):
    """@brief Select the exact seed feature; stop immediately on failure."""
    feature = get_com_member(model, "FeatureByName", str(name))
    if feature is None or not bool(get_com_member(feature, "Select2", False, 4)):
        raise ValueError(f"Pattern ana özelliği seçilemedi: {name}")


def _select_entity(model, entity, mark, append=True):
    """@brief Select entities with marked ISelectData and preserve failure evidence."""
    data = get_com_member(model.SelectionManager, "CreateSelectData")
    data.Mark = int(mark)
    return bool(get_com_member(entity, "Select4", append, data))


def _direction(model, vector, mark):
    """@brief Parallel straight edges in the same direction are semantically equivalent; choose one deterministically."""
    requested = _unit(vector)
    descriptors, _ = iter_model_edges(model)
    candidates = []
    for item in descriptors:
        direction = item.get("direction")
        if item.get("is_line") is not True or direction is None:
            continue
        dot = sum(a * b for a, b in zip(requested, direction))
        if abs(dot) >= 1 - 1e-8:
            candidates.append((item, dot))
    candidates.sort(key=lambda pair: (-(pair[0].get("length_mm") or 0), pair[0]["index"]))
    for item, dot in candidates:
        try:
            selected = _select_entity(model, item["edge"], mark)
        except Exception:
            selected = False
        if selected:
            return dot < 0
    raise ValueError(f"Pattern yönü için seçilebilir düz kenar yok: {requested}")


def linear_pattern(model, feature_name, first, spacing, count, second=(0, 0, 0), second_spacing=0, second_count=1):
    """@brief Create a 20-argument FeatureLinearPattern4; use the older 10-argument route only if the member is absent.
    @param model Native part document.
    @param first First direction vector.
    @param spacing Spacing in meters.
    @param count Instance count including the seed.
    @return IFeature; raise execution failure on an empty result.
    """
    if int(count) < 2 or int(second_count) < 1 or not math.isfinite(float(spacing)) or spacing <= 0:
        raise ValueError("Pattern sayısı veya aralığı geçersiz")
    if second_count > 1 and (not math.isfinite(float(second_spacing)) or second_spacing <= 0):
        raise ValueError("İkinci yön aralığı geçersiz")
    model.ClearSelection2(True)
    try:
        _seed(model, feature_name)
        flip1 = _direction(model, first, 1)
        flip2 = _direction(model, second, 2) if second_count > 1 else False
        args = (int(count), float(spacing), int(second_count), float(second_spacing),
                flip1, flip2, "", "", False, False)
        method = getattr(model.FeatureManager, "FeatureLinearPattern4", None)
        if method is not None:
            feature = method(*args, False, False, False, False, False, False, False, False, 0.0, 0.0)
        else:
            feature = model.FeatureManager.FeatureLinearPattern3(*args)
        if feature is None:
            raise RuntimeError("Yerel Linear Pattern oluşturulamadı")
        return feature
    finally:
        model.ClearSelection2(True)


def circular_pattern(model, feature_name, axis, angle, count, equal_spacing=True):
    """@brief Select the seed feature and explicit axis entity; preserve the existing seven-argument native interface."""
    if int(count) < 2 or not math.isfinite(float(angle)) or not 0 < angle <= 2 * math.pi + 1e-9:
        raise ValueError("Circular Pattern sayısı veya açısı geçersiz")
    model.ClearSelection2(True)
    try:
        _seed(model, feature_name)
        if isinstance(axis, str):
            selected = bool(model.Extension.SelectByID2(axis, "AXIS", 0, 0, 0, True, 1,
                create_empty_dispatch_variant(), 0))
        else:
            selected = _select_entity(model, axis, 1)
        if not selected:
            raise ValueError(f"Circular Pattern ekseni seçilemedi: {axis}")
        feature = model.FeatureManager.FeatureCircularPattern4(int(count), float(angle), False, "", False, bool(equal_spacing), False)
        if feature is None:
            raise RuntimeError("Yerel Circular Pattern oluşturulamadı")
        return feature
    finally:
        model.ClearSelection2(True)
