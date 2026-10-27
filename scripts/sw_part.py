"""
SOLIDWORKS part modeling utilities.
Common functions for sketching and feature creation.
"""
import weakref
from dataclasses import dataclass
from contextlib import contextmanager

try:
    from .sw_connect import get_com_member
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member
    from sw_preflight import import_com_dependencies


def _callout_variant():
    """
    Construct an empty Callout (Dispatch VARIANT) for Select4.

    Test doubles may lack sw_connect.create_empty_dispatch_variant, so use a defensive import instead of a hard module dependency. Fall back to None when unavailable; Select4 may still work, but versions reporting type mismatch should prefer Select2.
    """
    try:
        from sw_connect import create_empty_dispatch_variant  # type: ignore
    except ImportError:
        try:
            from .sw_connect import create_empty_dispatch_variant  # type: ignore
        except ImportError:
            return None
    try:
        return create_empty_dispatch_variant()
    except Exception:
        return None

pythoncom, _win32com, VARIANT = import_com_dependencies()

PLANE_NAME_ALIASES = {
    "Ön Düzlem": ["Ön Düzlem", "Front Plane"],
    "Üst Düzlem": ["Üst Düzlem", "Top Plane"],
    "Sağ Düzlem": ["Sağ Düzlem", "Right Plane"],
    "Front Plane": ["Front Plane", "Ön Düzlem", "\u524d\u89c6\u57fa\u51c6\u9762"],
    "Top Plane": ["Top Plane", "Üst Düzlem", "\u4e0a\u89c6\u57fa\u51c6\u9762"],
    "Right Plane": ["Right Plane", "Sağ Düzlem", "\u53f3\u89c6\u57fa\u51c6\u9762"],
    "\u524d\u89c6\u57fa\u51c6\u9762": ["\u524d\u89c6\u57fa\u51c6\u9762", "Front Plane"],
    "\u4e0a\u89c6\u57fa\u51c6\u9762": ["\u4e0a\u89c6\u57fa\u51c6\u9762", "Top Plane"],
    "\u53f3\u89c6\u57fa\u51c6\u9762": ["\u53f3\u89c6\u57fa\u51c6\u9762", "Right Plane"],
}

# Escaped legacy prefixes are API lookup aliases, not user-facing prose.
SKETCH_NAME_PREFIX_ALIASES = {
    "Sketch": "\u8349\u56fe",
    "\u8349\u56fe": "Sketch",
    "Çizim": "Sketch",
    "Eskiz": "Sketch",
}


@dataclass
class SketchSelectionRef:
    """
    Store sketch object references instead of relying on name-based SelectByID2("SKETCH") lookup.

    Chinese-localized SOLIDWORKS 2024 may consistently reject name-based SKETCH selection. Retaining references at creation permits later direct Select2 of the sketch, feature, or contour.
    """

    name: str
    sketch: object = None
    feature: object = None
    contours: tuple = ()
    regions: tuple = ()
    segments: tuple = ()
    source: str = ""

    def __str__(self):
        """Behave similarly to legacy plain sketch-name strings."""
        return self.name

    def __eq__(self, other):
        """Compare by name against sketch-name strings for backward compatibility."""
        if isinstance(other, SketchSelectionRef):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return NotImplemented

    def __hash__(self):
        return hash(self.name)


class _SketchCacheEntry:
    """
    Sketch-selection cache entry for one document.

    Retain a weak model reference and _oleobj_ identity to verify ownership. id(ole_object) alone is unsafe: CPython can reuse addresses after COM proxy collection, allowing an old entry to match a new document and create features in the wrong document.
    """

    __slots__ = ("model_ref", "ole_id", "sketches", "fingerprint")

    def __init__(self, model, ole_id):
        self.model_ref = _weak_model(model)
        self.ole_id = ole_id
        self.sketches = {}
        self.fingerprint = None

    def matches(self, model, ole_id):
        """@brief Check whether the entry still belongs to this model."""
        if ole_id is not None and self.ole_id is not None:
            if ole_id != self.ole_id:
                return False
        if self.model_ref is None:
            # This COM proxy does not support weak references; use _oleobj_ identity.
            return ole_id is not None and ole_id == self.ole_id
        alive = self.model_ref()
        if alive is None:
            return False
        return alive is model


