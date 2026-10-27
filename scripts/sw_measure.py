"""
SOLIDWORKS measurement and self-check utilities.

Three common evidence categories for mechanical design:
1. Mass properties (mass, volume, area, center of mass, moments of inertia).
2. Bounding boxes with axial dimensions for enclosure/tray fit checks.
3. Assembly interference detection with auditable results.

Functions return structured dictionaries rather than raw exceptions so MCP can provide failure reasons and next steps. Connection errors still propagate for centralized MCP handling.
"""
from __future__ import annotations

import math

try:
    from .sw_connect import get_com_member
except ImportError:
    from sw_connect import get_com_member


# swMassPropertyStatus_e
_MASS_STATUS_LABELS = {
    0: "not_calculated",
    1: "calculated",
    2: "failed",
}

# Unit conversion: SOLIDWORKS mass properties use SI (kg, m, m^2, m^3, kg*m^2).
_MM_PER_M = 1000.0
_KG_TO_G = 1000.0


def _safe_member(obj, name, *args, default=None):
    """@brief Read COM members safely; return a default on failure."""
    try:
        member = getattr(obj, name)
        value = member(*args) if args or callable(member) else member
    except Exception:
        return default
    return default if value is None else value


def _round(value, digits=6):
    """@brief Round numeric values safely; preserve None."""
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# swUserPreferenceDoubleValue_e.swMaterialPropertyDensity
SW_MATERIAL_DENSITY_PREF = 7

_DEFAULT_DENSITY_KG_M3 = 1000.0


def collect_mass_properties(model, density_kg_m3=None):
    """
    Read part or assembly mass properties.

    Args:
        model: IModelDoc2.
        density_kg_m3: Optional material density (kg/m³). None uses the document density. Documents without assigned material use the SOLIDWORKS default of 1000 kg/m³, so results cannot directly support engineering decisions.

    Returns:
        dict including mass_g, volume_mm3, surface_area_mm2, and center_of_mass_mm.

    Use IModelDocExtension.CreateMassProperty, the recommended Automation interface; IGetMassProperties supports only in-process unmanaged C++. Set density with the swMaterialPropertyDensity (7) preference. IMassProperty.Density is read-only and SetOverrideMass is not a valid member; both failed upstream machine checks.

    Setting the density preference changes the current document. For temporary estimates, restore the previous value after the call using previous_density_kg_m3 from the result.
    """
    result = {
        "units": {"mass": "g", "length": "mm", "volume": "mm3", "area": "mm2", "inertia": "kg*mm2"},
        "mass_g": None,
        "volume_mm3": None,
        "surface_area_mm2": None,
        "center_of_mass_mm": None,
        "moment_of_inertia_kg_mm2": None,
        "density_kg_m3": density_kg_m3,
        "material": None,
        "material_assigned": None,
        "errors": [],
    }

    material = _safe_member(model, "MaterialIdName")
    result["material"] = material
    result["material_assigned"] = bool(material)
    if not material:
        # Engineering caution, not execution failure: mass can be calculated, but density is only a default.
        result["warnings"] = [
            "Belgeye malzeme atanmamış; SOLIDWORKS varsayılan yoğunluğu (1000 kg/m³) kullanıyor; "
            "Kütle sonucu doğrudan mühendislik kararı için kullanılamaz; malzeme atayın veya density_kg_m3 belirtin."
        ]

    try:
        extension = get_com_member(model, "Extension")
        mass_property = get_com_member(extension, "CreateMassProperty")
    except Exception as exc:
        result["errors"].append(f"Mass Property nesnesi oluşturulamadı: {exc}")
        return result

    if mass_property is None:
        result["errors"].append("CreateMassProperty boş nesne döndü")
        return result

    if density_kg_m3 is not None:
        try:
            previous = _safe_member(model, "GetUserPreferenceDoubleValue", SW_MATERIAL_DENSITY_PREF)
            result["previous_density_kg_m3"] = previous
            model.SetUserPreferenceDoubleValue(SW_MATERIAL_DENSITY_PREF, float(density_kg_m3))
            result["density_overridden"] = True
        except Exception as exc:
            result["density_overridden"] = False
            result["errors"].append(f"Yoğunluk ayarlanamadı; belgenin mevcut yoğunluğu kullanılacak: {exc}")

    def read(name, *args):
        """@brief Read one mass-property member and record failures."""
        try:
            member = getattr(mass_property, name)
            return member(*args) if args or callable(member) else member
        except Exception as exc:
            result["errors"].append(f"{name} okunamadı: {exc}")
            return None

    # IMassProperty.Status is unavailable in some versions (observed with SW2024 SP5). It is diagnostic only;
    # do not add its absence to errors, otherwise every measurement gains a meaningless warning.
    status = None
    try:
        member = getattr(mass_property, "Status")
        status = member() if callable(member) else member
    except Exception:
        pass
    result["status"] = _MASS_STATUS_LABELS.get(status, status)

    mass_kg = read("Mass")
    if mass_kg is not None:
        result["mass_g"] = _round(float(mass_kg) * _KG_TO_G, 6)

    volume_m3 = read("Volume")
    if volume_m3 is not None:
        result["volume_mm3"] = _round(float(volume_m3) * (_MM_PER_M**3), 6)

    area_m2 = read("SurfaceArea")
    if area_m2 is not None:
        result["surface_area_mm2"] = _round(float(area_m2) * (_MM_PER_M**2), 6)

    # Infer density from mass/volume as an independent check of the density actually used;
    # a substantial mismatch with density_kg_m3 means the density setting did not take effect.
    implied_density = None
    if mass_kg not in (None, 0) and volume_m3 not in (None, 0):
        implied_density = _round(float(mass_kg) / float(volume_m3), 6)
    result["density_kg_m3"] = _round(float(density_kg_m3), 6) if density_kg_m3 is not None else implied_density
    result["implied_density_kg_m3"] = implied_density
    if density_kg_m3 is not None and implied_density is not None:
        if abs(implied_density - float(density_kg_m3)) > max(1.0, float(density_kg_m3) * 0.01):
            result["errors"].append(
                f"Yoğunluk ayarı uygulanmamış olabilir: istenen {density_kg_m3} kg/m³, "
                f"; kütle/hacim ile hesaplanan {implied_density} kg/m³."
            )

    # CenterOfMass is a method in makepy strongly typed proxies and a property in dynamic proxies;
    # get_com_member already handles the difference; do not access the property directly.
    try:
        center = list(get_com_member(mass_property, "CenterOfMass") or [])
    except Exception as exc:
        result["errors"].append(f"CenterOfMass okunamadı: {exc}")
        center = []
    if len(center) >= 3:
        result["center_of_mass_mm"] = [_round(value * _MM_PER_M, 6) for value in center[:3]]

    try:
        inertia = list(get_com_member(mass_property, "GetMomentOfInertia", 0) or [])
    except Exception as exc:
        result["errors"].append(f"GetMomentOfInertia okunamadı: {exc}")
        inertia = []
    if len(inertia) >= 9:
        # Return a symmetric 3x3 tensor; convert kg*m^2 to kg*mm^2.
        result["moment_of_inertia_kg_mm2"] = [
            [_round(inertia[row * 3 + column] * (_MM_PER_M**2), 6) for column in range(3)]
            for row in range(3)
        ]

    return result


