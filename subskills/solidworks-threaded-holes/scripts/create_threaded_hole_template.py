'Generate a SolidWorks internal-thread sample. Default: M6x1 blind hole with real tap-drill geometry, mouth chamfer, properties and optional evidence helix. Attempt real Thread/CosmeticThread first; fallback delivery remains subject to feature persistence and review gates.'
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
PARENT_SKILL_DIR = THIS_FILE.parents[3]
PARENT_SCRIPT_DIR = PARENT_SKILL_DIR / "scripts"
sys.path.insert(0, str(PARENT_SCRIPT_DIR))

from sw_appearance import set_document_appearance  # noqa: E402
from sw_connect import create_empty_dispatch_variant, get_com_member, mm  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_part import extrude_boss, sketch, sketch_rectangle  # noqa: E402
from sw_review import run_review, save_preview  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402

SW_SOLID_BODY = 0
SW_FM_SWEEP_THREAD = 87
SW_THREAD_METHOD_CUT = 0
SW_THREAD_END_BLIND = 0
SW_THREAD_END_REVOLUTIONS = 1
SW_COSMETIC_STANDARD_ISO = 8
SW_COSMETIC_END_BLIND = 0
SW_COSMETIC_END_THROUGH = 2
SW_END_COND_BLIND = 0
SW_END_COND_THROUGH_ALL = 1


THREAD_TABLE = {
    "M3X0.5": {"label": "M3x0.5", "nominal_mm": 3.0, "pitch_mm": 0.5, "tap_drill_mm": 2.5},
    "M4X0.7": {"label": "M4x0.7", "nominal_mm": 4.0, "pitch_mm": 0.7, "tap_drill_mm": 3.3},
    "M5X0.8": {"label": "M5x0.8", "nominal_mm": 5.0, "pitch_mm": 0.8, "tap_drill_mm": 4.2},
    "M6X1.0": {"label": "M6x1.0", "nominal_mm": 6.0, "pitch_mm": 1.0, "tap_drill_mm": 5.0},
    "M8X1.25": {"label": "M8x1.25", "nominal_mm": 8.0, "pitch_mm": 1.25, "tap_drill_mm": 6.8},
    "M10X1.5": {"label": "M10x1.5", "nominal_mm": 10.0, "pitch_mm": 1.5, "tap_drill_mm": 8.5},
    "M12X1.75": {"label": "M12x1.75", "nominal_mm": 12.0, "pitch_mm": 1.75, "tap_drill_mm": 10.2},
}

THREAD_ALIASES = {
    "M3": "M3X0.5",
    "M4": "M4X0.7",
    "M5": "M5X0.8",
    "M6": "M6X1.0",
    "M8": "M8X1.25",
    "M10": "M10X1.5",
    "M12": "M12X1.75",
}

FACE_CONFIGS = {
    "front": {"base_plane": "Front Plane", "axis": 2, "plane_axes": (0, 1)},
    "top": {"base_plane": "Top Plane", "axis": 1, "plane_axes": (0, 2)},
    "right": {"base_plane": "Right Plane", "axis": 0, "plane_axes": (1, 2)},
}


@dataclass
class ThreadedHoleParams:
    'Threaded-hole sample parameters, all in millimeters.'

    thread_label: str
    block_length_mm: float
    block_width_mm: float
    block_thickness_mm: float
    hole_x_mm: float
    hole_y_mm: float
    nominal_diameter_mm: float
    pitch_mm: float
    tap_drill_diameter_mm: float
    pilot_depth_mm: float
    thread_depth_mm: float
    mouth_chamfer_mm: float
    through_hole: bool
    hole_face: str
    thread_class: str
    right_handed: bool
    visible_thread_mode: str


def normalize_thread_key(value: str) -> str:
    'Normalize forms such as M6, M6x1 and M6x1.0 to table keys.'
    raw = value.strip().upper().replace(" ", "").replace("*", "X")
    if raw in THREAD_ALIASES:
        return THREAD_ALIASES[raw]
    if "X" not in raw:
        raise ValueError(f"Desteklenmeyen diş ölçüsü / Unsupported thread size: {value}")
    major, pitch = raw.split("X", 1)
    try:
        pitch_value = float(pitch)
    except ValueError as exc:
        raise ValueError(f"Geçersiz diş adımı / Invalid pitch format: {value}") from exc
    key = f"{major}X{pitch_value:g}"
    for known in THREAD_TABLE:
        known_major, known_pitch = known.split("X", 1)
        if known_major == major and abs(float(known_pitch) - pitch_value) < 1e-9:
            return known
    raise ValueError(f"Desteklenmeyen diş ölçüsü / Unsupported thread size: {value}; seçenekler / options: {', '.join(sorted(THREAD_ALIASES))}")


