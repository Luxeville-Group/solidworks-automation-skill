"""
SOLIDWORKS appearance and material utilities.

Appearance APIs vary by version and object type. These tolerant wrappers try common document, feature, and component interfaces in sequence for the same color.
"""
import re

try:
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()

SW_THIS_CONFIGURATION = 1
SW_SPECIFY_CONFIGURATION = 3


PRESET_COLORS = {
    "iron_red": "#8A0E0E",
    "armor_gold": "#D99A22",
    "dark_gunmetal": "#1F2328",
    "arc_blue": "#2AA8FF",
    "black": "#050505",
    "white": "#F2F2F2",
    "silver": "#BFC4C8",
    "aqua_blue": "#4FA6A8",
    "glass_tint": "#10232E",
    "signal_red": "#E31B35",
    "light_cyan": "#9DEBFF",
    "tire_black": "#111315",
    "graphite": "#33383D",
}


def rgb01(color):
    """
    Convert a color to RGB in the range 0..1.

    Supports preset names such as "iron_red", hexadecimal values such as "#8A0E0E", RGB tuples in 0..255, and RGB tuples in 0..1.
    """
    if isinstance(color, str):
        value = PRESET_COLORS.get(color, color).strip()
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
        if not match:
            raise ValueError(f"Bilinmeyen renk: {color}")
        hex_value = match.group(1)
        return tuple(int(hex_value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    if len(color) != 3:
        raise ValueError("RGB rengi 3 değer içermeli")
    if max(color) > 1:
        return tuple(float(v) / 255.0 for v in color)
    return tuple(float(v) for v in color)


def material_values(color, ambient=0.35, diffuse=0.75, specular=0.45,
                    shininess=0.35, transparency=0.0, emission=0.0):
    """
    Build a SOLIDWORKS material property array.

    Order: red, green, blue, ambient, diffuse, specular, shininess, transparency, emission.
    """
    red, green, blue = rgb01(color)
    return [red, green, blue, ambient, diffuse, specular, shininess, transparency, emission]


def material_variant(values):
    """Wrap the nine material values as COM SAFEARRAY(double) to prevent RGB channel misalignment."""
    if len(values) != 9:
        raise ValueError("SOLIDWORKS malzeme dizisi 9 değer içermeli")
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


def _configuration_args(configuration):
    """Build the configuration options and names for SetMaterialPropertyValues2."""
    if not configuration:
        return SW_THIS_CONFIGURATION, None
    names = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [str(configuration)])
    return SW_SPECIFY_CONFIGURATION, names


def _try_set(target, attr_name, values, *args):
    """Try setting a property or calling a method; a void method succeeds if it raises no exception."""
    try:
        member = getattr(target, attr_name)
        if callable(member):
            result = member(values, *args)
        else:
            setattr(target, attr_name, values)
            result = True
        return bool(result) if result is not None else True
    except Exception:
        return False


def get_material_property_values(target):
    """Read the nine material values from a document, feature, or component; return None on failure."""
    readers = [
        lambda: target.MaterialPropertyValues,
        lambda: target.GetMaterialPropertyValues(),
    ]
    for reader in readers:
        try:
            values = reader()
            if values is not None and len(values) >= 9:
                return tuple(float(value) for value in values[:9])
        except Exception:
            pass
    return None


def verify_appearance(target, color, tolerance=0.01):
    """Read back and verify the first three RGB values, returning structured results."""
    expected = rgb01(color)
    actual_values = get_material_property_values(target)
    actual = actual_values[:3] if actual_values else None
    max_error = max(abs(a - e) for a, e in zip(actual, expected)) if actual else None
    return {
        "ok": actual is not None and max_error <= float(tolerance),
        "expected_rgb": expected,
        "actual_rgb": actual,
        "max_error": max_error,
    }


def set_document_appearance(model, color, configuration=""):
    """
    Set document appearance color. Return True if at least one interface call succeeds.
    """
    packed = material_variant(material_values(color))
    option, names = _configuration_args(configuration)
    if configuration:
        extension = getattr(model, "Extension", None)
        wrote = bool(extension) and _try_set(
            extension, "SetMaterialPropertyValues", packed, option, names
        )
    else:
        wrote = _try_set(model, "MaterialPropertyValues", packed)
    return wrote and verify_appearance(model, color)["ok"]


def set_feature_appearance(feature, color, configuration=""):
    """
    Set feature appearance color. Return True if at least one interface call succeeds.
    """
    packed = material_variant(material_values(color))
    option, names = _configuration_args(configuration)
    wrote = _try_set(feature, "SetMaterialPropertyValues2", packed, option, names)
    if not wrote and not configuration:
        wrote = _try_set(feature, "SetMaterialPropertyValues", packed)
    return wrote and verify_appearance(feature, color)["ok"]


def set_component_appearance(component, color, configuration=""):
    """
    Set assembly component appearance color. Return True if at least one interface call succeeds.
    """
    packed = material_variant(material_values(color))
    option, names = _configuration_args(configuration)
    wrote = _try_set(component, "SetMaterialPropertyValues2", packed, option, names)
    if not wrote and not configuration:
        wrote = _try_set(component, "MaterialPropertyValues", packed)
    return wrote and verify_appearance(component, color)["ok"]


def apply_component_palette(assignments, strict=True):
    """
    Set component colors in a batch and read each back.

    Args:
        assignments: [(component, color), ...].
        strict: Raise RuntimeError immediately if any component fails when True.

    Returns:
        list[dict] with index, color, ok, expected_rgb, actual_rgb, and max_error.
    """
    reports = []
    for index, (component, color) in enumerate(assignments):
        wrote = set_component_appearance(component, color)
        report = verify_appearance(component, color)
        report.update({"index": index, "color": color, "ok": wrote and report["ok"]})
        reports.append(report)
        if strict and not report["ok"]:
            raise RuntimeError(
                f"Bileşen {index} görünüş doğrulaması başarısız: beklenen {report['expected_rgb']}, "
                f"gerçek {report['actual_rgb']}"
            )
    return reports


def apply_named_appearance(target, name):
    """
    Apply a preset appearance to a common object.

    Try document, component, and feature interfaces in that order.
    """
    return (
        set_document_appearance(target, name)
        or set_component_appearance(target, name)
        or set_feature_appearance(target, name)
    )
