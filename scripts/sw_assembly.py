"""
SOLIDWORKS assembly utilities.

Wrap error-prone COM workflows: component resolution, assembly-context entity mapping, actual Mate creation, and motion assembly validation. SOLIDWORKS API lengths are in meters.
"""
import math
import os

try:
    from .sw_preflight import import_com_dependencies
    from .sw_connect import open_document, safe_get_com_member
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import open_document, safe_get_com_member

pythoncom, _win32com, VARIANT = import_com_dependencies()


SW_MATE_COINCIDENT = 0
SW_MATE_CONCENTRIC = 1
SW_MATE_PARALLEL = 3
SW_MATE_DISTANCE = 5
SW_MATE_GEAR = 10
SW_ADD_MATE_ERROR_UNKNOWN = 0
SW_ADD_MATE_ERROR_NO_ERROR = 1
SW_COMPONENT_SUPPRESSED = 0
SW_COMPONENT_LIGHTWEIGHT = 1
SW_COMPONENT_FULLY_RESOLVED = 2
SW_COMPONENT_RESOLVED = 3
SW_SOLID_BODY = 0
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


def _as_alias_list(aliases):
    """Normalize a string or sequence to a nonempty list of names."""
    if isinstance(aliases, str):
        return [aliases]
    names = [str(item) for item in aliases if str(item)]
    if not names:
        raise ValueError("aliases boş olamaz")
    return names


def _active_solidworks_app():
    """Get the currently running SOLIDWORKS application object."""
    try:
        return _win32com.GetActiveObject("SldWorks.Application")
    except Exception:
        return None


def _activate_model_document(sw, model):
    """Activate a document with support for the ActivateDoc3 by-ref error argument."""
    if sw is None or model is None:
        return False
    title = safe_get_com_member(model, "GetTitle")
    if not title:
        return False
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        return sw.ActivateDoc3(title, False, 0, errors) is not None
    except Exception:
        try:
            sw.ActivateDoc2(title, False, errors)
            return True
        except Exception:
            return False


def _add_component5(asm_model, component_path, config_name, x, y, z):
    """Call the SW2024-compatible AddComponent5 signature."""
    add_component5 = getattr(asm_model, "AddComponent5", None)
    if not add_component5:
        return None
    return add_component5(
        component_path,
        0,              # swAddComponentConfigOptions_e: use the specified/default configuration.
        "",
        False,
        config_name or "",
        float(x),
        float(y),
        float(z),
    )


def _add_component4(asm_model, component_path, config_name, x, y, z):
    """Call AddComponent4."""
    return asm_model.AddComponent4(
        component_path,
        config_name or "",
        float(x),
        float(y),
        float(z),
    )


def add_component(asm_model, part_path, x=0, y=0, z=0, config_name="", sw=None):
    """
    Add a component to an assembly.

    Args:
        asm_model: IAssemblyDoc assembly document.
        part_path: Part/subassembly file path.
        x, y, z: Placement coordinates in meters.
        config_name: Configuration name; empty uses the default.
        sw: Optional SOLIDWORKS application for opening the part and switching back to the assembly if AddComponent fails.

    Returns:
        IComponent2 object.
    """
    component_path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(part_path))))
    if not os.path.exists(component_path):
        raise FileNotFoundError(f"Bileşen dosyası yok: {component_path}")

    component = None
    errors = []

    try:
        # AddComponent4 may return None with Chinese-localized SW2024 and pywin32;
        # the eight-argument AddComponent5 signature is more stable.
        component = _add_component5(asm_model, component_path, config_name, x, y, z)
    except Exception as exc:
        errors.append(f"AddComponent5: {exc}")

    if component is None:
        try:
            component = _add_component4(asm_model, component_path, config_name, x, y, z)
        except Exception as exc:
            errors.append(f"AddComponent4: {exc}")

    if component is None:
        sw = sw or _active_solidworks_app()
        if sw is not None:
            try:
                opened = open_document(sw, component_path, read_only=False, silent=True)
                if opened is None:
                    errors.append("OpenDoc6: None döndü")
                elif _activate_model_document(sw, asm_model):
                    component = _add_component5(
                        asm_model,
                        component_path,
                        config_name,
                        x,
                        y,
                        z,
                    )
                    if component is None:
                        errors.append("open_then_AddComponent5: None döndü")
                else:
                    errors.append("ActivateDoc: montaj yeniden etkinleştirilemedi")
            except Exception as exc:
                errors.append(f"open_then_AddComponent5: {exc}")
        else:
            errors.append("GetActiveObject(SldWorks.Application): None döndü")

    if component:
        print(f"Bileşen eklendi: {component_path}")
    else:
        detail = "; ".join(errors) if errors else "AddComponent5 ve AddComponent4 None döndürdü"
        print(f"Bileşen eklenemedi: {component_path} ({detail})")
    return component