def resolve_thread_spec(value: str, tap_drill_override: float | None = None) -> dict:
    'Parse ISO metric threads; out-of-table sizes require an explicit tap-drill diameter.'
    try:
        key = normalize_thread_key(value)
    except ValueError:
        raw = value.strip().upper().replace(" ", "").replace("*", "X")
        match = re.fullmatch(r"M(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)", raw)
        if match is None or tap_drill_override is None:
            raise
        nominal = float(match.group(1))
        pitch = float(match.group(2))
        return {
            "label": f"M{nominal:g}x{pitch:g}",
            "nominal_mm": nominal,
            "pitch_mm": pitch,
            "tap_drill_mm": float(tap_drill_override),
            "source": "user-specified",
        }
    spec = dict(THREAD_TABLE[key])
    if tap_drill_override is not None:
        spec["tap_drill_mm"] = float(tap_drill_override)
        spec["source"] = "user-override"
    else:
        spec["source"] = "verified-table"
    return spec


def finite_number(name: str, value: float) -> float:
    'Validate a finite number.'
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} sonlu sayı olmalıdır / must be finite")
    return number


def positive_number(name: str, value: float) -> float:
    'Validate a finite positive number.'
    number = finite_number(name, value)
    if number <= 0.0:
        raise ValueError(f"{name} 0'dan büyük olmalıdır / must be above 0")
    return number


def validate_basename(value: str) -> str:
    'Prevent output filenames from escaping the requested directory.'
    name = str(value).strip()
    if not name or name in {".", ".."} or Path(name).name != name or any(char in name for char in '<>:"/\\|?*'):
        raise ValueError('basename yol veya geçersiz Windows karakteri içeremez / basename must be a filename without paths or invalid Windows characters')
    return name


def face_config(face_name: str) -> dict:
    'Get coordinate configuration for the drilling face.'
    key = face_name.strip().lower()
    if key not in FACE_CONFIGS:
        raise ValueError(f"Desteklenmeyen delme yüzeyi / Unsupported drilling face: {face_name}; seçenekler / options: top/front/right")
    return FACE_CONFIGS[key]


def assert_feature(feature, label: str):
    'Check a SolidWorks feature object.'
    if feature is None:
        raise RuntimeError(f"{label} oluşturulamadı / creation failed")
    print(f"OK {label}: {getattr(feature, 'Name', '<Adsız / Unnamed>')}")
    return feature


def clear(model) -> None:
    'Clear the selection set.'
    model.ClearSelection2(True)


def hide_reference_planes(model) -> None:
    'Hide reference planes before preview export to keep construction geometry out of delivery images.'
    clear(model)
    try:
        if bool(get_com_member(model, "GetVisibilityOfConstructPlanes")):
            get_com_member(model, "ViewDispRefplanes")
    except Exception as exc:
        print(f"WARN Referans düzlemleri gizlenemedi / Could not hide reference planes: {exc}")
    clear(model)


def hide_visible_thread_sketch(model, params: ThreadedHoleParams) -> bool:
    'Hide the evidence helix sketch so lines through solids do not obscure standard previews.'
    name = f"Sketch_{params.thread_label}_Visible_Internal_Thread_Helix"
    clear(model)
    feature = model.FeatureByName(name)
    if feature is None or not bool(feature.Select2(False, 0)):
        clear(model)
        return False
    get_com_member(model, "BlankSketch")
    clear(model)
    return True


def select_plane(model, plane_name: str) -> str:
    'Select reference planes using localized aliases.'
    clear(model)
    aliases = {
        "Front Plane": ("Front Plane", "Ön Düzlem", "\u524d\u89c6\u57fa\u51c6\u9762"),
        "Top Plane": ("Top Plane", "Üst Düzlem", "\u4e0a\u89c6\u57fa\u51c6\u9762"),
        "Right Plane": ("Right Plane", "Sağ Düzlem", "\u53f3\u89c6\u57fa\u51c6\u9762"),
    }[plane_name]
    for name in aliases:
        selected = model.Extension.SelectByID2(
            name,
            "PLANE",
            0,
            0,
            0,
            False,
            0,
            create_empty_dispatch_variant(),
            0,
        )
        if selected:
            return name
    raise RuntimeError(f"Referans düzlemi seçilemiyor / Cannot select reference plane: {plane_name}")


def current_sketch_name(model, fallback: str) -> str:
    'Get the current sketch name.'
    active = model.SketchManager.ActiveSketch
    return active.Name if active else fallback


def create_offset_plane(model, name: str, base_plane: str, offset_mm: float) -> str:
    'Create an offset reference plane for the drilling start.'
    if model.FeatureByName(name):
        return name
    select_plane(model, base_plane)
    feature = assert_feature(model.FeatureManager.InsertRefPlane(8, mm(offset_mm), 0, 0, 0, 0), name)
    feature.Name = name
    return name