def _weak_model(model):
    """@brief Try to create a weak model reference; return None if unsupported."""
    try:
        return weakref.ref(model)
    except TypeError:
        return None


def _document_fingerprint(model):
    """
    Read the owning document fingerprint (title and path).

    Detect active-document changes that invalidate the entire previous cache.
    """
    try:
        document = get_com_member(model, "GetTitle"), get_com_member(model, "GetPathName")
    except Exception:
        return None
    return document


_SKETCH_SELECTION_CACHE = {}
_SKETCH_CACHE_LIMIT = 32


def clear_sketch_selection_cache(model=None):
    """
    Clear the sketch-selection cache.

    Args:
        model: Clear only this document when supplied; None clears all entries.

    Long-running processes such as an MCP server must call this, otherwise cached ISketch COM objects retain closed documents and prevent SOLIDWORKS from releasing them.
    """
    if model is None:
        _SKETCH_SELECTION_CACHE.clear()
        return
    key = _model_cache_key(model)
    _SKETCH_SELECTION_CACHE.pop(key, None)


def _prune_sketch_cache():
    """@brief Evict invalid entries; discard oldest inserted entries when over capacity."""
    for key, entry in list(_SKETCH_SELECTION_CACHE.items()):
        if entry.model_ref is not None and entry.model_ref() is None:
            _SKETCH_SELECTION_CACHE.pop(key, None)
    while len(_SKETCH_SELECTION_CACHE) > _SKETCH_CACHE_LIMIT:
        try:
            _SKETCH_SELECTION_CACHE.pop(next(iter(_SKETCH_SELECTION_CACHE)))
        except StopIteration:
            break


def _get_sketch_cache_entry(model, create=False):
    """@brief Get or create the model cache entry and detect document changes automatically."""
    ole_id = _model_cache_key(model)
    entry = _SKETCH_SELECTION_CACHE.get(ole_id)
    if entry is not None and entry.matches(model, ole_id) and entry.fingerprint == _document_fingerprint(model):
        return entry
    if not create:
        return None
    # Document changed or address reused: discard the old entry to avoid cross-document matches.
    _prune_sketch_cache()
    entry = _SketchCacheEntry(model, ole_id)
    entry.fingerprint = _document_fingerprint(model)
    _SKETCH_SELECTION_CACHE[ole_id] = entry
    return entry


# ============================================================
# Sketch operations
# ============================================================

def _empty_callout():
    """Create an empty Callout argument compatible with SelectByID2."""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _select_by_id(extension, entity_name, entity_type, append=False, mark=0):
    """
    Wrap SelectByID2 to avoid None causing type mismatches in some SOLIDWORKS versions.

    Args:
        extension: ModelDocExtension object.
        entity_name: Entity name.
        entity_type: Entity type string.
        append: Append to the selection when True.
        mark: Selection mark.

    Returns:
        bool.
    """
    return extension.SelectByID2(
        entity_name, entity_type, 0, 0, 0, append, mark, _empty_callout(), 0
    )


def _get_plane_name_candidates(plane_name):
    """
    Get candidate plane names.

    Args:
        plane_name: User-supplied plane name.

    Returns:
        list[str].
    """
    return PLANE_NAME_ALIASES.get(plane_name, [plane_name])


def _get_sketch_name_candidates(sketch_name):
    """
    Get sketch-name candidates with localized prefix compatibility.

    Args:
        sketch_name: Sketch name.

    Returns:
        list[str].
    """
    sketch_name = str(sketch_name)
    candidates = [sketch_name]
    for prefix, alias in SKETCH_NAME_PREFIX_ALIASES.items():
        if sketch_name.startswith(prefix):
            suffix = sketch_name[len(prefix):]
            for candidate_prefix in (alias, "Sketch", "Eskiz", "Çizim"):
                alias_name = candidate_prefix + suffix
                if alias_name not in candidates:
                    candidates.append(alias_name)
    return candidates