def resolve_component(component, state=SW_COMPONENT_FULLY_RESOLVED):
    """
    @brief Resolve a component to Resolved/FullyResolved state.
    @param component IComponent2 object.
    @param state swComponentSuppressionState_e; default 2=swComponentFullyResolved.
    @return SetSuppression2 result; try 3=swComponentResolved if the primary state fails.
    """
    if component is None:
        raise ValueError("component boş olamaz")
    try:
        return component.SetSuppression2(state)
    except Exception:
        if state != SW_COMPONENT_RESOLVED:
            return component.SetSuppression2(SW_COMPONENT_RESOLVED)
        raise


def get_component_model(component, resolve=True, raise_on_error=True):
    """
    @brief Get the part/subassembly document referenced by a component.
    @param component IComponent2 object.
    @param resolve Resolve first; lightweight or suppressed components may cause GetModelDoc2 to return None.
    @param raise_on_error Whether to raise on failure.
    @return IModelDoc2, or None on failure when raise_on_error=False.
    """
    if component is None:
        if raise_on_error:
            raise ValueError("component boş olamaz")
        return None
    if resolve:
        resolve_component(component)
    model = safe_get_com_member(component, "GetModelDoc2")
    if model is None and raise_on_error:
        name = safe_get_com_member(component, "Name2")
        raise RuntimeError(f"Bileşen resolved veya yüklü değil; parça belgesi okunamıyor: {name}")
    return model


def get_component_feature(component, aliases, resolve=True):
    """
    @brief Find an internal component feature by candidate names.
    @param component IComponent2 object.
    @param aliases Candidate feature names, such as ["Front Plane", "Front"].
    @param resolve Whether to resolve the component first.
    @return IFeature object.
    """
    model = get_component_model(component, resolve=resolve)
    names = []
    for alias in _as_alias_list(aliases):
        for candidate in PLANE_NAME_ALIASES.get(alias, [alias]):
            if candidate not in names:
                names.append(candidate)
    for name in names:
        feature = safe_get_com_member(model, "FeatureByName", name)
        if feature:
            return feature
    comp_name = safe_get_com_member(component, "Name2")
    raise RuntimeError(f"Bileşen {comp_name} eksik özellik: {names}")


def get_assembly_entity(component, feature_or_face):
    """
    @brief Map a part-document object to the assembly context of this component instance.
    @param component IComponent2 object.
    @param feature_or_face Part-level IFeature, IFace2, ISketchSegment, or similar object.
    @return Assembly-context object usable with Select2 to create a Mate.
    """
    entity = component.GetCorresponding(feature_or_face)
    if entity is None:
        comp_name = safe_get_com_member(component, "Name2")
        raise RuntimeError(f"Montaj bağlamı varlığı eşlenemedi: {comp_name}")
    return entity


def get_component_feature_entity(component, aliases, resolve=True):
    """
    @brief Find an internal component feature and map it to assembly context.
    @param component IComponent2 object.
    @param aliases Candidate feature names.
    @param resolve Whether to resolve first.
    @return Assembly-context entity.
    """
    feature = get_component_feature(component, aliases, resolve=resolve)
    return get_assembly_entity(component, feature)


