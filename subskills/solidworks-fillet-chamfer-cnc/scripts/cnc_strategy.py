'Offline parameters, DFM constraints and execution plans for the CNC fillet/chamfer subskill. Validate parameters before connecting SolidWorks COM and generate an auditable feature plan. Uses only the Python standard library for CI, VibeCAD and desktop preflight.'

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class MountParameters:
    'CNC mounting-base parameters; all lengths are millimeters.'

    length: float = 120.0
    width: float = 80.0
    thickness: float = 18.0
    boss_length: float = 58.0
    boss_width: float = 34.0
    boss_height: float = 10.0
    base_corner_radius: float = 8.0
    boss_corner_radius: float = 5.0
    top_chamfer: float = 1.0
    bottom_chamfer: float = 0.8
    boss_top_chamfer: float = 0.8
    hole_chamfer: float = 0.5
    chamfer_angle_deg: float = 45.0
    mount_hole_diameter: float = 7.0
    counterbore_diameter: float = 13.0
    counterbore_depth: float = 4.0
    mount_hole_x: float = 46.0
    mount_hole_y: float = 28.0
    dowel_hole_diameter: float = 5.0
    dowel_hole_x: float = 0.0
    dowel_hole_y: float = 24.0
    slot_length: float = 62.0
    slot_width: float = 16.0
    pocket_length: float = 24.0
    pocket_width: float = 30.0
    pocket_center_x: float = 45.0
    pocket_depth: float = 4.0
    pocket_shape: str = "rounded_slot"
    minimum_edge_wall: float = 2.0
    minimum_feature_web: float = 2.0
    minimum_bottom_wall: float = 3.0


NUMERIC_FIELDS = tuple(
    item.name for item in fields(MountParameters) if item.name != "pocket_shape"
)
NONNEGATIVE_FIELDS = {
    "base_corner_radius",
    "boss_corner_radius",
    "top_chamfer",
    "bottom_chamfer",
    "boss_top_chamfer",
    "hole_chamfer",
    "dowel_hole_x",
    "dowel_hole_y",
}
POCKET_SHAPES = {"rounded_slot", "rectangle"}
INVALID_BASENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def finite_number(name: str, value: Any) -> float:
    'Convert input to a finite float.'
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} sayısal olmalıdır / must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} sonlu sayı olmalıdır / must be finite")
    return number


def validate_basename(value: str) -> str:
    'Validate the output basename against path escape and invalid Windows characters.'
    basename = str(value).strip()
    if not basename or basename in {".", ".."}:
        raise ValueError('basename boş veya nokta yolu olamaz / basename cannot be empty or a dot path')
    if Path(basename).name != basename or INVALID_BASENAME.search(basename):
        raise ValueError('basename yol veya geçersiz Windows karakteri içeremez / basename must be a filename without paths or invalid Windows characters')
    return basename


def _coerce_overrides(overrides: Mapping[str, Any]) -> dict[str, Any]:
    'Validate parameter keys and convert overrides to field types.'
    allowed = {item.name for item in fields(MountParameters)}
    unknown = sorted(set(overrides) - allowed)
    if unknown:
        raise ValueError(f"Bilinmeyen parametre / Unknown parameter: {', '.join(unknown)}")
    result: dict[str, Any] = {}
    for name, value in overrides.items():
        if name == "pocket_shape":
            result[name] = str(value).strip().lower()
        else:
            result[name] = finite_number(name, value)
    return result


def parse_set_values(items: list[str] | tuple[str, ...]) -> dict[str, Any]:
    'Parse repeated --set name=value arguments.'
    overrides: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--set için name=value biçimi gerekir / --set requires name=value: {item}")
        name, value = item.split("=", 1)
        name = name.strip()
        if not name or not value.strip():
            raise ValueError(f"--set adı ve değeri boş olamaz / --set name and value cannot be empty: {item}")
        overrides[name] = value.strip()
    return _coerce_overrides(overrides)


def load_parameter_file(path: Path) -> dict[str, Any]:
    'Read a parameter JSON file, accepting a direct object or a parameters wrapper.'
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Parametre dosyası okunamıyor / Cannot read parameter file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError('Parametre dosyasının kökü JSON nesnesi olmalıdır / Parameter-file root must be a JSON object')
    values = payload.get("parameters", payload)
    if not isinstance(values, dict):
        raise ValueError('parameters bir JSON nesnesi olmalıdır / parameters must be a JSON object')
    return _coerce_overrides(values)


def parameter_positions(params: MountParameters) -> dict[str, list[tuple[float, float]]]:
    'Return the shared hole-position source for modeling and offline collision checks.'
    mount = [
        (x, y)
        for x in (-params.mount_hole_x, params.mount_hole_x)
        for y in (-params.mount_hole_y, params.mount_hole_y)
    ]
    dowel = [
        (-params.dowel_hole_x, -params.dowel_hole_y),
        (params.dowel_hole_x, params.dowel_hole_y),
    ]
    return {"mount": mount, "dowel": dowel}


