"""SOLIDWORKS dimension and custom-property operations.

Wrap only interfaces checked against SOLIDWORKS 2024 Interop and official API Help: IDimension.SetSystemValue3 and ICustomPropertyManager.Add3/Get6.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

try:
    from .sw_connect import get_com_member, save_document
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member, save_document
    from sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()

PROPERTY_TYPES = {
    "number": 3,
    "double": 5,
    "yes_no": 11,
    "text": 30,
    "date": 64,
}
SET_VALUE_MODES = {
    "current": 1,
    "all": 2,
    "specific": 3,
}
SET_VALUE_STATUS = {
    0: "successful",
    1: "failure",
    2: "invalid_value",
    3: "driven_dimension",
    4: "model_not_loaded",
    5: "frozen_feature_owner",
}


def _configuration_names(model) -> list[str]:
    """Return document configuration names, supporting COM tuple/list/None results."""
    names = get_com_member(model, "GetConfigurationNames")
    return [str(name) for name in (names or [])]


def _resolve_configuration_name(names: Sequence[str], requested: str) -> str | None:
    """@brief Return the actual configuration name using SOLIDWORKS case-insensitive matching."""
    matches = [str(name) for name in names if str(name).casefold() == requested.casefold()]
    if len(matches) > 1:
        raise RuntimeError(f"Konfigürasyon adı büyük/küçük harf eşleşmesi tekil değil: {requested}")
    return matches[0] if matches else None


def _active_configuration_name(model) -> str:
    """@brief Return the active configuration name, or an empty string when unavailable."""
    try:
        manager = get_com_member(model, "ConfigurationManager")
        active = get_com_member(manager, "ActiveConfiguration")
        return str(get_com_member(active, "Name") or "")
    except Exception:
        return ""


def inspect_configurations(model) -> dict[str, Any]:
    """@brief Read the configuration-family inventory and current configuration; changes still require manual review."""
    names = _configuration_names(model)
    current = _active_configuration_name(model)
    return {
        "status": "pilot" if names else "blocked",
        "configurations": names,
        "active_configuration": current,
        "review_required": True,
        "limitations": ["Design table oluşturma/düzenleme veya büyük konfigürasyon ailesi toplu değişikliği yapılmadı", "Konfigürasyonlar arasındaki ölçü, özellik, suppression ve geometri farkları elle incelenmeli"],
    }


def activate_configuration(
    model,
    configuration_name: str,
    *,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """@brief Activate an existing configuration and verify by reading its active name."""
    requested_name = str(configuration_name).strip()
    if not requested_name:
        raise ValueError("configuration_name boş olamaz")
    names = _configuration_names(model)
    name = _resolve_configuration_name(names, requested_name)
    if name is None:
        raise LookupError(f"Konfigürasyon bulunamadı: {requested_name}")

    before = _active_configuration_name(model)
    api_called = before != name
    api_return = bool(get_com_member(model, "ShowConfiguration2", name)) if api_called else None
    after = _active_configuration_name(model)
    readback_verified = after == name
    api_success = readback_verified
    rebuild_success = bool(get_com_member(model, "EditRebuild3")) if rebuild and readback_verified else readback_verified
    save_success = bool(save_document(model)) if save and readback_verified and rebuild_success else not save
    success = readback_verified and rebuild_success and save_success
    return {
        "success": success,
        "configuration": name,
        "requested_configuration": requested_name,
        "before": before,
        "after": after,
        "api_called": api_called,
        "api_return": api_return,
        "api_success": api_success,
        "readback_verified": readback_verified,
        "rebuild_success": rebuild_success,
        "save_requested": save,
        "save_success": save_success,
        "review_required": True,
    }


def create_configuration(
    model,
    configuration_name: str,
    *,
    comment: str = "",
    alternate_name: str = "",
    options: int = 0,
    if_exists: str = "reuse",
    activate: bool = True,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """@brief Create a configuration using AddConfiguration3 and verify inventory and active-name readback.

    options is the official swConfigurationOptions2_e bitmask. Default 0 preserves SOLIDWORKS behavior; callers must explicitly select nonzero values from the target-version enum.
    """
    requested_name = str(configuration_name).strip()
    if not requested_name:
        raise ValueError("configuration_name boş olamaz")
    if if_exists not in {"reuse", "error"}:
        raise ValueError("if_exists yalnızca reuse veya error destekler")
    if int(options) < 0:
        raise ValueError("options negatif olamaz")

    before_names = _configuration_names(model)
    existing_name = _resolve_configuration_name(before_names, requested_name)
    existed = existing_name is not None
    name = existing_name or requested_name
    if existed and if_exists == "error":
        raise FileExistsError(f"Konfigürasyon zaten var: {name}")

    created = None if existed else get_com_member(
        model,
        "AddConfiguration3",
        name,
        str(comment),
        str(alternate_name),
        int(options),
    )
    if not existed and created is None:
        raise RuntimeError(f"AddConfiguration3 konfigürasyon nesnesi döndürmedi: {name}")

    after_names = _configuration_names(model)
    listed_name = _resolve_configuration_name(after_names, name)
    listed = listed_name is not None
    name = listed_name or name
    activation = (
        activate_configuration(model, name, rebuild=rebuild, save=False)
        if activate and listed
        else None
    )
    if activation:
        rebuild_success = bool(activation["rebuild_success"])
    elif rebuild and listed:
        rebuild_success = bool(get_com_member(model, "EditRebuild3"))
    else:
        rebuild_success = listed
    active_verified = activation["readback_verified"] if activation else True
    save_success = bool(save_document(model)) if save and listed and rebuild_success and active_verified else not save
    success = listed and rebuild_success and active_verified and save_success
    return {
        "success": success,
        "configuration": name,
        "requested_configuration": requested_name,
        "created": not existed,
        "reused": existed,
        "listed_after_create": listed,
        "configurations_before": before_names,
        "configurations_after": after_names,
        "options": int(options),
        "activation": activation,
        "save_requested": save,
        "save_success": save_success,
        "review_required": True,
    }


def _dimension_value_mm(dimension, configuration_name: str | None = None) -> float:
    """Read a dimension system value and convert it to millimeters."""
    if configuration_name:
        return float(dimension.GetSystemValue2(configuration_name)) * 1000.0
    return float(get_com_member(dimension, "SystemValue")) * 1000.0


def update_dimension_mm(
    model,
    dimension_name: str,
    value_mm: float,
    *,
    configuration_mode: str = "current",
    configuration_names: Sequence[str] | None = None,
    rebuild: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """Update a named dimension and return auditable evidence.

    configuration_mode supports current, all, and specific; specific requires configuration names. SOLIDWORKS internal API lengths are meters.
    """
    if not dimension_name.strip():
        raise ValueError("dimension_name boş olamaz")
    if value_mm <= 0:
        raise ValueError("value_mm sıfırdan büyük olmalı")
    if configuration_mode not in SET_VALUE_MODES:
        raise ValueError(f"Desteklenmeyen konfigürasyon kapsamı: {configuration_mode}")

    dimension = model.Parameter(dimension_name)
    if dimension is None:
        raise LookupError(f"Ölçü bulunamadı: {dimension_name}")

    requested_names = [str(name).strip() for name in (configuration_names or []) if str(name).strip()]
    if configuration_mode == "specific" and not requested_names:
        raise ValueError("specific modu configuration_names gerektirir")
    if configuration_mode == "all":
        evidence_names = _configuration_names(model)
    elif configuration_mode == "specific":
        evidence_names = requested_names
    else:
        evidence_names = []

    before = (
        {name: _dimension_value_mm(dimension, name) for name in evidence_names}
        if evidence_names
        else {"current": _dimension_value_mm(dimension)}
    )
    names_variant = (
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, requested_names)
        if configuration_mode == "specific"
        else None
    )
    status_code = int(
        dimension.SetSystemValue3(
            float(value_mm) / 1000.0,
            SET_VALUE_MODES[configuration_mode],
            names_variant,
        )
    )
    rebuild_success = (
        bool(get_com_member(model, "EditRebuild3"))
        if rebuild and status_code == 0
        else status_code == 0
    )
    after = (
        {name: _dimension_value_mm(dimension, name) for name in evidence_names}
        if evidence_names
        else {"current": _dimension_value_mm(dimension)}
    )
    save_success = bool(save_document(model)) if save and status_code == 0 and rebuild_success else not save
    success = status_code == 0 and rebuild_success and save_success
    return {
        "success": success,
        "dimension": dimension_name,
        "configuration_mode": configuration_mode,
        "configuration_names": requested_names,
        "requested_mm": float(value_mm),
        "before_mm": before,
        "after_mm": after,
        "set_status": status_code,
        "set_status_label": SET_VALUE_STATUS.get(status_code, f"unknown_{status_code}"),
        "rebuild_success": rebuild_success,
        "save_requested": save,
        "save_success": save_success,
    }


def _property_manager(model, configuration_name: str = ""):
    manager = model.Extension.CustomPropertyManager(configuration_name)
    if manager is None:
        scope = configuration_name or "Dosya düzeyi"
        raise RuntimeError(f"Alınamadı: {scope} custom property manager")
    return manager


def read_custom_property(model, name: str, *, configuration_name: str = "") -> dict[str, Any]:
    """Read a file-level or configuration-level custom property."""
    manager = _property_manager(model, configuration_name)
    raw_value = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    resolved_value = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")
    was_resolved = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    is_linked = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
    status = int(manager.Get6(name, False, raw_value, resolved_value, was_resolved, is_linked))
    return {
        "name": name,
        "configuration": configuration_name,
        "status": status,
        "exists": status != 1,
        "raw": str(raw_value.value or ""),
        "resolved": str(resolved_value.value or ""),
        "was_resolved": bool(was_resolved.value),
        "is_linked": bool(is_linked.value),
    }


def set_custom_properties(
    model,
    properties: Mapping[str, Any],
    *,
    configuration_name: str = "",
    property_type: str = "text",
    save: bool = False,
) -> dict[str, Any]:
    """Write file-level or configuration-level properties and verify each by readback."""
    if not properties:
        raise ValueError("properties boş olamaz")
    if property_type not in PROPERTY_TYPES:
        raise ValueError(f"Desteklenmeyen özellik türü: {property_type}")
    manager = _property_manager(model, configuration_name)
    results = []
    for raw_name, raw_value in properties.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("Özellik adı boş olamaz")
        value = str(raw_value)
        add_status = int(manager.Add3(name, PROPERTY_TYPES[property_type], value, 2))
        readback = read_custom_property(model, name, configuration_name=configuration_name)
        verified = add_status == 0 and readback["exists"] and readback["raw"] == value
        results.append({
            "name": name,
            "requested": value,
            "add_status": add_status,
            "verified": verified,
            "readback": readback,
        })
    save_success = bool(save_document(model)) if save and all(item["verified"] for item in results) else not save
    return {
        "success": all(item["verified"] for item in results) and save_success,
        "configuration": configuration_name,
        "property_type": property_type,
        "properties": results,
        "save_requested": save,
        "save_success": save_success,
    }