def _as_tuple(value):
    """Normalize a COM single object, SAFEARRAY, or None to a tuple."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(item for item in value if item is not None)
    if isinstance(value, list):
        return tuple(item for item in value if item is not None)
    return (value,)


def _safe_com_member(obj, attr_name, *args, default=None):
    """Read COM members with a default fallback so diagnostics cannot raise another COM error."""
    if obj is None:
        return default
    try:
        value = get_com_member(obj, attr_name, *args)
        return default if value is None else value
    except Exception:
        return default


def _model_cache_key(model):
    """Build a model cache key scoped to the current Python process."""
    ole_object = getattr(model, "_oleobj_", None)
    if ole_object is not None:
        return id(ole_object)
    return id(model)


def _cache_name_variants(sketch_name):
    """Build sketch cache names with localized default-prefix compatibility."""
    variants = []
    for candidate in _get_sketch_name_candidates(sketch_name):
        if candidate not in variants:
            variants.append(candidate)
    return variants


def _cache_sketch_ref(model, sketch_ref):
    """Cache sketch object references to bypass later SelectByID2("SKETCH") calls."""
    if not sketch_ref or not sketch_ref.name:
        return sketch_ref
    entry = _get_sketch_cache_entry(model, create=True)
    for candidate in _cache_name_variants(sketch_ref.name):
        entry.sketches[candidate] = sketch_ref
    return sketch_ref


def _find_cached_sketch_ref(model, sketch_name):
    """Find sketch object references in the current-process cache."""
    if isinstance(sketch_name, SketchSelectionRef):
        return sketch_name

    entry = _get_sketch_cache_entry(model, create=False)
    if entry is None:
        return None
    for candidate in _cache_name_variants(sketch_name):
        cached = entry.sketches.get(candidate)
        if cached:
            return cached
    return None


def _capture_sketch_ref(model, sketch_obj=None, fallback="Sketch1", source=""):
    """Extract reusable selection references from the active or supplied sketch."""
    if sketch_obj is None:
        sketch_obj = _safe_com_member(model.SketchManager, "ActiveSketch")
    if sketch_obj is None:
        return None

    sketch_name = _safe_com_member(sketch_obj, "Name", default=fallback) or fallback
    sketch_ref = SketchSelectionRef(
        name=sketch_name,
        sketch=sketch_obj,
        feature=_safe_com_member(sketch_obj, "GetFeature"),
        contours=_as_tuple(_safe_com_member(sketch_obj, "GetSketchContours")),
        regions=_as_tuple(_safe_com_member(sketch_obj, "GetSketchRegions")),
        segments=_as_tuple(_safe_com_member(sketch_obj, "GetSketchSegments")),
        source=source,
    )
    return _cache_sketch_ref(model, sketch_ref)


def _refresh_sketch_ref(sketch_ref):
    """Refresh Feature/Contour references after exiting the sketch."""
    if not sketch_ref or sketch_ref.sketch is None:
        return sketch_ref
    feature = _safe_com_member(sketch_ref.sketch, "GetFeature")
    contours = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchContours"))
    regions = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchRegions"))
    segments = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchSegments"))
    if feature is not None:
        sketch_ref.feature = feature
    if contours:
        sketch_ref.contours = contours
    if regions:
        sketch_ref.regions = regions
    if segments:
        sketch_ref.segments = segments
    return sketch_ref


def _select_first_candidate(extension, candidate_names, entity_type, append=False, mark=0):
    """
    Try selecting entities by candidate name in order.

    Args:
        extension: ModelDocExtension.
        candidate_names: Candidate names.
        entity_type: Entity type string.
        append: Append selection when True.
        mark: Selection mark.

    Returns:
        str | None.
    """
    for candidate_name in candidate_names:
        if _select_by_id(extension, candidate_name, entity_type, append=append, mark=mark):
            return candidate_name
    return None


def _get_selection_count(model):
    """
    Get the current selection count.

    Args:
        model: IModelDoc2.

    Returns:
        int.
    """
    selection_manager = model.SelectionManager
    count_member = getattr(selection_manager, "GetSelectedObjectCount2")
    return count_member(-1) if callable(count_member) else int(count_member)


def _select_com_object(obj, append=False, mark=0):
    """Select through object Select2/Select4, preferring to avoid SelectByID2 name resolution."""
    if obj is None:
        return False
    for method_name in ("Select2", "Select4"):
        method = getattr(obj, method_name, None)
        if not method:
            continue
        try:
            if method_name == "Select2":
                if bool(method(append, mark)):
                    return True
            elif bool(method(append, _empty_callout())):
                return True
        except Exception:
            continue
    return False


def _select_any_object(objects, append=False, mark=0):
    """Try selecting all supplied COM objects; succeed if at least one is selected."""
    selected_count = 0
    for obj in _as_tuple(objects):
        if _select_com_object(obj, append=(append or selected_count > 0), mark=mark):
            selected_count += 1
    return selected_count > 0


def _select_sketch_ref(model, sketch_ref, mark=0):
    """
    Select sketch references in a stable priority order.

    Contours/regions match FeatureExtrusion3 preselection requirements best; fall back to sketch Feature or Sketch objects when unavailable.
    """
    if not sketch_ref:
        return False
    model.ClearSelection2(True)
    _refresh_sketch_ref(sketch_ref)
    for objects in (
        sketch_ref.feature,
        sketch_ref.sketch,
        sketch_ref.contours,
        sketch_ref.regions,
        sketch_ref.segments,
    ):
        if _select_any_object(objects, append=False, mark=mark):
            return True
        model.ClearSelection2(True)
    return False


def _select_sketch_feature_by_name(model, sketch_name, mark=0):
    """Find a sketch feature with FeatureByName, then select the object directly."""
    for candidate in _get_sketch_name_candidates(sketch_name):
        feature = _safe_com_member(model, "FeatureByName", candidate)
        if feature and _select_com_object(feature, append=False, mark=mark):
            return candidate
    return None


def _ensure_sketch_selected(model, sketch_name):
    """
    Ensure a usable sketch selection before extrusion/cutting.

    Args:
        model: IModelDoc2.
        sketch_name: Sketch name.

    Returns:
        str.
    """
    if str(sketch_name) == "__current_selection__" and _get_selection_count(model) > 0:
        return "__current_selection__"

    active_ref = _capture_sketch_ref(model, fallback=str(sketch_name), source="active")
    if active_ref and _select_sketch_ref(model, active_ref):
        return active_ref.name

    cached_ref = _find_cached_sketch_ref(model, sketch_name)
    if cached_ref and _select_sketch_ref(model, cached_ref):
        return cached_ref.name

    selected_feature = _select_sketch_feature_by_name(model, sketch_name)
    if selected_feature:
        return selected_feature

    selected_sketch = _select_first_candidate(
        model.Extension, _get_sketch_name_candidates(sketch_name), "SKETCH"
    )
    if not selected_sketch:
        model.ClearSelection2(True)
        raise ValueError(
            f"Sketch seçilemedi: {sketch_name}. Etkin Sketch nesnesi, önbellekteki Sketch nesnesi, "
            "FeatureByName ve SelectByID2('SKETCH')."
        )
    return selected_sketch


def start_sketch(model, plane_name="Front Plane"):
    """
    Start a sketch on a reference plane.

    Args:
        model: IModelDoc2.
        plane_name: Reference-plane name, such as "Front Plane", "Top Plane", or "Right Plane"; localized aliases are supported.
    """
    model.ClearSelection2(True)

    selected_plane = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(plane_name), "PLANE"
    )
    if selected_plane:
        model.SketchManager.InsertSketch(True)
        return selected_plane

    raise ValueError(f"Düzlem seçilemedi: {plane_name}")


def end_sketch(model):
    """
    Exit the current sketch and return a reusable selection reference.

    Existing callers may ignore the result; pass it to extrude_boss(), extrude_cut(), or other feature functions for stable selection.
    """
    sketch_ref = _capture_sketch_ref(model, source="end_sketch")
    model.SketchManager.InsertSketch(True)
    return _cache_sketch_ref(model, _refresh_sketch_ref(sketch_ref))


@contextmanager
def sketch(model, plane_name="Front Plane"):
    """
    Sketch context manager.

    Example:
        with sketch(model, "Front Plane") as sketch_ref:
            sketch_circle(model, 0, 0, mm(25))
        extrude_boss(model, sketch_ref, mm(50))

    Yields:
        SketchSelectionRef, retaining sketch references and contour/region collections for direct object Select2. This avoids name-based SelectByID2 failures in localized versions or after rebuilds. __str__ returns the sketch name for compatibility with legacy string comparisons and formatting.
    """
    start_sketch(model, plane_name)
    sketch_ref = None
    try:
        sketch_ref = _capture_sketch_ref(model, source="context")
        yield sketch_ref if sketch_ref else current_sketch_name(model)
    finally:
        finished_ref = end_sketch(model)
        if sketch_ref and finished_ref:
            sketch_ref.feature = finished_ref.feature
            sketch_ref.contours = finished_ref.contours
            sketch_ref.regions = finished_ref.regions
            sketch_ref.segments = finished_ref.segments
            _cache_sketch_ref(model, sketch_ref)


def current_sketch_name(model, fallback="Sketch1"):
    """
    Get the current sketch name.

    Args:
        model: IModelDoc2.
        fallback: Default name when the current sketch cannot be read.
    """
    active_sketch = model.SketchManager.ActiveSketch
    if active_sketch:
        return active_sketch.Name
    return fallback


def sketch_line(model, x1, y1, x2, y2):
    """Draw a line (meters)."""
    return model.SketchManager.CreateLine(x1, y1, 0, x2, y2, 0)


def sketch_rectangle(model, cx, cy, w, h):
    """Draw a center rectangle (meters)."""
    return model.SketchManager.CreateCenterRectangle(
        cx, cy, 0, cx + w / 2, cy + h / 2, 0
    )


def sketch_corner_rectangle(model, x1, y1, x2, y2):
    """Draw a corner rectangle (meters)."""
    return model.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0)


def sketch_circle(model, cx, cy, radius):
    """Draw a circle (meters)."""
    return model.SketchManager.CreateCircleByRadius(cx, cy, 0, radius)


def sketch_arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    """
    Draw an arc.

    Args:
        cx, cy: Center coordinates in meters.
        x1, y1: Start coordinates.
        x2, y2: End coordinates.
        direction: 1=counterclockwise, -1=clockwise.
    """
    return model.SketchManager.CreateArc(cx, cy, 0, x1, y1, 0, x2, y2, 0, direction)


def sketch_polygon(model, cx, cy, radius, sides=6):
    """Draw a regular polygon using an inscribed circle."""
    return model.SketchManager.CreatePolygon(cx, cy, 0, cx + radius, cy, 0, sides, True)


def sketch_slot(model, x1, y1, x2, y2, radius):
    """Draw a slot."""
    return model.SketchManager.CreateSketchSlot(
        0,  # swSketchSlotCreationType_e: 0=Straight
        radius, radius,  # Width
        x1, y1, 0,
        x2, y2, 0,
        0, 0, 0,
        1, False
    )


def sketch_spline(model, points):
    """
    Draw a spline.

    Args:
        points: Control points [(x1,y1), (x2,y2), ...] in meters.
    """
    import array
    point_array = array.array('d')
    for x, y in points:
        point_array.extend([x, y, 0.0])
    return model.SketchManager.CreateSpline2(point_array, False)


def auto_dimension_sketch(model, sketch=None, sketch_segments=None):
    """@brief Create actual sketch dimensions using the official AutoDimension2 workflow.

    Drawing InsertModelAnnotations imports existing display dimensions; it cannot invent dimensions for extrusion depths or rectangular profiles. In sketch edit mode, select horizontal/vertical datum lines and call ISketch.AutoDimension2. The resulting DisplayDimensions belong to the model and can be imported and reviewed in drawings.

    Return status_code (officially 0 for success), selection count, and auditable dimension-creation evidence. Never disguise a failure as success.
    """
    active = sketch or _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None:
        return {"status": "blocked", "status_code": None, "error_code": "SKETCH_NOT_ACTIVE", "selected": 0}

    def segments():
        supplied = _as_tuple(sketch_segments)
        if supplied:
            return supplied
        for name in ("GetSketchSegments", "IGetSketchSegments"):
            value = _safe_com_member(active, name)
            result = _as_tuple(value)
            if result:
                return result
        return ()

    horizontal = None
    vertical = None
    for segment in segments():
        try:
            start = get_com_member(segment, "GetStartPoint2")
            end = get_com_member(segment, "GetEndPoint2")
            dx = abs(float(get_com_member(start, "X")) - float(get_com_member(end, "X")))
            dy = abs(float(get_com_member(start, "Y")) - float(get_com_member(end, "Y")))
        except Exception:
            continue
        if dx > dy and horizontal is None:
            horizontal = segment
        elif dy > dx and vertical is None:
            vertical = segment

    model.ClearSelection2(True)
    selected = 0
    # SW2024 swAutodimMark_e: 2=horizontal datum, 4=vertical datum.
    # The official example uses a vertical line as horizontal datum and a horizontal line as vertical datum.
    for segment, mark in ((vertical, 2), (horizontal, 4)):
        if segment is None:
            continue
        try:
            if bool(segment.Select3(selected > 0, mark, _empty_callout())):
                selected += 1
        except Exception:
            try:
                if bool(segment.Select4(selected > 0, _empty_callout())):
                    selected += 1
            except Exception:
                pass

    status_code = None
    try:
        # swAutodimEntitiesAll=1, Baseline=1, Below=-1, Left=-1.
        status_code = int(get_com_member(active, "AutoDimension2", 1, 1, -1, 1, -1))
    except Exception as exc:
        model.ClearSelection2(True)
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "SKETCH_AUTODIMENSION_CALL_FAILED",
            "error": str(exc),
            "selected": selected,
        }
    try:
        model.GraphicsRedraw2()
    except Exception:
        pass
    model.ClearSelection2(True)
    return {
        "status": "pass" if status_code == 0 else "blocked",
        "status_code": status_code,
        "error_code": None if status_code == 0 else "SKETCH_AUTODIMENSION_REJECTED",
        "selected": selected,
    }


def add_dimension(model, x, y):
    """Add a dimension at a specified position."""
    return model.AddDimension2(x, y, 0)


def add_sketch_relation(model, relation_type):
    """
    Add a sketch geometric relation.

    Common relation_type values:
        "sgFIXED", "sgHORIZONTAL", "sgVERTICAL", "sgCOLINEAR",
        "sgPARALLEL", "sgPERPENDICULAR", "sgTANGENT", "sgCONCENTRIC",
        "sgEQUAL", "sgSYMMETRIC", "sgMIDPOINT", "sgCOINCIDENT".
    """
    return model.SketchAddConstraints(relation_type)


# ============================================================
# Feature operations
# ============================================================

def extrude_boss(model, sketch_name, depth, direction=True, merge=True):
    """
    Extrude a boss.

    Args:
        model: IModelDoc2.
        sketch_name: Sketch name, such as "Sketch1".
        depth: Extrusion depth in meters.
        direction: True reverses the default sketch-normal direction.
        merge: Merge results when True.
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: single-direction extrusion
        False,        # Flip
        direction,    # Dir: extrusion direction
        0,            # T1: Blind
        0,            # T2: Blind
        depth,        # D1
        0.0,          # D2
        False,        # Dchk1
        False,        # Dchk2
        False,        # Ddir1
        False,        # Ddir2
        0.0,          # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        merge,        # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0: start from the sketch plane
        0.0,          # StartOffset
        False         # FlipStartOffset
    )