def select_sketch(model, name: str) -> None:
    'Select the specified sketch.'
    clear(model)
    selected = model.Extension.SelectByID2(
        name,
        "SKETCH",
        0,
        0,
        0,
        False,
        0,
        create_empty_dispatch_variant(),
        0,
    )
    if not selected:
        raise RuntimeError(f"Eskiz seçilemiyor / Cannot select sketch: {name}")


def cut_hole_from_sketch(model, sketch_name: str, depth_mm: float, label: str, through: bool = False):
    'Create a blind-depth or Through All cut from the sketch.'
    select_sketch(model, sketch_name)
    end_condition = SW_END_COND_THROUGH_ALL if through else SW_END_COND_BLIND
    feature = model.FeatureManager.FeatureCut4(
        True, False, False, end_condition, SW_END_COND_BLIND, mm(depth_mm), 0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0, False, False,
    )
    return assert_feature(feature, label)


def circle_center_radius(edge):
    'Read circular-edge center and radius.'
    try:
        curve = get_com_member(edge, "GetCurve")
        if not curve or not get_com_member(curve, "IsCircle"):
            return None
        values = get_com_member(curve, "CircleParams")
        return (float(values[0]), float(values[1]), float(values[2])), float(values[6])
    except Exception:
        return None


def all_edges(model):
    'Enumerate all body edges.'
    model.ForceRebuild3(False)
    edges = []
    for body in get_com_member(model, "GetBodies2", SW_SOLID_BODY, False) or []:
        edges.extend(list(get_com_member(body, "GetEdges") or []))
    return edges


def model_point_from_local(params: ThreadedHoleParams, u_m: float, v_m: float, axis_m: float) -> tuple[float, float, float]:
    'Convert local drilling-face coordinates into model XYZ.'
    config = face_config(params.hole_face)
    coords = [0.0, 0.0, 0.0]
    coords[config["plane_axes"][0]] = u_m
    coords[config["plane_axes"][1]] = v_m
    coords[config["axis"]] = axis_m
    return tuple(coords)


def locate_hole_mouth_edge(model, params: ThreadedHoleParams, select: bool = True):
    'Locate the hole-mouth circular edge and center on the drilling start face.'
    config = face_config(params.hole_face)
    axis_index = config["axis"]
    u_index, v_index = config["plane_axes"]
    face_offset = mm(params.block_thickness_mm)
    target_radius = mm(params.tap_drill_diameter_mm / 2.0)
    if select:
        clear(model)
    for edge in all_edges(model):
        data = circle_center_radius(edge)
        if not data:
            continue
        center, radius = data
        center_matches = (
            abs(center[u_index] - mm(params.hole_x_mm)) < mm(0.2)
            and abs(center[v_index] - mm(params.hole_y_mm)) < mm(0.2)
            and abs(abs(center[axis_index]) - face_offset) < mm(0.5)
        )
        radius_matches = abs(radius - target_radius) < mm(0.3)
        if center_matches and radius_matches:
            if not select or edge.Select2(False, 0):
                return edge, center
    raise RuntimeError('Delme başlangıç yüzeyinde delik ağzı dairesel kenarı bulunamadı / Hole-mouth circular edge not found on drilling start face')


def select_hole_mouth_edge(model, params: ThreadedHoleParams):
    'Select the hole-mouth circular edge on the drilling start face.'
    edge, _center = locate_hole_mouth_edge(model, params, select=True)
    return edge


def add_hole_mouth_chamfer(model, params: ThreadedHoleParams):
    'Add a small 45-degree mouth chamfer.'
    select_hole_mouth_edge(model, params)
    feature = model.FeatureManager.InsertFeatureChamfer(
        4, 1, mm(params.mouth_chamfer_mm), math.pi / 4.0, 0, 0, 0, 0
    )
    assert_feature(feature, 'Delik ağzı pahı / Mouth chamfer').Name = "Chamfer_Thread_Mouth"
    clear(model)
    return feature


