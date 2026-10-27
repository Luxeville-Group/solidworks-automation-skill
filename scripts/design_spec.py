"""
Parse and validate design specifications.

Mechanical engineers describe parts in version-controlled specifications; the
executor rebuilds them idempotently. Specifications can be diffed/committed, capture
design intent, produce repeatable feature-tree structures and use verify to compare
read-back geometry against expected values.

Example specification, default units mm:

.. code-block:: json

    {
      "schema_version": "1.0",
      "part_name": "motor_mount",
      "units": "mm",
      "base": {"type": "rect_plate", "width": 120, "height": 80, "thickness": 8},
      "holes": [
        {"id": "H1", "type": "through", "diameter": 6.6, "position": [15, 15]},
        {"id": "H2", "type": "blind", "diameter": 5.0, "depth": 6, "position": [15, 65]}
      ],
      "fillets": [{"radius": 4, "axis": "z", "convex_only": true}],
      "verify": {"envelope_mm": [120, 80, 8], "hole_count": 2,
                 "tolerance_mm": 0.1}
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

SUPPORTED_UNITS = {"mm", "cm", "m", "in"}

# Convert units to millimeters
_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
}

BASE_TYPES = {"rect_plate", "cylinder", "none"}

HOLE_TYPES = {"through", "blind", "counterbore", "countersink"}

MAX_HOLES = 200
MAX_FILLETS = 50


class DesignSpecError(ValueError):
    """Design spec doğrulanamadı."""

    def __init__(self, code, message, field=None):
        self.code = code
        self.field = field
        super().__init__(f"[{code}] {message}" + (f" (alan: {field})" if field else ""))


def unit_scale(units: str) -> float:
    """Return the unit-to-millimeter conversion factor."""
    key = str(units or "mm").strip().lower()
    if key not in _UNIT_TO_MM:
        raise DesignSpecError(
            "SPEC_UNIT_UNSUPPORTED",
            f"Desteklenmeyen birim {units!r}; seçenekler {sorted(_UNIT_TO_MM)}",
            "units",
        )
    return _UNIT_TO_MM[key]


def to_mm(value, units: str) -> float:
    """Convert specification lengths to millimeters."""
    try:
        return float(value) * unit_scale(units)
    except (TypeError, ValueError) as exc:
        raise DesignSpecError("SPEC_NUMBER_INVALID", f"Sayısal değer bekleniyordu; alınan {value!r}") from exc


def _positive(value, field, where=""):
    """Validate a positive number."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DesignSpecError("SPEC_NUMBER_INVALID", f"Sayısal değer bekleniyordu; alınan {value!r}", field) from exc
    if number <= 0:
        raise DesignSpecError("SPEC_NOT_POSITIVE", f"Pozitif sayı gerekli; alınan {number}", field)
    return number