def collect_bounding_box(model):
    """
    Read a part bounding box.

    Args:
        model: Part IModelDoc2.

    Returns:
        dict with min_corner_mm, max_corner_mm, size_mm, and diagonal_mm.

    GetPartBox(True) returns model-coordinate [xmin,ymin,zmin,xmax,ymax,zmax]. Assemblies use GetBox with a different signature; select the appropriate API automatically.
    """
    result = {
        "units": "mm",
        "min_corner_mm": None,
        "max_corner_mm": None,
        "size_mm": None,
        "diagonal_mm": None,
        "errors": [],
    }

    box = None
    try:
        member = getattr(model, "GetPartBox")
        box = member(True)
    except Exception:
        try:
            box = model.GetBox(0)
        except Exception as exc:
            result["errors"].append(f"Bounding box okunamadı: {exc}")
            return result

    values = list(box or [])
    if len(values) < 6:
        result["errors"].append("Bounding box 6 koordinat değeri döndürmedi")
        return result

    scaled = [float(value) * _MM_PER_M for value in values[:6]]
    minimum, maximum = scaled[:3], scaled[3:6]
    size = [abs(maximum[index] - minimum[index]) for index in range(3)]
    result["min_corner_mm"] = [_round(value, 6) for value in minimum]
    result["max_corner_mm"] = [_round(value, 6) for value in maximum]
    result["size_mm"] = [_round(value, 6) for value in size]
    result["diagonal_mm"] = _round(math.sqrt(sum(value * value for value in size)), 6)
    return result


