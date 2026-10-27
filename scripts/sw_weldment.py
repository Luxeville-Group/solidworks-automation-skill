"""SOLIDWORKS native weldment structural members and cut-list wrappers."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

try:
    from .sw_connect import get_com_member, save_document
    from .sw_document_data import set_custom_properties
    from .sw_part import _ensure_sketch_selected
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member, save_document
    from sw_document_data import set_custom_properties
    from sw_part import _ensure_sketch_selected
    from sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()

SW_CONNECTED_SEGMENTS_SIMPLE_CUT = 1
SW_END_CONDITION_MITER = 1
SW_SOLID_BODY = 0
# Escaped legacy CAD property names preserve existing document lookup semantics.
CORE_CUT_LIST_PROPERTY_NAMES = {
    "length",
    "\u957f\u5ea6",
    "angle1",
    "\u89d2\u5ea61",
    "angle2",
    "\u89d2\u5ea62",
    "angle direction",
    "\u89d2\u5ea6\u65b9\u5411",
    "angle rotation",
    "\u89d2\u5ea6\u65cb\u8f6c",
    "description",
    "\u8bf4\u660e",
    "material",
    "\u6750\u6599",
    "weight",
    "\u8d28\u91cf",
    "\u5355\u91cd",
    "quantity",
    "\u6570\u91cf",
    "total length",
    "\u603b\u957f\u5ea6",
    "unit_of_measure",
    "\u8ba1\u91cf\u5355\u4f4d",
    "profile_designation",
    "material_spec",
    "source_repository",
    "source_sku",
    "uzunluk", "açı1", "açı2", "açı yönü", "açı dönüşü",
    "açıklama", "malzeme", "kütle", "birim ağırlık", "adet", "toplam uzunluk", "ölçü birimi",
}


def _as_tuple(value) -> tuple:
    """@brief Normalize a COM object, SAFEARRAY, or empty value to a tuple."""
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(item for item in value if item is not None)
    return (value,)


def _active_configuration_name(model) -> str:
    """@brief Read the active configuration for configurable custom-profile calls."""
    manager = get_com_member(model, "ConfigurationManager")
    configuration = get_com_member(manager, "ActiveConfiguration")
    return str(get_com_member(configuration, "Name") or "")


def create_weldment_profile(
    model,
    sketch_ref,
    output_path: str | Path,
    *,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """@brief Save the selected profile sketch as an actual .sldlfp weldment profile."""
    target = Path(output_path).expanduser().resolve()
    if target.suffix.casefold() != ".sldlfp":
        raise ValueError("Weldment profil çıktısı .sldlfp uzantısı kullanmalı")
    target.parent.mkdir(parents=True, exist_ok=True)
    _ensure_sketch_selected(model, sketch_ref)
    configuration_name = _active_configuration_name(model)
    if properties:
        set_custom_properties(
            model,
            properties,
            configuration_name=configuration_name,
            save=False,
        )
        _ensure_sketch_selected(model, sketch_ref)
    if not save_document(model, str(target)):
        raise RuntimeError("Özel Weldment profili kaydedilemedi")
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("SOLIDWORKS başarı bildirdi ancak .sldlfp dosyası oluşmadı")
    return {
        "path": str(target),
        "configuration_name": configuration_name,
        "size_bytes": target.stat().st_size,
        "properties": dict(properties or {}),
    }


def create_structural_member(
    model,
    profile_path: str | Path,
    segment_groups: Iterable[Iterable[Any]],
    *,
    configuration_name: str = "",
    apply_corner_treatment: bool = True,
    corner_treatment_type: int = SW_END_CONDITION_MITER,
    connected_segments_option: int = SW_CONNECTED_SEGMENTS_SIMPLE_CUT,
    allow_protrusion: bool = False,
):
    """@brief Create native structural members using InsertStructuralWeldment5."""
    profile = Path(profile_path).expanduser().resolve()
    if not profile.is_file() or profile.suffix.casefold() != ".sldlfp":
        raise FileNotFoundError(f"Weldment profili yok veya biçimi yanlış: {profile}")
    manager = get_com_member(model, "FeatureManager")
    existing_types = {
        str(get_com_member(feature, "GetTypeName2") or "")
        for feature in _iter_feature_chain(get_com_member(model, "FirstFeature"), "GetNextFeature")
    }
    if "WeldmentFeature" not in existing_types:
        model.ClearSelection2(True)
        weldment_feature = get_com_member(manager, "InsertWeldmentFeature")
        if weldment_feature is None:
            raise RuntimeError("InsertWeldmentFeature başarısız")
    groups = []
    for index, raw_segments in enumerate(segment_groups, start=1):
        segments = tuple(item for item in raw_segments if item is not None)
        if not segments:
            raise ValueError(f"Structural Member grup {index} yol segmenti içermiyor")
        group = get_com_member(manager, "CreateStructuralMemberGroup")
        if group is None:
            raise RuntimeError("CreateStructuralMemberGroup nesne döndürmedi")
        group.Segments = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, segments)
        group.ApplyCornerTreatment = bool(apply_corner_treatment)
        if apply_corner_treatment:
            group.CornerTreatmentType = int(corner_treatment_type)
            # Keep each path segment as a separate cut body so the cut list groups correctly by length.
            group.MiterMergeCondition = False
        groups.append(group)

    # pywin32 marshals Python tuples as VARIANT SAFEARRAY; avoid ambiguous preselection sets.
    feature = get_com_member(
        manager,
        "InsertStructuralWeldment5",
        str(profile),
        int(connected_segments_option),
        bool(allow_protrusion),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tuple(groups)),
        str(configuration_name),
    )
    if feature is None:
        raise RuntimeError("InsertStructuralWeldment5 başarısız")
    model.ClearSelection2(True)
    if not bool(get_com_member(model, "EditRebuild3")):
        raise RuntimeError("Structural Member oluşturulduktan sonra model Rebuild başarısız")
    return feature


def _body_length_key(body) -> int:
    """@brief Build a micrometer-resolution grouping key from the longest bounding-box side."""
    box = tuple(float(item) for item in (get_com_member(body, "GetBodyBox") or ()))
    if len(box) != 6:
        raise RuntimeError("Structural Member gövdesi 6 değerli bounding box döndürmedi")
    spans = (abs(box[3] - box[0]), abs(box[4] - box[1]), abs(box[5] - box[2]))
    return int(round(max(spans) * 1_000_000.0))


def _body_cut_list_key(body) -> tuple[int, int, int]:
    """@brief Build a rotation-invariant three-axis micrometer bounding-box key to avoid merging different same-length profiles."""
    box = tuple(float(item) for item in (get_com_member(body, "GetBodyBox") or ()))
    if len(box) != 6:
        raise RuntimeError("Structural Member gövdesi 6 değerli bounding box döndürmedi")
    spans = sorted((abs(box[3] - box[0]), abs(box[4] - box[1]), abs(box[5] - box[2])))
    return tuple(int(round(item * 1_000_000.0)) for item in spans)


def ensure_cut_list(model) -> list[Any]:
    """@brief Create native CutListFolder entries by body length for a weldment without a list.

    Each InsertWeldmentCutList2 call accepts bodies belonging to the same cut item. Group by longest bounding-box side so equal-length rectangular-frame beams/posts form quantity-two entries without merging different lengths.
    """
    existing_by_name = {}
    for feature in iter_features_recursive(model):
        if str(get_com_member(feature, "GetTypeName2") or "") == "CutListFolder":
            existing_by_name.setdefault(str(get_com_member(feature, "Name") or ""), feature)
    existing = list(existing_by_name.values())
    if existing:
        return existing
    bodies = _as_tuple(get_com_member(model, "GetBodies2", SW_SOLID_BODY, False))
    if not bodies:
        raise RuntimeError("Cut List içine yazılabilecek Structural Member gövdesi yok")
    grouped: dict[tuple[int, int, int], list[Any]] = {}
    for body in bodies:
        grouped.setdefault(_body_cut_list_key(body), []).append(body)
    manager = get_com_member(model, "FeatureManager")
    created = []
    for length_key in sorted(grouped):
        body_array = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH,
            tuple(grouped[length_key]),
        )
        method = getattr(manager, "InsertWeldmentCutList2", None)
        if callable(method):
            feature = method(body_array)
        else:
            ole_object = getattr(manager, "_oleobj_", None)
            if ole_object is None:
                raise RuntimeError("FeatureManager InsertWeldmentCutList2 desteklemiyor")
            # SW2026 IDispatch also exposes DISPID 174 as a pseudo-property valued None;
            # call directly with the official DISPATCH_METHOD semantics instead of treating None as a function.
            feature = ole_object.Invoke(
                174,
                0,
                pythoncom.DISPATCH_METHOD,
                True,
                body_array,
            )
        if feature is None:
            raise RuntimeError(f"InsertWeldmentCutList2 başarısız: length_key={length_key}")
        created.append(feature)
    if not bool(get_com_member(model, "EditRebuild3")):
        raise RuntimeError("Cut List oluşturulduktan sonra model Rebuild başarısız")
    return created


def _iter_feature_chain(first_feature, next_member: str):
    """@brief Traverse a top-level or sibling subfeature chain."""
    feature = first_feature
    count = 0
    while feature is not None and count < 4096:
        yield feature
        feature = get_com_member(feature, next_member)
        count += 1


def iter_features_recursive(model):
    """@brief Recursively traverse weldment folder children such as CutListFolder."""
    def walk(feature):
        yield feature
        try:
            first_child = get_com_member(feature, "GetFirstSubFeature")
        except Exception:
            first_child = None
        for child in _iter_feature_chain(first_child, "GetNextSubFeature"):
            yield from walk(child)

    for root in _iter_feature_chain(get_com_member(model, "FirstFeature"), "GetNextFeature"):
        yield from walk(root)


def _read_property(manager, name: str) -> dict[str, Any]:
    """@brief Read cut-list properties using Get6 and preserve raw/resolved values."""
    raw = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    resolved = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    was_resolved = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    linked = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    status = int(manager.Get6(name, False, raw, resolved, was_resolved, linked))
    return {
        "name": str(name),
        "status": status,
        "raw": str(raw.value or ""),
        "resolved": str(resolved.value or ""),
        "was_resolved": bool(was_resolved.value),
        "linked": bool(linked.value),
    }


def read_property_manager(manager, *, core_only: bool = True) -> dict[str, dict[str, Any]]:
    """@brief Enumerate manufacturing properties, excluding template title-block noise by default."""
    names = _as_tuple(get_com_member(manager, "GetNames"))
    if core_only:
        names = tuple(
            name for name in names if str(name).strip().casefold() in CORE_CUT_LIST_PROPERTY_NAMES
        )
    return {str(name): _read_property(manager, str(name)) for name in names}


def set_cut_list_properties(model, properties: dict[str, Any]) -> list[dict[str, Any]]:
    """@brief Write profile source and material specification to each native cut-list item and read back."""
    if not properties:
        raise ValueError("Cut List özellikleri boş olamaz")
    ensure_cut_list(model)
    results = []
    seen_names = set()
    for feature in iter_features_recursive(model):
        if str(get_com_member(feature, "GetTypeName2") or "") != "CutListFolder":
            continue
        feature_name = str(get_com_member(feature, "Name") or "")
        if feature_name in seen_names:
            continue
        seen_names.add(feature_name)
        manager = get_com_member(feature, "CustomPropertyManager")
        item = {"name": feature_name, "properties": {}}
        for raw_name, raw_value in properties.items():
            name = str(raw_name).strip()
            if not name:
                raise ValueError("Cut List özellik adı boş olamaz")
            value = str(raw_value)
            add_status = int(manager.Add3(name, 30, value, 2))
            readback = _read_property(manager, name)
            verified = readback["raw"] == value or readback["resolved"] == value
            if not verified:
                raise RuntimeError(f"Cut List özellik readback başarısız: {item['name']} / {name}")
            item["properties"][name] = {"add_status": add_status, **readback}
        results.append(item)
    return results


def update_cut_list(model) -> list[dict[str, Any]]:
    """@brief Update all native CutListFolder entries and return folder-level geometry evidence."""
    folders = []
    seen_names = set()
    for feature in iter_features_recursive(model):
        type_name = str(get_com_member(feature, "GetTypeName2") or "")
        if type_name != "CutListFolder":
            continue
        feature_name = str(get_com_member(feature, "Name") or "")
        if feature_name in seen_names:
            continue
        seen_names.add(feature_name)
        body_folder = get_com_member(feature, "GetSpecificFeature2")
        update_ok = bool(get_com_member(body_folder, "UpdateCutList")) if body_folder else False
        manager = get_com_member(feature, "CustomPropertyManager")
        folders.append({
            "name": feature_name,
            "type": type_name,
            "body_count": int(get_com_member(body_folder, "GetBodyCount") or 0) if body_folder else 0,
            "update_ok": update_ok,
            "properties": read_property_manager(manager) if manager else {},
        })
    return folders


def weldment_evidence(model, *, create_missing_cut_list: bool = False) -> dict[str, Any]:
    """@brief Read structural members, body count, and SW2024+ configuration cut-list items."""
    if create_missing_cut_list:
        ensure_cut_list(model)
    folders = update_cut_list(model)
    features = []
    seen_features = set()
    for feature in iter_features_recursive(model):
        row = {
            "name": str(get_com_member(feature, "Name") or ""),
            "type": str(get_com_member(feature, "GetTypeName2") or ""),
        }
        key = (row["name"], row["type"])
        if key not in seen_features:
            seen_features.add(key)
            features.append(row)
    configuration = get_com_member(get_com_member(model, "ConfigurationManager"), "ActiveConfiguration")
    cut_list_items = []
    try:
        items = _as_tuple(get_com_member(configuration, "GetCutListItems"))
    except Exception:
        items = ()
    for index, item in enumerate(items, start=1):
        manager = get_com_member(item, "CustomPropertyManager")
        cut_list_items.append({
            "index": index,
            "properties": read_property_manager(manager) if manager else {},
        })

    bodies = _as_tuple(get_com_member(model, "GetBodies2", SW_SOLID_BODY, False))
    feature_types = [item["type"] for item in features]
    return {
        "configuration": str(get_com_member(configuration, "Name") or ""),
        "features": features,
        "feature_types": feature_types,
        "solid_body_count": len(bodies),
        "cut_list_folders": folders,
        "cut_list_items": cut_list_items,
        "has_weldment_feature": "WeldmentFeature" in feature_types,
        "has_structural_member": any(item in {"StructuralMember", "WeldMemberFeat"} for item in feature_types),
    }


def export_cut_list_csv(evidence: dict[str, Any], output_path: str | Path) -> Path:
    """@brief Export complete cut-list properties as UTF-8-SIG CSV."""
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = evidence.get("cut_list_folders") or evidence.get("cut_list_items") or []
    property_names = sorted({name for row in rows for name in row.get("properties", {})})
    columns = ["index", "name", "body_count", *property_names]
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            values = {
                "index": row.get("index", index),
                "name": row.get("name", ""),
                "body_count": row.get("body_count", ""),
            }
            for name, payload in row.get("properties", {}).items():
                values[name] = payload.get("resolved") or payload.get("raw") or ""
            writer.writerow(values)
    return target