def add_real_thread_feature(model, params: ThreadedHoleParams):
    'Attempt a real SolidWorks Thread feature.'
    edge, _center = locate_hole_mouth_edge(model, params, select=False)
    thread_data = model.FeatureManager.CreateDefinition(SW_FM_SWEEP_THREAD)
    if thread_data is None:
        raise RuntimeError('CreateDefinition(swFmSweepThread) None döndürdü / returned None')

    try:
        thread_data.InitializeThreadData()
    except Exception as exc:
        print(f"WARN InitializeThreadData atlandı / skipped: {exc}")

    clear(model)
    if not edge.Select2(False, 1):
        raise RuntimeError('Delik ağzı kenarı seçilemedi; ThreadFeatureData seçim işareti 1 gerektirir / Hole-mouth edge selection failed; mark 1 is required')

    end_condition = SW_THREAD_END_REVOLUTIONS if params.through_hole else SW_THREAD_END_BLIND
    end_value = (
        ("Revolutions", params.thread_depth_mm / params.pitch_mm)
        if params.through_hole
        else ("BlindDepth", mm(params.thread_depth_mm))
    )
    for attr, value in (
        ("Edge", edge),
        ("Type", "Metric Tap"),
        ("ThreadMethod", SW_THREAD_METHOD_CUT),
        ("EndCondition", end_condition),
        end_value,
        ("Pitch", mm(params.pitch_mm)),
        ("Size", params.thread_label),
        ("PitchOverride", True),
        ("DiameterOverride", False),
        ("RightHanded", params.right_handed),
    ):
        try:
            setattr(thread_data, attr, value)
            print(f"  {attr}={value}")
        except Exception as exc:
            print(f"WARN Ayarlanamadı / Could not set {attr}; hata / failed: {exc}")

    feature = model.FeatureManager.CreateFeature(thread_data)
    if feature is None:
        raise RuntimeError('CreateFeature(ThreadFeatureData) None döndürdü / returned None')
    end_label = "Through" if params.through_hole else "Blind"
    hand_label = "RH" if params.right_handed else "LH"
    feature.Name = f"Thread_{params.thread_label}_Internal_{end_label}_{hand_label}"
    return assert_feature(feature, f"{params.thread_label} gerçek iç diş / real internal thread")


def add_cosmetic_thread_feature(model, params: ThreadedHoleParams):
    'Add a SolidWorks Cosmetic Thread representation.'
    edge = select_hole_mouth_edge(model, params)
    clear(model)
    if not edge.Select2(False, 0):
        raise RuntimeError('Delik ağzı kenarı seçilemedi; Cosmetic Thread oluşturulamıyor / Hole-mouth edge selection failed; cannot create Cosmetic Thread')
    end_condition = SW_COSMETIC_END_THROUGH if params.through_hole else SW_COSMETIC_END_BLIND
    hand_note = "RH" if params.right_handed else "LH"
    feature = model.FeatureManager.InsertCosmeticThread3(
        SW_COSMETIC_STANDARD_ISO,
        "Tapped Hole",
        params.thread_label,
        mm(params.nominal_diameter_mm),
        end_condition,
        mm(params.thread_depth_mm),
        f"{params.thread_label} - {params.thread_class} {hand_note}",
    )
    if feature is None:
        raise RuntimeError('InsertCosmeticThread3 None döndürdü / returned None')
    end_label = "Through" if params.through_hole else "Blind"
    feature.Name = f"CosmeticThread_{params.thread_label}_Internal_{end_label}_{hand_note}"
    clear(model)
    return assert_feature(feature, f"{params.thread_label} kozmetik diş / cosmetic thread")


def visible_helix_plan(params: ThreadedHoleParams) -> dict:
    'Return a helix sampling plan preserving pitch within the hole bottom/exit.'
    start_offset_mm = min(0.3, params.thread_depth_mm * 0.1)
    maximum_depth_mm = params.block_thickness_mm if params.through_hole else params.pilot_depth_mm
    end_depth_mm = min(params.thread_depth_mm, maximum_depth_mm)
    axial_depth_mm = end_depth_mm - start_offset_mm
    if axial_depth_mm <= 0.0:
        raise ValueError('Görünür helisin etkin eksenel derinliği pozitif olmalıdır / Visible helix effective axial depth must be positive')
    turns = axial_depth_mm / params.pitch_mm
    segment_count = max(32, int(math.ceil(turns * 32.0)))
    return {
        "start_offset_mm": start_offset_mm,
        "axial_depth_mm": axial_depth_mm,
        "turns": turns,
        "segment_count": segment_count,
    }