def _circle_gap(
    first: tuple[float, float],
    first_radius: float,
    second: tuple[float, float],
    second_radius: float,
) -> float:
    'Compute net clearance between two circular machining features.'
    return math.dist(first, second) - first_radius - second_radius


def _point_to_centered_slot_gap(
    point: tuple[float, float],
    point_radius: float,
    size_x: float,
    size_y: float,
) -> float:
    'Compute clearance from a circular feature to an origin-centered horizontal/vertical obround slot.'
    if size_x >= size_y:
        slot_radius = size_y / 2.0
        half_centerline = max(0.0, size_x / 2.0 - slot_radius)
        closest = (min(max(point[0], -half_centerline), half_centerline), 0.0)
    else:
        slot_radius = size_x / 2.0
        half_centerline = max(0.0, size_y / 2.0 - slot_radius)
        closest = (0.0, min(max(point[1], -half_centerline), half_centerline))
    return math.dist(point, closest) - point_radius - slot_radius


def analyze_parameters(params: MountParameters) -> dict[str, Any]:
    'Run engineering-parameter and 2D-envelope checks without COM.'
    errors: list[str] = []
    warnings: list[str] = []

    for name in NUMERIC_FIELDS:
        value = finite_number(name, getattr(params, name))
        if name in NONNEGATIVE_FIELDS:
            if value < 0.0:
                errors.append(f"{name} 0'dan küçük olamaz / cannot be below 0")
        elif value <= 0.0:
            errors.append(f"{name} 0'dan büyük olmalıdır / must be above 0")

    if params.pocket_shape not in POCKET_SHAPES:
        errors.append(f"pocket_shape şu seçeneklerden biri olmalıdır / pocket_shape must be one of: {sorted(POCKET_SHAPES)} seçenekleri / options")
    if not 5.0 <= params.chamfer_angle_deg <= 85.0:
        errors.append('chamfer_angle_deg 5 ile 85 derece arasında olmalıdır / chamfer_angle_deg must be between 5 and 85 degrees')
    if params.boss_length + 2.0 * params.minimum_feature_web > params.length:
        errors.append('boss_length taban uzunluğunda minimum basamak genişliğini bırakmıyor / boss_length leaves insufficient step width along the base')
    if params.boss_width + 2.0 * params.minimum_feature_web > params.width:
        errors.append('boss_width taban genişliğinde minimum basamak genişliğini bırakmıyor / boss_width leaves insufficient step width across the base')
    if params.base_corner_radius * 2.0 >= min(params.length, params.width):
        errors.append('base_corner_radius çok büyük; radyüs kendini kesebilir veya bozulabilir / base_corner_radius risks self-intersection or degeneration')
    if params.boss_corner_radius * 2.0 >= min(params.boss_length, params.boss_width):
        errors.append('boss_corner_radius çok büyük; radyüs kendini kesebilir veya bozulabilir / boss_corner_radius risks self-intersection or degeneration')

    if params.top_chamfer > params.thickness / 2.0:
        errors.append('top_chamfer taban kalınlığının yarısını aşamaz / top_chamfer cannot exceed half the base thickness')
    if params.bottom_chamfer > params.thickness / 2.0:
        errors.append('bottom_chamfer taban kalınlığının yarısını aşamaz / bottom_chamfer cannot exceed half the base thickness')
    if params.top_chamfer + params.bottom_chamfer >= params.thickness:
        errors.append('Üst ve alt pahlar kalınlık yönünde katı bırakmıyor / Top and bottom chamfers leave no solid through the thickness')
    if params.boss_top_chamfer > params.boss_height / 2.0:
        errors.append('boss_top_chamfer çıkıntı yüksekliğinin yarısını aşamaz / boss_top_chamfer cannot exceed half the boss height')
    if params.base_corner_radius and params.top_chamfer > params.base_corner_radius:
        warnings.append('top_chamfer, base_corner_radius değerini aşıyor; kesişimde çözüm riski yüksek / top_chamfer exceeds base_corner_radius; increased junction solver risk')
    if params.boss_corner_radius and params.boss_top_chamfer > params.boss_corner_radius:
        warnings.append('boss_top_chamfer, boss_corner_radius değerini aşıyor; kesişimde çözüm riski yüksek / boss_top_chamfer exceeds boss_corner_radius; increased junction solver risk')

    if params.counterbore_diameter <= params.mount_hole_diameter:
        errors.append('counterbore_diameter, mount_hole_diameter değerinden büyük olmalıdır / counterbore_diameter must exceed mount_hole_diameter')
    if params.counterbore_depth >= params.thickness - params.minimum_bottom_wall:
        errors.append('counterbore_depth, minimum_bottom_wall bırakmıyor / counterbore_depth does not preserve minimum_bottom_wall')
    if params.pocket_depth >= params.thickness - params.minimum_bottom_wall:
        errors.append('pocket_depth, minimum_bottom_wall bırakmıyor / pocket_depth does not preserve minimum_bottom_wall')
    if params.hole_chamfer > params.counterbore_depth / 2.0:
        errors.append('hole_chamfer havşa derinliğine göre çok büyük / hole_chamfer is too large for the counterbore depth')

    positions = parameter_positions(params)
    mount_radius = params.counterbore_diameter / 2.0 + params.hole_chamfer
    dowel_radius = params.dowel_hole_diameter / 2.0 + params.hole_chamfer
    for label, points, radius in (
        ('Montaj havşası / Mounting counterbore', positions["mount"], mount_radius),
        ('Konumlandırma deliği / Dowel hole', positions["dowel"], dowel_radius),
    ):
        for x, y in points:
            if abs(x) + radius + params.minimum_edge_wall > params.length / 2.0:
                errors.append(f"{label} X={x:g} taban dışında veya kenar et kalınlığı yetersiz / outside base or insufficient edge wall")
            if abs(y) + radius + params.minimum_edge_wall > params.width / 2.0:
                errors.append(f"{label} Y={y:g} taban dışında veya kenar et kalınlığı yetersiz / outside base or insufficient edge wall")

    all_holes = [
        *(('mount', point, mount_radius) for point in positions["mount"]),
        *(('dowel', point, dowel_radius) for point in positions["dowel"]),
    ]
    if len(set(positions["dowel"])) != len(positions["dowel"]):
        errors.append('İki konumlandırma deliği çakışıyor; dowel_hole_x ve dowel_hole_y birlikte 0 olamaz / Dowel holes coincide; x and y cannot both be zero')
    for index, (first_kind, first, first_radius) in enumerate(all_holes):
        for second_kind, second, second_radius in all_holes[index + 1 :]:
            gap = _circle_gap(first, first_radius, second, second_radius)
            if gap < params.minimum_feature_web:
                errors.append(
                    f"{first_kind} delik / hole {first} ve / and {second_kind} delik / hole {second} net aralık / net clearance "
                    f"{gap:.3f} mm, minimum_feature_web değerinden küçük / mm is below minimum_feature_web"
                )

    slot_major = max(params.slot_length, params.slot_width)
    if not math.isclose(params.slot_length, slot_major):
        warnings.append('slot_length, slot_width değerinden küçük; uzun boyut kanal ekseni olarak kullanılacak / slot_length is below slot_width; the longer dimension becomes the slot axis')
    if params.slot_length + 2.0 * params.minimum_edge_wall > params.length:
        errors.append('Merkez uzun delik uzunluk yönünde kenar etini korumuyor / Center slot leaves insufficient end wall')
    if params.slot_width + 2.0 * params.minimum_edge_wall > params.width:
        errors.append('Merkez uzun delik genişlik yönünde kenar etini korumuyor / Center slot leaves insufficient side wall')
    if params.slot_length > params.boss_length or params.slot_width > params.boss_width:
        warnings.append('Merkez kanal çıkıntı sınırını aşıp tabana giriyor; kapalı cep yerine geçiş istendiğini doğrulayın / Center slot cuts beyond the boss into the base; confirm a through channel is intended')

    if abs(params.pocket_center_x) + params.pocket_length / 2.0 + params.minimum_edge_wall > params.length / 2.0:
        errors.append('Hafifletme cebi X yönünde tabanı aşıyor veya kenar eti yetersiz / Pocket exceeds X bounds or leaves insufficient edge wall')
    if params.pocket_width / 2.0 + params.minimum_edge_wall > params.width / 2.0:
        errors.append('Hafifletme cebi Y yönünde tabanı aşıyor veya kenar eti yetersiz / Pocket exceeds Y bounds or leaves insufficient edge wall')
    center_slot_half_x = params.slot_length / 2.0
    pocket_inner_x = abs(params.pocket_center_x) - params.pocket_length / 2.0
    slot_pocket_web = pocket_inner_x - center_slot_half_x
    if slot_pocket_web < params.minimum_feature_web:
        errors.append(
            f"Merkez kanal ile cep arasında X net aralığı / X clearance between center slot and pocket {slot_pocket_web:.3f} mm "
            'minimum_feature_web değerinden küçük / below minimum_feature_web'
        )
    if params.pocket_shape == "rectangle":
        warnings.append('Dikdörtgen cep keskin iç köşeler içeriyor; CNC için takım radyüsü belirtin veya rounded_slot kullanın / Rectangular pocket has sharp internal corners; specify tool radius or use rounded_slot')

    for kind, point, radius in all_holes:
        gap = _point_to_centered_slot_gap(point, radius, params.slot_length, params.slot_width)
        if gap < params.minimum_feature_web:
            errors.append(f"{kind} delik / hole {point} merkez kanala net aralık / clearance to center slot {gap:.3f} mm yetersiz / mm is insufficient")
        pocket_dx = abs(abs(point[0]) - abs(params.pocket_center_x)) - params.pocket_length / 2.0
        pocket_dy = abs(point[1]) - params.pocket_width / 2.0
        approximate_gap = math.hypot(max(0.0, pocket_dx), max(0.0, pocket_dy)) - radius
        if pocket_dx <= 0.0 and pocket_dy <= 0.0:
            approximate_gap = -radius
        if approximate_gap < params.minimum_feature_web:
            errors.append(f"{kind} delik / hole {point} cep sınırına net aralık yetersiz / insufficient clearance to pocket envelope")

    return {
        "status": "blocked" if errors else "pass_with_warnings" if warnings else "pass",
        "errors": errors,
        "warnings": warnings,
        "calculated": {
            "mount_hole_positions_mm": positions["mount"],
            "dowel_hole_positions_mm": positions["dowel"],
            "slot_to_pocket_web_mm": round(slot_pocket_web, 6),
            "base_bottom_wall_mm": round(params.thickness - params.pocket_depth, 6),
            "counterbore_bottom_wall_mm": round(params.thickness - params.counterbore_depth, 6),
        },
    }