def find_largest_cylinder_face(component, min_radius=0.0, max_radius=None, resolve=True):
    """
    @brief Find the largest-area cylindrical face within a radius range.
    @param component IComponent2 object.
    @param min_radius Minimum radius in meters.
    @param max_radius Maximum radius in meters; None means unlimited.
    @param resolve Whether to resolve first.
    @return Cylindrical IFace2 in assembly context.
    """
    part = get_component_model(component, resolve=resolve)
    max_radius = float("inf") if max_radius is None else float(max_radius)
    best_face = None
    best_area = -1.0
    bodies = safe_get_com_member(part, "GetBodies2", SW_SOLID_BODY, False) or []
    for body in bodies:
        faces = safe_get_com_member(body, "GetFaces") or []
        for face in faces:
            surface = safe_get_com_member(face, "GetSurface")
            if not surface:
                continue
            try:
                if not safe_get_com_member(surface, "IsCylinder"):
                    continue
                params = safe_get_com_member(surface, "CylinderParams")
                radius = float(params[6])
                if radius < min_radius or radius > max_radius:
                    continue
                area = float(safe_get_com_member(face, "GetArea"))
                if area > best_area:
                    best_area = area
                    best_face = face
            except Exception:
                continue

    if best_face is None:
        comp_name = safe_get_com_member(component, "Name2")
        raise RuntimeError(
            f"Silindirik yüz bulunamadı: {comp_name}, radius=[{min_radius}, {max_radius}]"
        )
    return get_assembly_entity(component, best_face)


def select_entities_for_mate(model, entity1, entity2, mark=1):
    """
    @brief Select two assembly-context entities and check the selection count.
    @param model IModelDoc2/IAssemblyDoc object.
    @param entity1 First Mate entity.
    @param entity2 Second Mate entity.
    @param mark SOLIDWORKS selection mark, normally 1 for a standard Mate.
    @return True.
    """
    model.ClearSelection2(True)
    if not entity1.Select2(False, mark):
        raise RuntimeError("İlk Mate varlığı seçilemedi")
    if not entity2.Select2(True, mark):
        raise RuntimeError("İkinci Mate varlığı seçilemedi")
    selected_count = model.SelectionManager.GetSelectedObjectCount2(-1)
    if selected_count != 2:
        model.ClearSelection2(True)
        raise RuntimeError(f"Mate seçim sayısı yanlış: selected={selected_count}, expected=2")
    return True


def add_mate5_checked(
    asm_model,
    mate_type,
    align=0,
    flip=False,
    distance=0.0,
    distance_upper=None,
    distance_lower=None,
    gear_num=0.0,
    gear_den=0.0,
    angle=0.0,
    angle_upper=None,
    angle_lower=None,
    for_positioning_only=False,
    lock_rotation=False,
    width_mate_option=0,
    name=None,
    clear_selection=True,
):
    """
    @brief Create a Mate using the 15-argument AddMate5 in SOLIDWORKS 2015+ and check its error code.
    @param asm_model IAssemblyDoc/IModelDoc2 assembly object.
    @param mate_type swMateType_e value.
    @param gear_num Gear ratio numerator, used only by Gear Mate.
    @param gear_den Gear ratio denominator, used only by Gear Mate.
    @param lock_rotation Lock concentric rotation; default to False for motion models.
    @param name Optional Mate name.
    @return Mate2 object.
    """
    distance_upper = distance if distance_upper is None else distance_upper
    distance_lower = distance if distance_lower is None else distance_lower
    angle_upper = angle if angle_upper is None else angle_upper
    angle_lower = angle if angle_lower is None else angle_lower
    error_status = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    mate = asm_model.AddMate5(
        int(mate_type),
        int(align),
        bool(flip),
        float(distance),
        float(distance_upper),
        float(distance_lower),
        float(gear_num),
        float(gear_den),
        float(angle),
        float(angle_upper),
        float(angle_lower),
        bool(for_positioning_only),
        bool(lock_rotation),
        int(width_mate_option),
        error_status,
    )
    # swAddMateError_e: 1=swAddMateError_NoError; some versions also return a nonempty Mate with 0=Unknown.
    if mate is None or int(error_status.value) not in (
        SW_ADD_MATE_ERROR_UNKNOWN,
        SW_ADD_MATE_ERROR_NO_ERROR,
    ):
        raise RuntimeError(
            f"AddMate5 başarısız: type={mate_type}, error_status={error_status.value}"
        )
    if name:
        try:
            mate.Name = name
        except Exception:
            pass
    if clear_selection:
        asm_model.ClearSelection2(True)
    return mate