def add_visible_thread_helix(model, params: ThreadedHoleParams) -> int:
    'Create a visible internal-thread helix using short 3D sketch segments.'
    _edge, mouth_center = locate_hole_mouth_edge(model, params, select=False)
    config = face_config(params.hole_face)
    axis_index = config["axis"]
    mouth_axis = mouth_center[axis_index]
    inward_sign = -1.0 if mouth_axis >= 0 else 1.0
    plan = visible_helix_plan(params)
    turns = plan["turns"]
    segment_count = plan["segment_count"]
    radius = mm(max(params.tap_drill_diameter_mm / 2.0 + 0.15, params.nominal_diameter_mm / 2.0 - 0.08))
    start_offset = mm(plan["start_offset_mm"])
    z_depth = mm(plan["axial_depth_mm"])
    winding_sign = 1.0 if params.right_handed else -1.0

    sketch_mgr = model.SketchManager
    sketch_mgr.Insert3DSketch(True)
    sketch_name = current_sketch_name(model, f"Sketch_{params.thread_label}_Visible_Thread_Helix")
    previous = None
    created = 0
    for index in range(segment_count + 1):
        angle = winding_sign * 2.0 * math.pi * turns * index / segment_count
        axis_value = mouth_axis + inward_sign * (start_offset + z_depth * index / segment_count)
        point = model_point_from_local(
            params,
            mm(params.hole_x_mm) + radius * math.cos(angle),
            mm(params.hole_y_mm) + radius * math.sin(angle),
            axis_value,
        )
        if previous is not None:
            segment = sketch_mgr.CreateLine(
                previous[0],
                previous[1],
                previous[2],
                point[0],
                point[1],
                point[2],
            )
            if segment:
                created += 1
        previous = point
    sketch_mgr.Insert3DSketch(True)

    feature = model.FeatureByName(sketch_name)
    if feature:
        feature.Name = f"Sketch_{params.thread_label}_Visible_Internal_Thread_Helix"
    print(f"OK Görünür diş helisi / Visible thread helix: {created} segment, {turns:.3f} tur / turns")
    return created


def write_thread_properties(model, params: ThreadedHoleParams, thread_status: str, visible_segments: int) -> None:
    'Write model custom properties.'
    manager = model.Extension.CustomPropertyManager("")
    manager.Add3('Diş ölçüsü / Thread size', 30, f"{params.thread_label} internal thread", 2)
    manager.Add3('Kılavuz ön deliği / Tap-drill diameter', 30, f"{params.tap_drill_diameter_mm} mm", 2)
    manager.Add3('Diş derinliği / Thread depth', 30, f"{params.thread_depth_mm} mm", 2)
    manager.Add3('Ön delik derinliği / Tap-drill depth', 30, f"{params.pilot_depth_mm} mm", 2)
    manager.Add3('Diş tolerans sınıfı / Thread tolerance class', 30, params.thread_class, 2)
    manager.Add3('Diş yönü / Thread hand', 30, "RH" if params.right_handed else "LH", 2)
    manager.Add3('Delik bitiş koşulu / Hole end condition', 30, "through" if params.through_hole else "blind", 2)
    manager.Add3('Diş durumu / Thread status', 30, thread_status, 2)
    manager.Add3('Görünür diş helisi / Visible thread helix', 30, f"{visible_segments} segments", 2)
    manager.Add3('Diş modelleme notu / Thread modeling note', 30, 'Ön delik ve ağız pahı gerçek geometridir; Thread/CosmeticThread başarısız olursa özellikler ve 3D helis kullanılır / Tap-drill and mouth chamfer are real geometry; failed Thread/CosmeticThread uses properties and a 3D helix.', 2)