def extrude_cut(model, sketch_name, depth, direction=True, flip=False):
    """
    Extruded cut.

    Args:
        model: IModelDoc2.
        sketch_name: Sketch name.
        depth: Cut depth in meters; 0 means through-all.
        direction: True reverses the default direction opposite to sketch normal.
        flip: True cuts outside the profile; False cuts inside.
    """
    _ensure_sketch_selected(model, sketch_name)
    if depth == 0:
        # Through-all
        end_condition = 1  # swEndCondThroughAll
        depth = 0.01  # Placeholder value
    else:
        end_condition = 0  # swEndCondBlind

    return model.FeatureManager.FeatureCut4(
        True, bool(flip), bool(direction),  # Sd, Flip, Dir
        end_condition, 0, depth, 0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False,
        True, True, False, False,  # assembly-scope flags -> False for part docs
        False, 0, 0, False, False
    )


def extrude_midplane(model, sketch_name, total_depth):
    """
    Mid-plane extrusion, symmetric on both sides.

    Args:
        total_depth: Total depth in meters; each side is total_depth/2.
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: single-direction definition, with end condition set to mid-plane
        False,        # Flip
        True,         # Dir
        6,            # T1: swEndCondMidPlane
        0,            # T2
        total_depth,  # D1
        0.0,          # D2
        False,        # Dchk1
        False,        # Dchk2
        False,        # Ddir1
        False,        # Ddir2
        0.0,          # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        True,         # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0
        0.0,          # StartOffset
        False         # FlipStartOffset
    )


def revolve_boss(model, sketch_name, angle_rad, axis_sketch_name=None):
    """
    Revolved boss.

    Args:
        sketch_name: Profile sketch name.
        angle_rad: Revolution angle in radians; 2*pi is 360 degrees.
        axis_sketch_name: Axis sketch name; None requires a preselected axis.
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureRevolve2(
        True, True, False,
        False, False, False,
        0, 0,
        angle_rad, 0,
        False, False,
        0.0, 0.0,
        0, 0, 0, True, True, True
    )


