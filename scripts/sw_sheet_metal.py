"""SOLIDWORKS native sheet-metal creation and evidence readback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .sw_connect import get_com_member
    from .sw_part import _ensure_sketch_selected
except ImportError:
    from sw_connect import get_com_member
    from sw_part import _ensure_sketch_selected


SW_FM_BASE_FLANGE = 34
SW_END_COND_BLIND = 0
SW_BEND_ALLOWANCE_K_FACTOR = 2
SW_SHEET_METAL_RELIEF_RECTANGULAR = 1
SW_SOLID_BODY = 0


@dataclass(frozen=True)
class BaseFlangeSpec:
    """@brief Manufacturable base-flange parameters; all lengths are meters."""

    thickness: float
    bend_radius: float
    depth: float
    k_factor: float = 0.42
    relief_ratio: float = 0.5
    reverse_direction: bool = False
    reverse_thickness: bool = False

    def validate(self) -> None:
        """@brief Reject obviously invalid manufacturing parameters before COM calls."""
        if self.thickness <= 0:
            raise ValueError("Sac levha kalınlığı sıfırdan büyük olmalı")
        if self.bend_radius < 0:
            raise ValueError("Büküm yarıçapı negatif olamaz")
        if self.depth <= 0:
            raise ValueError("Base Flange derinliği sıfırdan büyük olmalı")
        if not 0 < self.k_factor < 1:
            raise ValueError("K faktörü 0 ile 1 arasında olmalı")
        if self.relief_ratio <= 0:
            raise ValueError("Relief oranı sıfırdan büyük olmalı")


def _feature_type(feature: Any) -> str:
    """@brief Read a feature type name safely."""
    try:
        return str(get_com_member(feature, "GetTypeName2") or "")
    except Exception:
        return ""


def iter_features(model):
    """@brief Traverse features in order with pywin32 property/method compatibility."""
    feature = get_com_member(model, "FirstFeature")
    # pywin32 may reuse short-lived wrapper Python IDs for different COM objects;
    # do not deduplicate by id; use a hard limit to guard against feature-chain cycles.
    count = 0
    while feature is not None and count < 4096:
        yield feature
        feature = get_com_member(feature, "GetNextFeature")
        count += 1


def create_base_flange(model, sketch_ref, spec: BaseFlangeSpec):
    """@brief Create a native base flange from an open or closed sketch using the modern FeatureData API.

    Open polylines create profile flanges; closed profiles create flat bases. Return an actual IFeature or raise on failure; never wrap empty results as success.
    """
    spec.validate()
    _ensure_sketch_selected(model, sketch_ref)
    manager = get_com_member(model, "FeatureManager")

    bend_allowance = get_com_member(manager, "CreateCustomBendAllowance")
    if bend_allowance is None:
        raise RuntimeError("CreateCustomBendAllowance nesne döndürmedi")
    bend_allowance.Type = SW_BEND_ALLOWANCE_K_FACTOR
    bend_allowance.KFactor = float(spec.k_factor)

    data = get_com_member(manager, "CreateDefinition", SW_FM_BASE_FLANGE)
    if data is None:
        raise RuntimeError("CreateDefinition(swFmBaseFlange) FeatureData döndürmedi")

    data.Initialize(
        False,
        True,
        bend_allowance,
        True,
        SW_SHEET_METAL_RELIEF_RECTANGULAR,
        True,
        float(spec.relief_ratio),
        0.0,
        0.0,
    )
    data.D1EndConditionType = SW_END_COND_BLIND
    data.D1EndConditionDistance = float(spec.depth)
    data.D2EndConditionType = SW_END_COND_BLIND
    data.D2EndConditionDistance = 0.0
    data.OverrideDefaultSheetMetalParameters = True
    data.Thickness = float(spec.thickness)
    data.BendRadius = float(spec.bend_radius)
    data.ReverseDirection = bool(spec.reverse_direction)
    data.ReverseThickness = bool(spec.reverse_thickness)

    feature = get_com_member(manager, "CreateFeature", data)
    if feature is None:
        raise RuntimeError("CreateFeature(IBaseFlangeFeatureData) başarısız")
    # GetErrorCode2 also has a by-ref isWarning argument; only hard errors need rejection here.
    # Unambiguous GetErrorCode supports both static and dynamic pywin32 proxies.
    error_code = int(get_com_member(feature, "GetErrorCode") or 0)
    if error_code:
        raise RuntimeError(f"Base Flange özellik hata kodu: {error_code}")
    return feature


def sheet_metal_evidence(model) -> dict[str, Any]:
    """@brief Read native features, bodies, and key sheet-metal parameters as auditable evidence."""
    feature_rows = []
    base_parameters = []
    for feature in iter_features(model):
        type_name = _feature_type(feature)
        name = str(get_com_member(feature, "Name") or "")
        feature_rows.append({"name": name, "type": type_name})
        if type_name in {"BaseFlange", "SMBaseFlange", "Base-Flange"}:
            definition = get_com_member(feature, "GetDefinition")
            if definition is not None:
                base_parameters.append({
                    "name": name,
                    "thickness_m": float(get_com_member(definition, "Thickness") or 0.0),
                    "bend_radius_m": float(get_com_member(definition, "BendRadius") or 0.0),
                    "depth_m": float(get_com_member(definition, "D1EndConditionDistance") or 0.0),
                    "k_factor": float(get_com_member(definition, "KFactor") or 0.0),
                })

    bodies = tuple(get_com_member(model, "GetBodies2", SW_SOLID_BODY, False) or ())
    body_rows = []
    for body in bodies:
        is_sheet_metal = False
        try:
            is_sheet_metal = bool(get_com_member(body, "IsSheetMetal"))
        except Exception:
            pass
        body_rows.append({
            "name": str(get_com_member(body, "Name") or ""),
            "is_sheet_metal": is_sheet_metal,
        })

    type_names = [row["type"] for row in feature_rows]
    return {
        "features": feature_rows,
        "feature_types": type_names,
        "base_flange_parameters": base_parameters,
        "bodies": body_rows,
        "has_sheet_metal_feature": any("SheetMetal" in item for item in type_names),
        "has_base_flange": bool(base_parameters),
        "all_solid_bodies_are_sheet_metal": bool(body_rows) and all(
            row["is_sheet_metal"] for row in body_rows
        ),
    }