def inspect_interference(asm_model, treat_subassemblies_as_components=False,
                         treat_coincidence_as_interference=False, include_volume=True):
    """
    Run assembly interference detection.

    Args:
        asm_model: IAssemblyDoc.
        treat_subassemblies_as_components: Compare subassemblies as single components.
        treat_coincidence_as_interference: Count coincident faces as interference. Default False avoids false positives at bolt contacts and mating plates.
        include_volume: Read each interference volume to assess severity.

    Returns:
        dict with interference_count, items, severity, and manual_review_required.

    Always require manual review. Zero interference does not prove a correct design: clearances may be excessive or suppressed components excluded. Nonzero interference may be intentional for press fits, weldments, or injection-molded components.
    """
    result = {
        "status": "blocked",
        "interference_count": None,
        "items": [],
        "severity": None,
        "manual_review_required": True,
        "options": {
            "treat_subassemblies_as_components": bool(treat_subassemblies_as_components),
            "treat_coincidence_as_interference": bool(treat_coincidence_as_interference),
        },
        "errors": [],
    }

    try:
        asm_model.ClearSelection2(True)
        interference = get_com_member(asm_model, "InterferenceDetectionManager")
    except Exception as exc:
        result["errors"].append(f"Interference Detection nesnesi alınamadı: {exc}")
        return result

    if interference is None:
        result["errors"].append("InterferenceDetectionManager boş nesne döndü; etkin belgenin montaj olduğunu doğrulayın.")
        return result

    try:
        interference.TreatSubAssembliesAsComponents = bool(treat_subassemblies_as_components)
        interference.TreatCoincidenceAsInterference = bool(treat_coincidence_as_interference)
        interference.IgnoreHiddenBodies = False
        interference.ShowIgnoredInterferences = True
        interference.IncludeMultibodyPartInterferences = False
        result["options"].update(ignore_hidden_bodies=False,
                                 show_ignored_interferences=True,
                                 include_multibody_part_interferences=False)
        # GetInterferences computes results; call Done only after readback to release the manager.
        raw_items = get_com_member(interference, "GetInterferences")
        detected = list(raw_items) if raw_items is not None else []
        count = int(get_com_member(interference, "GetInterferenceCount"))
        if count < 0 or count != len(detected):
            raise RuntimeError(f"Interference sayısı diziyle eşleşmiyor: {count} != {len(detected)}")
        items = []
        for index, item in enumerate(detected):
            entry = {"index": index, "name": None}
            if include_volume:
                volume_m3 = float(get_com_member(item, "Volume"))
                if not math.isfinite(volume_m3) or volume_m3 < 0:
                    raise RuntimeError(f"Geçersiz interference hacmi: {volume_m3}")
                entry["volume_mm3"] = _round(volume_m3 * (_MM_PER_M**3), 6)
            components = get_com_member(item, "Components")
            entry["components"] = [
                {"name": get_com_member(component, "Name2"),
                 "path": get_com_member(component, "GetPathName")}
                for component in (components if components is not None else [])
            ]
            items.append(entry)
    except Exception as exc:
        result["errors"].append(f"Interference yapılandırma, hesaplama veya okuma başarısız: {exc}")
        return result
    finally:
        try:
            interference.Done()
        except Exception as exc:
            result["errors"].append(f"Interference Detection sonlandırılamadı: {exc}")

    if result["errors"]:
        return result

    volumes = [item.get("volume_mm3") for item in items if item.get("volume_mm3") is not None]
    if count == 0:
        result["severity"] = "none"
    elif volumes and max(volumes) < 1.0:
        result["severity"] = "negligible"
    elif volumes and max(volumes) < 100.0:
        result["severity"] = "minor"
    else:
        result["severity"] = "major"

    result["status"] = "pass" if count == 0 else "warn"
    result["interference_count"] = count
    result["items"] = items
    result["max_volume_mm3"] = _round(max(volumes), 6) if volumes else None
    return result


def check_tolerance_fit(shaft_mm, hole_mm, nominal_mm=None, fit="clearance"):
    """
    Calculate nominal fit clearance and provide an IT tolerance-grade reference.

    Args:
        shaft_mm: Measured or nominal external shaft diameter, mm.
        hole_mm: Measured or nominal internal hole diameter, mm.
        nominal_mm: Nominal dimension; defaults to hole size.
        fit: "clearance", "transition", or "interference".

    Returns:
        dict including clearance_mm and assessment.

    This is supporting information, not a tolerance-table replacement. Determine limit deviations using GB/T 1800 or ISO 286 and choose a functional fit designation such as H7/g6. Nominal SOLIDWORKS dimensions exclude tolerances; this checks only nominal clearance, not a tolerance stack.
    """
    nominal = float(nominal_mm if nominal_mm is not None else hole_mm)
    clearance = float(hole_mm) - float(shaft_mm)

    if fit == "clearance":
        expected = clearance > 0
        verdict = "Boşluklu geçme" if expected else "Boşluklu geçme değil: delik milden büyük değil"
    elif fit == "interference":
        expected = clearance < 0
        verdict = "Sıkı geçme" if expected else "Sıkı geçme değil: delik milden küçük değil"
    else:
        expected = True
        verdict = "Geçiş geçmesi"

    return {
        "nominal_mm": _round(nominal, 6),
        "hole_mm": _round(float(hole_mm), 6),
        "shaft_mm": _round(float(shaft_mm), 6),
        "clearance_mm": _round(clearance, 6),
        "fit_requested": fit,
        "fit_satisfied": bool(expected),
        "verdict": verdict,
        "caveat": "Nominal ölçüler tolerans içermez; gerçek geçme GB/T 1800 veya ISO 286 tabloları ve tolerans zinciri hesabı gerektirir.",
    }