def _position(value, field):
    """Validate 2D/3D coordinates."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise DesignSpecError("SPEC_POSITION_INVALID", f"[x, y] veya [x, y, z] bekleniyordu; alınan {value!r}", field)
    result = []
    for item in value[:3]:
        try:
            result.append(float(item))
        except (TypeError, ValueError) as exc:
            raise DesignSpecError("SPEC_POSITION_INVALID", f"Koordinat sayısal olmayan değer içeriyor: {item!r}", field) from exc
    while len(result) < 3:
        result.append(0.0)
    return result


def validate_design_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a design specification and normalize lengths to millimeters.

    Args:
        spec: Parsed dictionary; units comes from spec[units], default mm.

    Returns:
        Dictionary with status=ok and normalized specification on success;
        otherwise errors contains all problems so users can fix them together.
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if not isinstance(spec, dict):
        return {
            "status": "error",
            "errors": [{"code": "SPEC_NOT_OBJECT", "message": "Spec bir JSON object olmalıdır"}],
            "warnings": [],
        }

    version = str(spec.get("schema_version", SCHEMA_VERSION))
    if version != SCHEMA_VERSION:
        warnings.append(
            f"Spesifikasyon schema_version={version}; mevcut yürütücü sürümü {SCHEMA_VERSION}; "
            "Geçerli sürüme göre ayrıştırılacak; alan farklılıkları göz ardı edilebilir."
        )

    part_name = spec.get("part_name")
    if part_name is not None and not str(part_name).strip():
        errors.append({"code": "SPEC_PART_NAME_EMPTY", "message": "part_name boş olamaz", "field": "part_name"})

    units = str(spec.get("units", "mm"))
    try:
        scale = unit_scale(units)
    except DesignSpecError as exc:
        return {"status": "error", "errors": [{"code": exc.code, "message": str(exc), "field": exc.field}], "warnings": warnings}

    normalized: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "part_name": str(part_name or "part").strip() or "part",
        "source_units": units,
        "holes": [],
        "fillets": [],
    }

    # ---- base ----
    base_declared = "base" in spec and spec.get("base") is not None
    base = spec.get("base") or {}
    if not isinstance(base, dict):
        errors.append({"code": "SPEC_BASE_INVALID", "message": "base bir object olmalıdır", "field": "base"})
        base = {}
        base_declared = False
    # Missing base usually indicates an omission and would produce an empty document;
    # explicit base.type=none instead expresses an intentional features-only request.
    base_type = str(base.get("type", "none")).strip().lower()
    if not base_declared and base_type == "none":
        errors.append({
            "code": "SPEC_EMPTY",
            "message": (
                "Spec temel katıyı tanımlamıyor. base (rect_plate veya cylinder) belirtin; "
                "yalnızca sonraki feature işlemleri gerekiyorsa base.type=none değerini açıkça belirtin."
            ),
            "field": "base",
        })
    if base_type not in BASE_TYPES:
        errors.append({
            "code": "SPEC_BASE_TYPE",
            "message": f"Desteklenmeyen base.type={base_type!r}; seçenekler {sorted(BASE_TYPES)}",
            "field": "base.type",
        })
    else:
        entry: Dict[str, Any] = {"type": base_type}
        if base_type == "rect_plate":
            for key, mm_key in (("width", "width_mm"), ("height", "height_mm"), ("thickness", "thickness_mm")):
                if key not in base:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"rect_plate eksik alan: {key}", "field": f"base.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(base[key], f"base.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif base_type == "cylinder":
            for key, mm_key in (("diameter", "diameter_mm"), ("height", "height_mm")):
                if key not in base:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"cylinder eksik alan: {key}", "field": f"base.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(base[key], f"base.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        normalized["base"] = entry

    # ---- holes ----
    holes = spec.get("holes") or []
    if not isinstance(holes, list):
        errors.append({"code": "SPEC_HOLES_INVALID", "message": "holes bir array olmalıdır", "field": "holes"})
        holes = []
    elif len(holes) > MAX_HOLES:
        errors.append({
            "code": "SPEC_HOLES_TOO_MANY",
            "message": f"holes sayısı {len(holes)} sınırı aşıyor: {MAX_HOLES}",
            "field": "holes",
        })
        holes = holes[:MAX_HOLES]

    seen_ids = set()
    for index, hole in enumerate(holes):
        where = f"holes[{index}]"
        if not isinstance(hole, dict):
            errors.append({"code": "SPEC_HOLE_INVALID", "message": "Delik bir object olmalıdır", "field": where})
            continue
        hole_type = str(hole.get("type", "through")).strip().lower()
        if hole_type not in HOLE_TYPES:
            errors.append({
                "code": "SPEC_HOLE_TYPE",
                "message": f"Desteklenmeyen delik türü {hole_type!r}; seçenekler {sorted(HOLE_TYPES)}",
                "field": f"{where}.type",
            })
            continue

        entry = {"type": hole_type}
        hole_id = hole.get("id")
        if hole_id is not None:
            hole_id = str(hole_id)
            if hole_id in seen_ids:
                errors.append({"code": "SPEC_HOLE_ID_DUPLICATE", "message": f"Yinelenen delik id: {hole_id}", "field": f"{where}.id"})
            seen_ids.add(hole_id)
            entry["id"] = hole_id
        else:
            warnings.append(f"{where} için id verilmedi; inceleme izlenebilirliği için her deliği adlandırın.")
            entry["id"] = f"H{index + 1}"

        try:
            entry["diameter_mm"] = round(_positive(hole.get("diameter"), f"{where}.diameter") * scale, 6)
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        try:
            entry["position_mm"] = [round(value * scale, 6) for value in _position(hole.get("position"), f"{where}.position")]
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})

        if hole_type == "blind":
            if hole.get("depth") is None:
                errors.append({"code": "SPEC_FIELD_MISSING", "message": "Blind hole için depth belirtilmelidir", "field": f"{where}.depth"})
            else:
                try:
                    entry["depth_mm"] = round(_positive(hole["depth"], f"{where}.depth") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif hole_type == "counterbore":
            for key, mm_key in (("counterbore_diameter", "counterbore_diameter_mm"), ("counterbore_depth", "counterbore_depth_mm")):
                if hole.get(key) is None:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"Counterbore için gerekli: {key}", "field": f"{where}.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(hole[key], f"{where}.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif hole_type == "countersink":
            for key, mm_key in (("countersink_diameter", "countersink_diameter_mm"), ("angle", "angle_deg")):
                if hole.get(key) is None:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"Countersink için gerekli: {key}", "field": f"{where}.{key}"})
                    continue
                if key == "angle":
                    entry[mm_key] = float(hole[key])
                else:
                    try:
                        entry[mm_key] = round(_positive(hole[key], f"{where}.{key}") * scale, 6)
                    except DesignSpecError as exc:
                        errors.append({"code": exc.code, "message": str(exc), "field": exc.field})

        normalized["holes"].append(entry)

    # ---- fillets ----
    fillets = spec.get("fillets") or []
    if not isinstance(fillets, list):
        errors.append({"code": "SPEC_FILLETS_INVALID", "message": "fillets bir array olmalıdır", "field": "fillets"})
        fillets = []
    elif len(fillets) > MAX_FILLETS:
        errors.append({
            "code": "SPEC_FILLETS_TOO_MANY",
            "message": f"fillets sayısı {len(fillets)} sınırı aşıyor: {MAX_FILLETS}",
            "field": "fillets",
        })
        fillets = fillets[:MAX_FILLETS]

    for index, fillet in enumerate(fillets):
        where = f"fillets[{index}]"
        if not isinstance(fillet, dict):
            errors.append({"code": "SPEC_FILLET_INVALID", "message": "Fillet bir object olmalıdır", "field": where})
            continue
        entry = {}
        try:
            entry["radius_mm"] = round(_positive(fillet.get("radius"), f"{where}.radius") * scale, 6)
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        axis = str(fillet.get("axis", "z")).strip().lower()
        if axis not in {"x", "y", "z", "vertical", "all"}:
            errors.append({"code": "SPEC_FILLET_AXIS", "message": f"Desteklenmeyen axis={axis!r}", "field": f"{where}.axis"})
        else:
            entry["axis"] = axis
        for flag in ("convex_only", "concave_only"):
            if flag in fillet:
                entry[flag] = bool(fillet[flag])
        if entry.get("convex_only") and entry.get("concave_only"):
            errors.append({"code": "SPEC_FILLET_FLAGS", "message": "convex_only ve concave_only aynı anda true olamaz", "field": where})
        normalized["fillets"].append(entry)

    # ---- Fillet-radius feasibility ----
    thickness = (normalized.get("base") or {}).get("thickness_mm")
    for index, fillet in enumerate(normalized["fillets"]):
        radius = fillet.get("radius_mm")
        if radius is None or not thickness:
            continue
        if radius * 2 > thickness:
            warnings.append(
                f"fillets[{index}] yarıçapı {radius} mm; levha kalınlığının yarısını aşıyor (kalınlık {thickness} mm), "
                "SolidWorks oluşturamayabilir veya kendiyle kesişme oluşabilir; tasarım amacını doğrulayın."
            )

    # ---- verify ----
    verify = spec.get("verify") or {}
    if verify and not isinstance(verify, dict):
        errors.append({"code": "SPEC_VERIFY_INVALID", "message": "verify bir object olmalıdır", "field": "verify"})
        verify = {}
    if verify:
        normalized_verify: Dict[str, Any] = {}
        if verify.get("envelope_mm") is not None:
            try:
                normalized_verify["envelope_mm"] = [round(value * scale, 6) for value in _position(verify["envelope_mm"], "verify.envelope_mm")]
            except DesignSpecError as exc:
                errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        if verify.get("hole_count") is not None:
            try:
                normalized_verify["hole_count"] = int(verify["hole_count"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.hole_count bir tamsayı olmalıdır", "field": "verify.hole_count"})
        if verify.get("tolerance_mm") is not None:
            try:
                normalized_verify["tolerance_mm"] = abs(float(verify["tolerance_mm"]))
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.tolerance_mm sayısal olmalıdır", "field": "verify.tolerance_mm"})
        if verify.get("min_mass_g") is not None:
            try:
                normalized_verify["min_mass_g"] = float(verify["min_mass_g"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.min_mass_g sayısal olmalıdır", "field": "verify.min_mass_g"})
        if verify.get("max_mass_g") is not None:
            try:
                normalized_verify["max_mass_g"] = float(verify["max_mass_g"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.max_mass_g sayısal olmalıdır", "field": "verify.max_mass_g"})
        normalized["verify"] = normalized_verify
    else:
        normalized["verify"] = {}

    return {
        "status": "ok" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized if not errors else None,
    }


def load_design_spec(path) -> Dict[str, Any]:
    """
    Read and validate a .json design specification.

    Args:
        path: Specification path.

    Returns:
        validate_design_spec result with source_path added.
    """
    resolved = Path(str(path)).expanduser().resolve()
    if not resolved.is_file():
        return {
            "status": "error",
            "errors": [{"code": "SPEC_FILE_MISSING", "message": f"Spesifikasyon dosyası yok: {resolved}"}],
            "warnings": [],
            "source_path": str(resolved),
        }
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "errors": [{"code": "SPEC_JSON_INVALID", "message": f"JSON ayrıştırılamadı: {exc}"}],
            "warnings": [],
            "source_path": str(resolved),
        }
    result = validate_design_spec(payload)
    result["source_path"] = str(resolved)
    return result


def compare_verification(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare measured geometry with the specification verify section.

    Args:
        actual: Read-back envelope_mm / hole_count / mass_g.
        expected: Normalized verify section.

    Returns:
        Dictionary with pass/warn/skipped status and per-comparison checks.

    Mismatches return warn rather than error: they may reflect design changes
    instead of execution defects and require engineering judgment. Never silently pass.
    """
    checks: List[Dict[str, Any]] = []
    tolerance = float(expected.get("tolerance_mm", 0.1) or 0.1)

    expected_envelope = expected.get("envelope_mm")
    actual_size = actual.get("envelope_mm") or actual.get("size_mm")
    if expected_envelope and actual_size:
        deltas = []
        for axis in range(3):
            want = float(expected_envelope[axis]) if axis < len(expected_envelope) else 0.0
            got = float(actual_size[axis]) if axis < len(actual_size) else 0.0
            deltas.append(abs(got - want))
        passed = max(deltas) <= tolerance
        checks.append({
            "name": "envelope_mm",
            "expected": list(expected_envelope),
            "actual": list(actual_size),
            "max_delta_mm": round(max(deltas), 6),
            "tolerance_mm": tolerance,
            "passed": passed,
        })
    elif expected_envelope:
        checks.append({
            "name": "envelope_mm",
            "expected": list(expected_envelope),
            "actual": None,
            "passed": False,
            "note": "Bounding box okunamadı; boyutlar doğrulanamıyor.",
        })

    if expected.get("hole_count") is not None:
        actual_count = actual.get("hole_count")
        checks.append({
            "name": "hole_count",
            "expected": expected["hole_count"],
            "actual": actual_count,
            "passed": actual_count == expected["hole_count"],
        })

    mass_g = actual.get("mass_g")
    if expected.get("min_mass_g") is not None:
        checks.append({
            "name": "min_mass_g",
            "expected": expected["min_mass_g"],
            "actual": mass_g,
            "passed": mass_g is not None and mass_g >= expected["min_mass_g"],
        })
    if expected.get("max_mass_g") is not None:
        checks.append({
            "name": "max_mass_g",
            "expected": expected["max_mass_g"],
            "actual": mass_g,
            "passed": mass_g is not None and mass_g <= expected["max_mass_g"],
        })

    if not checks:
        return {"status": "skipped", "checks": [], "note": "Spec verify bölümü içermiyor; geometri doğrulaması atlandı."}

    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "pass" if not failed else "warn",
        "checks": checks,
        "failed": [check["name"] for check in failed],
        "manual_review_required": bool(failed),
    }