def fillet(model, radius, edges=None):
    """
    Create a constant-radius fillet.

    Args:
        model: IModelDoc2.
        radius: Fillet radius in meters.
        edges: Edges to select; None uses the current selection.

    Returns:
        IFeature or None.

    IFeatureManager::FeatureFillet takes four arguments: (Options, Radius, R1, R2). Passing seven arguments with trailing None raises a non-optional-argument error (0x8002000F) on SOLIDWORKS 2024/2026 in upstream machine checks. Older documentation/wrappers were misleading.

    Explicitly validate edge selection: with an empty set SOLIDWORKS may fillet the current profile and create an unintended feature.
    """
    if edges is not None:
        for edge in edges:
            try:
                edge.Select2(True, 0)
            except Exception:
                try:
                    edge.Select4(True, _callout_variant())
                except Exception:
                    continue
    if _get_selection_count(model) <= 0:
        raise ValueError(
            "Fillet öncesinde kenar seçin. Geometri koşullarıyla select_edges() kullanın "
            "veya kullanılabilir kenarları solidworks_list_edges ile görüntüleyin."
        )
    return model.FeatureManager.FeatureFillet(195, radius, 0, 0)


def chamfer(model, distance, angle_deg=45):
    """
    Create a chamfer.

    Args:
        distance: Chamfer distance in meters.
        angle_deg: Chamfer angle in degrees.
    """
    import math
    angle_rad = angle_deg * math.pi / 180.0
    return model.FeatureManager.InsertFeatureChamfer(
        4, 1, distance, angle_rad, 0, 0, 0, 0
    )