def add_concentric_mate_by_cylinders(
    asm_model,
    component_a,
    component_b,
    radius_a=None,
    radius_b=None,
    name=None,
    lock_rotation=False,
):
    """
    @brief Create a concentric Mate from two cylindrical faces, retaining rotational freedom by default.
    @param asm_model IAssemblyDoc/IModelDoc2 assembly object.
    @param component_a First component.
    @param component_b Second component.
    @param radius_a First cylinder radius range (min, max), meters; None permits any.
    @param radius_b Second cylinder radius range (min, max), meters; None permits any.
    @param name Optional Mate name.
    @param lock_rotation Lock concentric rotation; keep False for motion assemblies.
    @return Mate2 object.
    """
    radius_a = radius_a or (0.0, None)
    radius_b = radius_b or (0.0, None)
    face_a = find_largest_cylinder_face(component_a, radius_a[0], radius_a[1])
    face_b = find_largest_cylinder_face(component_b, radius_b[0], radius_b[1])
    select_entities_for_mate(asm_model, face_a, face_b, mark=1)
    return add_mate5_checked(
        asm_model,
        SW_MATE_CONCENTRIC,
        lock_rotation=lock_rotation,
        name=name,
    )


def add_gear_mate_by_cylinders(
    asm_model,
    component_a,
    component_b,
    teeth_a,
    teeth_b,
    radius_a=None,
    radius_b=None,
    name=None,
):
    """
    @brief Create an actual Gear Mate from two gear shaft/bore cylindrical faces.
    @param asm_model IAssemblyDoc/IModelDoc2 assembly object.
    @param component_a First gear component.
    @param component_b Second gear component.
    @param teeth_a First gear tooth count or equivalent pitch-circle ratio.
    @param teeth_b Second gear tooth count or equivalent pitch-circle ratio.
    @param radius_a First shaft/bore radius range in meters.
    @param radius_b Second shaft/bore radius range in meters.
    @param name Optional Mate name.
    @return Mate2 object.
    """
    if float(teeth_a) == 0 or float(teeth_b) == 0:
        raise ValueError("Gear Mate diş sayısı veya aktarım oranı sıfır olamaz")
    radius_a = radius_a or (0.0, None)
    radius_b = radius_b or (0.0, None)
    face_a = find_largest_cylinder_face(component_a, radius_a[0], radius_a[1])
    face_b = find_largest_cylinder_face(component_b, radius_b[0], radius_b[1])
    select_entities_for_mate(asm_model, face_a, face_b, mark=1)
    return add_mate5_checked(
        asm_model,
        SW_MATE_GEAR,
        gear_num=float(teeth_a),
        gear_den=float(teeth_b),
        name=name,
    )


def add_revolute_joint_by_cylinders(
    asm_model,
    component_a,
    component_b,
    radius_a=None,
    radius_b=None,
    name=None,
):
    """
    @brief Create the core concentric Mate for a rotating hinge shaft.

    An official Hinge Mate is equivalent to concentric alignment plus axial positioning. Preserve one rotational degree of freedom here, then constrain axial motion with a coincident-plane or distance Mate.
    """
    return add_concentric_mate_by_cylinders(
        asm_model,
        component_a,
        component_b,
        radius_a=radius_a,
        radius_b=radius_b,
        name=name,
        lock_rotation=False,
    )