def require_valid_parameters(params: MountParameters) -> dict[str, Any]:
    'Block COM modeling immediately on hard parameter errors.'
    report = analyze_parameters(params)
    if report["errors"]:
        raise ValueError("；".join(report["errors"]))
    return report


def build_parameters(*overrides: Mapping[str, Any]) -> tuple[MountParameters, dict[str, Any]]:
    'Apply parameter overrides in order and return a validated immutable object.'
    params = MountParameters()
    for values in overrides:
        params = replace(params, **_coerce_overrides(values))
    report = require_valid_parameters(params)
    return params, report


def fallback_values(value_mm: float, policy: str) -> list[float]:
    'Generate a bounded, traceable dimension-fallback ladder.'
    if value_mm <= 0.0:
        return []
    if policy == "strict":
        return [value_mm]
    if policy != "progressive":
        raise ValueError('failure_policy strict veya progressive olmalıdır / failure_policy must be strict or progressive')
    values = [value_mm, value_mm * 0.75, value_mm * 0.5]
    return list(dict.fromkeys(round(item, 6) for item in values if item >= 0.1))


def build_operation_plan(params: MountParameters, failure_policy: str = "progressive") -> list[dict[str, Any]]:
    'Generate a plan with explicit semantic targets, expected edge counts and dimension fallbacks.'
    operations = [
        ("outer_treatments", "Fillet_Base_Corners", "fillet", "base_vertical_edges", 4, params.base_corner_radius),
        ("outer_treatments", "Fillet_Boss_Corners", "fillet", "boss_vertical_edges", 4, params.boss_corner_radius),
        (
            "outer_treatments",
            "Chamfer_Top_Outer",
            "chamfer",
            "base_top_outer_loop",
            8 if params.base_corner_radius > 0.0 else 4,
            params.top_chamfer,
        ),
        (
            "outer_treatments",
            "Chamfer_Bottom_Outer",
            "chamfer",
            "base_bottom_outer_loop",
            8 if params.base_corner_radius > 0.0 else 4,
            params.bottom_chamfer,
        ),
        (
            "outer_treatments",
            "Chamfer_Boss_Top",
            "chamfer",
            "boss_top_outer_loop",
            8 if params.boss_corner_radius > 0.0 else 4,
            params.boss_top_chamfer,
        ),
        ("finishing", "Chamfer_Hole_Mouths", "chamfer", "hole_mouth_loops", 6, params.hole_chamfer),
    ]
    plan = []
    for stage, name, kind, target, expected_count, value in operations:
        if value <= 0.0:
            continue
        plan.append(
            {
                "stage": stage,
                "name": name,
                "kind": kind,
                "target": target,
                "expected_edge_count": expected_count,
                "requested_value_mm": value,
                "attempt_values_mm": fallback_values(value, failure_policy),
                "angle_deg": params.chamfer_angle_deg if kind == "chamfer" else None,
                "required": True,
            }
        )
    return plan


def plan_payload(
    params: MountParameters,
    validation: Mapping[str, Any],
    failure_policy: str,
) -> dict[str, Any]:
    'Return a directly serializable v2 plan payload.'
    return {
        "schema_version": 2,
        "units": "mm",
        "parameters": asdict(params),
        "validation": dict(validation),
        "failure_policy": failure_policy,
        "operations": build_operation_plan(params, failure_policy),
    }