def linear_pattern(model, feature_name, d1_x, d1_y, d1_z, d1_spacing, d1_count,
                    d2_x=0, d2_y=0, d2_z=0, d2_spacing=0, d2_count=1):
    """
    Create a linear pattern.

    Args:
        feature_name: Seed feature name.
        d1_*: First direction vector, spacing in meters, and count.
        d2_*: Optional second direction.
    """
    try:
        from .sw_pattern import linear_pattern as create_pattern
    except ImportError:
        from sw_pattern import linear_pattern as create_pattern
    return create_pattern(model, feature_name, (d1_x, d1_y, d1_z), d1_spacing, d1_count,
        (d2_x, d2_y, d2_z), d2_spacing, d2_count)


def circular_pattern(model, feature_name, axis_name, angle_rad, count, equal_spacing=True):
    """
    Create a circular pattern.

    Args:
        feature_name: Seed feature name.
        axis_name: Rotation axis name.
        angle_rad: Total angle in radians.
        count: Number of instances.
        equal_spacing: Equal spacing when True.
    """
    try:
        from .sw_pattern import circular_pattern as create_pattern
    except ImportError:
        from sw_pattern import circular_pattern as create_pattern
    return create_pattern(model, feature_name, axis_name, angle_rad, count, equal_spacing)


def shell(model, thickness, faces_to_remove=None):
    """
    Create a shell.

    Args:
        thickness: Wall thickness in meters.
        faces_to_remove: Faces requiring preselection for removal.
    """
    return model.FeatureManager.InsertFeatureShell(thickness, False)


def mirror_feature(model, feature_name, mirror_plane_name):
    """
    Mirror a feature.

    Args:
        feature_name: Feature to mirror.
        mirror_plane_name: Mirror plane name.
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, mirror_plane_name, "PLANE", append=True, mark=1)
    return model.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)


def hole_wizard(model, hole_type, standard, fastener_type, size, depth, x, y, z):
    """
    Simplified Hole Wizard scaffold.
    Full Hole Wizard parameters are complex; consult target-version API documentation before adjusting.
    """
    # Hole Wizard uses FeatureManager.HoleWizard5.
    # Parameters depend on hole type; this is a scaffold.
    pass


def rib(model, sketch_name, thickness, direction=True):
    """
    Create a rib.

    Args:
        sketch_name: Rib profile sketch name.
        thickness: Rib thickness in meters.
        direction: Extrusion direction.
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.InsertRib(
        direction, False, thickness, 0, False, False, False, 0, False
    )