def build_transform_data_x(tx, ty, tz, angle_rad=0.0):
    """
    @brief Build a SOLIDWORKS MathTransform array for local X-axis rotation and translation.
    @param tx X translation in meters.
    @param ty Y translation in meters.
    @param tz Z translation in meters.
    @param angle_rad X-axis rotation in radians.
    @return A 16-tuple assignable to MathTransform.ArrayData.
    """
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return (
        1.0, 0.0, 0.0,
        0.0, c, -s,
        0.0, s, c,
        tx, ty, tz,
        1.0,
        0.0, 0.0, 0.0,
    )


def apply_component_transform_x(component, tx, ty, tz, angle_rad=0.0):
    """
    @brief Update pose from the existing Transform2 and trigger assembly solving.
    @param component IComponent2 object.
    @param tx X translation in meters.
    @param ty Y translation in meters.
    @param tz Z translation in meters.
    @param angle_rad X-axis rotation in radians.
    @return True if SetTransformAndSolve2 or Transform2 assignment succeeds.
    """
    transform = component.Transform2
    if transform is None:
        raise RuntimeError("Bileşende kullanılabilir Transform2 yok")
    transform.ArrayData = build_transform_data_x(tx, ty, tz, angle_rad)
    try:
        if component.SetTransformAndSolve2(transform):
            return True
    except Exception:
        pass
    try:
        component.Transform2 = transform
        return True
    except Exception:
        return False


def iter_feature_tree(model, include_subfeatures=True):
    """
    @brief Walk the feature tree, supporting FirstFeature/GetNextFeature pseudo-callable properties.
    @param model IModelDoc2 object.
    @param include_subfeatures Include subfeatures when True.
    @return Generator yielding (feature, depth).
    """
    def walk_subfeatures(parent, depth):
        sub = safe_get_com_member(parent, "GetFirstSubFeature")
        while sub:
            yield sub, depth
            if include_subfeatures:
                yield from walk_subfeatures(sub, depth + 1)
            sub = safe_get_com_member(sub, "GetNextSubFeature")

    feature = safe_get_com_member(model, "FirstFeature")
    while feature:
        yield feature, 0
        if include_subfeatures:
            yield from walk_subfeatures(feature, 1)
        feature = safe_get_com_member(feature, "GetNextFeature")


def collect_mate_feature_summary(model):
    """
    @brief Collect summaries of MateGroup and its child Mate features.
    @param model IModelDoc2 assembly object.
    @return List of name, type, and depth values verifying actual mechanical Mates in the feature tree.
    """
    result = []
    for feature, depth in iter_feature_tree(model, include_subfeatures=True):
        name = safe_get_com_member(feature, "Name")
        type_name = safe_get_com_member(feature, "GetTypeName2")
        if (
            type_name == "MateGroup"
            or str(type_name).startswith("Mate")
            or "mate" in str(name).lower()
            or "\u914d\u5408" in str(name)
        ):
            result.append({
                "name": name,
                "type": type_name,
                "depth": depth,
            })
    return result


def add_mate_coincident(asm_model, entity1_name, entity1_type, entity2_name, entity2_type):
    """
    Add a coincident Mate.

    Args:
        entity1_name/entity2_name: Entity names (face, edge, vertex, etc.).
        entity1_type/entity2_type: Type strings such as "FACE", "PLANE", "EDGE", or "VERTEX".
    """
    asm_model.ClearSelection2(True)
    _select_by_id(asm_model.Extension, entity1_name, entity1_type, mark=1)
    _select_by_id(asm_model.Extension, entity2_name, entity2_type, append=True, mark=1)
    return add_mate5_checked(asm_model, SW_MATE_COINCIDENT)