def build_params(args) -> ThreadedHoleParams:
    'Build threaded-hole parameters from CLI arguments.'
    block_length = positive_number("block_length", args.block_length)
    block_width = positive_number("block_width", args.block_width)
    block_thickness = positive_number("block_thickness", args.block_thickness)
    hole_x = finite_number("hole_x", args.hole_x)
    hole_y = finite_number("hole_y", args.hole_y)
    mouth_chamfer = positive_number("mouth_chamfer", args.mouth_chamfer)
    tap_drill_override = None if args.tap_drill is None else positive_number("tap_drill", args.tap_drill)
    spec = resolve_thread_spec(args.thread, tap_drill_override)
    nominal = positive_number("nominal_diameter", spec["nominal_mm"])
    pitch = positive_number("pitch", spec["pitch_mm"])
    tap_drill = positive_number("tap_drill", spec["tap_drill_mm"])
    if tap_drill >= nominal:
        raise ValueError('Kılavuz ön deliği diş anma çapından küçük olmalıdır / Tap-drill diameter must be below nominal thread diameter')

    thread_depth = args.thread_depth
    if thread_depth is None:
        thread_depth = block_thickness if args.through else min(nominal * 2.0, block_thickness - 4.0)
    thread_depth = positive_number("thread_depth", thread_depth)
    pilot_depth = args.pilot_depth
    if args.through:
        if pilot_depth is not None and not math.isclose(float(pilot_depth), block_thickness, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError('Geçiş deliği pilot_depth değeri parça kalınlığıdır; --pilot-depth seçeneğini kaldırın / Through-hole pilot_depth follows part thickness; remove --pilot-depth')
        pilot_depth = block_thickness
        if thread_depth > block_thickness:
            raise ValueError('Geçiş deliği diş derinliği parça kalınlığını aşamaz / Through-thread depth cannot exceed part thickness')
    else:
        if pilot_depth is None:
            pilot_depth = min(thread_depth + max(pitch, 1.0), block_thickness - 1.0)
        pilot_depth = positive_number("pilot_depth", pilot_depth)
        if pilot_depth >= block_thickness:
            raise ValueError('Kör ön delik derinliği parça kalınlığından küçük olmalıdır; geçiş için --through kullanın / Blind pilot depth must be below thickness; use --through for a through hole')
        if thread_depth > pilot_depth:
            raise ValueError('Diş derinliği ön delik derinliğini aşamaz / Thread depth cannot exceed tap-drill depth')

    required_radius = max(nominal / 2.0, tap_drill / 2.0 + mouth_chamfer)
    if abs(hole_x) + required_radius >= block_length / 2.0:
        raise ValueError('Delik X konumu kullanılabilir sınır dışında; anma çapı/pah payı yok / Hole X exceeds usable bounds without major-diameter/chamfer allowance')
    if abs(hole_y) + required_radius >= block_width / 2.0:
        raise ValueError('Delik Y konumu kullanılabilir sınır dışında; anma çapı/pah payı yok / Hole Y exceeds usable bounds without major-diameter/chamfer allowance')

    hole_face = args.hole_face.strip().lower()
    face_config(hole_face)
    thread_class = str(getattr(args, "thread_class", "6H")).strip()
    if not thread_class:
        raise ValueError('thread_class boş olamaz / thread_class cannot be empty')
    handedness = str(getattr(args, "handedness", "right")).strip().lower()
    if handedness not in {"right", "left"}:
        raise ValueError('handedness right veya left olmalıdır / handedness must be right or left')
    visible_thread_mode = str(getattr(args, "visible_thread", "fallback")).strip().lower()
    if visible_thread_mode not in {"fallback", "always", "never"}:
        raise ValueError('visible_thread fallback, always veya never olmalıdır / visible_thread must be fallback, always or never')
    return ThreadedHoleParams(
        thread_label=spec["label"],
        block_length_mm=block_length,
        block_width_mm=block_width,
        block_thickness_mm=block_thickness,
        hole_x_mm=hole_x,
        hole_y_mm=hole_y,
        nominal_diameter_mm=nominal,
        pitch_mm=pitch,
        tap_drill_diameter_mm=tap_drill,
        pilot_depth_mm=pilot_depth,
        thread_depth_mm=thread_depth,
        mouth_chamfer_mm=mouth_chamfer,
        through_hole=bool(args.through),
        hole_face=hole_face,
        thread_class=thread_class,
        right_handed=handedness == "right",
        visible_thread_mode=visible_thread_mode,
    )


def collect_thread_feature_evidence(model, params: ThreadedHoleParams, visible_segments: int) -> dict:
    'Read the feature tree after rebuild; a COM object is not persistence evidence.'
    features = []
    guard = 0

    def traverse(feature, next_member: str, parent: str | None = None) -> None:
        'Traverse sibling features and subfeatures; CosmeticThread usually belongs to the cut.'
        nonlocal guard
        while feature is not None and guard < 10000:
            name = str(get_com_member(feature, "Name") or "")
            item = {
                "name": name,
                "type": str(get_com_member(feature, "GetTypeName2") or ""),
            }
            if parent:
                item["parent"] = parent
            features.append(item)
            guard += 1
            subfeature = get_com_member(feature, "GetFirstSubFeature")
            if subfeature is not None:
                traverse(subfeature, "GetNextSubFeature", parent=name)
            feature = get_com_member(feature, next_member)

    traverse(get_com_member(model, "FirstFeature"), "GetNextFeature")
    names = [item["name"] for item in features]
    has_real = any(name.startswith(f"Thread_{params.thread_label}_Internal_") for name in names)
    has_cosmetic = any(name.startswith(f"CosmeticThread_{params.thread_label}_Internal_") for name in names)
    has_visible = visible_segments > 0 and any("Visible_Internal_Thread_Helix" in name for name in names)
    representation = "real-thread" if has_real else "cosmetic-thread" if has_cosmetic else "visible-helix" if has_visible else "metadata-only"
    return {
        "representation": representation,
        "has_tap_drill_cut": f"Cut_{params.thread_label}_Tap_Drill" in names,
        "has_mouth_chamfer": "Chamfer_Thread_Mouth" in names,
        "has_real_thread": has_real,
        "has_cosmetic_thread": has_cosmetic,
        "has_visible_helix": has_visible,
        "features": features,
    }


def require_thread_representation(evidence: dict) -> str:
    'Require a real thread, cosmetic thread or evidence helix after rebuild.'
    representation = str(evidence.get("representation") or "metadata-only")
    if representation == "metadata-only":
        raise RuntimeError(
            'Yeniden oluşturmadan sonra Thread, CosmeticThread veya görünür helis bulunamadı / No Thread, CosmeticThread or visible helix after rebuild; '
            'yalnızca özel özellikler doğrulanmış teslim sayılamaz / custom properties alone cannot establish verified delivery'
        )
    return f"{representation}-verified"


def create_threaded_hole_block(params: ThreadedHoleParams, output_dir: Path, basename: str):
    'Create the threaded-hole sample, save, export and review.'
    basename = validate_basename(basename)
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / f"{basename}.SLDPRT"
    step_path = output_dir / f"{basename}.step"
    param_path = output_dir / f"{basename}_parameters.json"

    session = SolidWorksSession(visible=True)
    try:
        session.close(title=part_path.name)
    except Exception:
        pass
    model = session.new_part()
    config = face_config(params.hole_face)

    with sketch(model, config["base_plane"]) as base_sketch:
        sketch_rectangle(model, 0, 0, mm(params.block_length_mm), mm(params.block_width_mm))
    base_feature = extrude_boss(model, base_sketch, mm(params.block_thickness_mm), direction=False)
    assert_feature(base_feature, 'Taban / Base').Name = "Boss_Thread_Test_Block"

    top_plane = create_offset_plane(model, "Plane_Hole_Start", config["base_plane"], params.block_thickness_mm)
    clear(model)
    model.Extension.SelectByID2(top_plane, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
    model.SketchManager.InsertSketch(True)
    hole_sketch = current_sketch_name(model, "Sketch_Tap_Drill_Hole")
    model.SketchManager.CreateCircleByRadius(
        mm(params.hole_x_mm),
        mm(params.hole_y_mm),
        0,
        mm(params.tap_drill_diameter_mm / 2.0),
    )
    model.SketchManager.InsertSketch(True)
    cut_feature = cut_hole_from_sketch(
        model,
        hole_sketch,
        params.pilot_depth_mm,
        f"{params.thread_label} kılavuz ön deliği / tap-drill {params.tap_drill_diameter_mm}mm",
        through=params.through_hole,
    )
    cut_feature.Name = f"Cut_{params.thread_label}_Tap_Drill"

    thread_attempts = []
    try:
        add_real_thread_feature(model, params)
        thread_attempts.append({"method": "ThreadFeatureData", "result": "created"})
    except Exception as exc:
        thread_attempts.append({"method": "ThreadFeatureData", "result": "failed", "error": str(exc)})
        print(f"WARN Gerçek Thread başarısız; Cosmetic Thread deneniyor / Real Thread failed; trying Cosmetic Thread: {exc}")
        try:
            add_cosmetic_thread_feature(model, params)
            thread_attempts.append({"method": "CosmeticThread", "result": "created"})
        except Exception as cosmetic_exc:
            thread_attempts.append({"method": "CosmeticThread", "result": "failed", "error": str(cosmetic_exc)})
            print(f"WARN Cosmetic Thread başarısız; özellik ve görünür helis kullanılıyor / Cosmetic Thread failed; falling back to properties and visible helix: {cosmetic_exc}")

    model.ForceRebuild3(False)
    preliminary_evidence = collect_thread_feature_evidence(model, params, visible_segments=0)
    should_add_visible = params.visible_thread_mode == "always" or (
        params.visible_thread_mode == "fallback"
        and preliminary_evidence["representation"] == "metadata-only"
    )
    visible_segments = add_visible_thread_helix(model, params) if should_add_visible else 0
    add_hole_mouth_chamfer(model, params)

    set_document_appearance(model, "silver")
    model.ForceRebuild3(False)
    thread_evidence = collect_thread_feature_evidence(model, params, visible_segments)
    if not thread_evidence["has_tap_drill_cut"] or not thread_evidence["has_mouth_chamfer"]:
        raise RuntimeError('Rebuild sonrasında ön delik kesimi veya ağız pahı yok; teslim durduruldu / Tap-drill cut or mouth chamfer missing after rebuild; delivery stopped')
    thread_status = require_thread_representation(thread_evidence)
    write_thread_properties(model, params, thread_status, visible_segments)
    hide_reference_planes(model)
    model.ViewZoomtofit2()

    thread_evidence_preview_path = None
    if visible_segments > 0:
        thread_evidence_preview_path = output_dir / f"{basename}_thread_evidence.bmp"
        save_preview(model, thread_evidence_preview_path, "isometric")
        if not hide_visible_thread_sketch(model, params):
            print('WARN Görünür helis gizlenemedi; standart önizlemede katı içinden eskiz çizgileri görünebilir / Helix hiding failed; sketch lines may show through solids')

    param_path.write_text(
        json.dumps(
            {
                "units": "mm",
                "params": asdict(params),
                "thread_status": thread_status,
                "thread_attempts": thread_attempts,
                "thread_evidence": thread_evidence,
                "thread_evidence_preview": str(thread_evidence_preview_path) if thread_evidence_preview_path else None,
                "visible_thread_helix_segments": visible_segments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not session.save(model, str(part_path)):
        raise RuntimeError(f"Kaydetme başarısız / Save failed: {part_path}")
    if not export_to_step(model, str(step_path)):
        raise RuntimeError(f"STEP dışa aktarma başarısız / STEP export failed: {step_path}")

    expected_outputs = [str(part_path), str(step_path), str(param_path)]
    if thread_evidence_preview_path is not None:
        expected_outputs.append(str(thread_evidence_preview_path))
    report, report_path = run_review(
        model,
        output_dir,
        basename=basename,
        expected_outputs=expected_outputs,
    )
    print(f"İnceleme raporu / Review report: {report_path}")
    print(f"İnceleme durumu / Review status: {report['evaluation']['status']} / {report['evaluation']['score']}")
    print(f"Diş durumu / Thread status: {thread_status}")
    return {
        "part_path": str(part_path),
        "step_path": str(step_path),
        "param_path": str(param_path),
        "review_path": str(report_path),
        "review": report["evaluation"],
        "thread_status": thread_status,
        "thread_evidence_preview": str(thread_evidence_preview_path) if thread_evidence_preview_path else None,
    }


def parse_args():
    'Parse CLI arguments.'
    parser = argparse.ArgumentParser(description='SolidWorks iç dişli delik örneği oluşturur / Generate a SolidWorks internal-thread hole sample.')
    parser.add_argument("--thread", default="M6", help='Diş ölçüsü, varsayılan M6; M3/M4/M5/M6/M8/M10/M12 veya M6x1.0 / Thread size.')
    parser.add_argument("--block-length", type=float, default=40.0, help='Taban uzunluğu mm / Base length mm.')
    parser.add_argument("--block-width", type=float, default=30.0, help='Taban genişliği mm / Base width mm.')
    parser.add_argument("--block-thickness", type=float, default=16.0, help='Taban kalınlığı mm / Base thickness mm.')
    parser.add_argument("--hole-x", type=float, default=0.0, help='Delik merkezi X, mm / Hole-center X, mm.')
    parser.add_argument("--hole-y", type=float, default=0.0, help='Delik merkezi Y, mm / Hole-center Y, mm.')
    parser.add_argument("--tap-drill", type=float, help='Varsayılan kılavuz ön delik çapını değiştir, mm / Override tap-drill diameter, mm.')
    parser.add_argument("--pilot-depth", type=float, help='Ön delik derinliği mm; belirtilmezse diş derinliği ve kalınlıktan tahmin edilir / Pilot depth, estimated if omitted.')
    parser.add_argument("--thread-depth", type=float, help='Diş derinliği mm; varsayılan yaklaşık 2D / Thread depth, default approximately 2D.')
    parser.add_argument("--mouth-chamfer", type=float, default=0.6, help='45 derece ağız pahı mesafesi, mm / 45-degree mouth chamfer distance, mm.')
    parser.add_argument("--through", action="store_true", help='Ön delik ve kozmetik diş için tam geçiş kullan / Use Through All tap-drill and through cosmetic thread.')
    parser.add_argument("--hole-face", choices=sorted(FACE_CONFIGS), default="top", help='Delme yüzeyi: top (varsayılan), front veya right / Drilling face.')
    parser.add_argument("--thread-class", default="6H", help='İç diş tolerans sınıfı, varsayılan 6H / Internal-thread tolerance class.')
    parser.add_argument("--handedness", choices=("right", "left"), default="right", help='Diş yönü, varsayılan sağ / Thread hand, default right.')
    parser.add_argument(
        "--visible-thread",
        choices=("fallback", "always", "never"),
        default="fallback",
        help='3D helis politikası: fallback yalnızca Thread/CosmeticThread kalıcı değilse oluşturur / Helix fallback requires missing persistent thread features.',
    )
    parser.add_argument("--basename", help='Çıktı dosya öneki; yoksa diş ölçüsünden üretilir / Output prefix, generated from thread size if omitted.')
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "solidworks_threaded_hole_output",
        help='Çıktı dizini / Output directory.',
    )
    return parser.parse_args()


def main() -> int:
    'Command-line entry point.'
    args = parse_args()
    params = build_params(args)
    basename = validate_basename(args.basename or f"{params.thread_label.replace('.', '_')}_Internal_Threaded_Hole_Block")
    result = create_threaded_hole_block(params, args.output_dir, basename)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