def add_mate_concentric(asm_model, face1_name, face2_name):
    """Add a concentric Mate."""
    asm_model.ClearSelection2(True)
    _select_by_id(asm_model.Extension, face1_name, "FACE", mark=1)
    _select_by_id(asm_model.Extension, face2_name, "FACE", append=True, mark=1)
    return add_mate5_checked(asm_model, SW_MATE_CONCENTRIC, lock_rotation=False)


def add_mate_distance(asm_model, entity1_name, entity1_type, entity2_name, entity2_type, distance):
    """
    Add a distance Mate.

    Args:
        distance: Mate distance in meters.
    """
    asm_model.ClearSelection2(True)
    _select_by_id(asm_model.Extension, entity1_name, entity1_type, mark=1)
    _select_by_id(asm_model.Extension, entity2_name, entity2_type, append=True, mark=1)
    return add_mate5_checked(asm_model, SW_MATE_DISTANCE, distance=distance)


def add_mate_parallel(asm_model, face1_name, face2_name):
    """Add a parallel Mate."""
    asm_model.ClearSelection2(True)
    _select_by_id(asm_model.Extension, face1_name, "FACE", mark=1)
    _select_by_id(asm_model.Extension, face2_name, "FACE", append=True, mark=1)
    return add_mate5_checked(asm_model, SW_MATE_PARALLEL)


def get_components(asm_model, top_level_only=True):
    """
    Get all assembly components.

    Args:
        top_level_only: True for top-level components only; False includes subassemblies.

    Returns:
        List of component information.
    """
    components = safe_get_com_member(asm_model, "GetComponents", top_level_only)
    result = []
    if components:
        for comp in components:
            result.append({
                "name": safe_get_com_member(comp, "Name2"),
                "path": safe_get_com_member(comp, "GetPathName"),
                "suppressed": safe_get_com_member(comp, "IsSuppressed"),
                "visible": safe_get_com_member(comp, "Visible"),
            })
    return result


def find_component_by_name(asm_model, keyword, top_level_only=True, case_sensitive=False):
    """
    @brief Find IComponent2 by a component-name keyword.
    @param asm_model Assembly IModelDoc2/IAssemblyDoc.
    @param keyword Name keyword, such as "impeller" or "rotor".
    @param top_level_only True for top-level components only.
    @param case_sensitive Whether matching is case sensitive.
    @return First matching IComponent2.
    """
    if not keyword:
        raise ValueError("keyword boş olamaz")
    components = safe_get_com_member(asm_model, "GetComponents", top_level_only) or []
    needle = str(keyword) if case_sensitive else str(keyword).lower()
    for component in components:
        name = str(safe_get_com_member(component, "Name2"))
        haystack = name if case_sensitive else name.lower()
        if needle in haystack:
            return component
    raise RuntimeError(f"Bileşen bulunamadı: {keyword}")


def suppress_component(asm_model, component_name):
    """Suppress a component."""
    _select_by_id(asm_model.Extension, component_name, "COMPONENT")
    asm_model.EditSuppress()


def unsuppress_component(asm_model, component_name):
    """Unsuppress a component."""
    _select_by_id(asm_model.Extension, component_name, "COMPONENT")
    asm_model.EditUnsuppress()


def replace_component(asm_model, old_component_name, new_part_path):
    """
    Replace an assembly component.

    Args:
        old_component_name: Existing component name.
        new_part_path: New part file path.
    """
    _select_by_id(asm_model.Extension, old_component_name, "COMPONENT")
    return asm_model.ReplaceComponents2(new_part_path, "", False, 0, True)


def get_interference_detection(asm_model):
    """Run interference detection and return an auditable report."""
    try:
        from .sw_measure import inspect_interference
    except ImportError:
        from sw_measure import inspect_interference
    result = inspect_interference(asm_model)
    # Preserve the legacy SI volume field; share calculation and failure handling.
    for item in result["items"]:
        value = item.get("volume_mm3")
        item["volume"] = value / 1e9 if value is not None else None
    if result["errors"]:
        result["error"] = "; ".join(result["errors"])
    return result
