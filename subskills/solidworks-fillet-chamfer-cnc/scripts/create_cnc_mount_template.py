'SolidWorks CNC mounting-base template with multiple fillets/chamfers. Creates parametric geometry with bounded fallback and topology evidence. --dry-run performs parameter/DFM checks without connecting to SolidWorks.'

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from cnc_strategy import (  # noqa: E402
    MountParameters,
    build_operation_plan,
    build_parameters,
    load_parameter_file,
    parameter_positions,
    parse_set_values,
    plan_payload,
    validate_basename,
)
from sw_appearance import set_document_appearance  # noqa: E402
from sw_connect import create_empty_dispatch_variant, get_com_member, mm  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_part import sketch_slot  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


SW_SOLID_BODY = 0
SELECTION_TOLERANCE_MM = 0.05
EdgePredicate = Callable[[Any], bool]


def assert_feature(feature, label: str):
    'Check that a feature was created.'
    if feature is None:
        raise RuntimeError(f"{label} oluşturulamadı / creation failed")
    print(f"OK: {label} -> {getattr(feature, 'Name', '<unnamed>')}")
    return feature


def clear(model) -> None:
    'Clear the selection set.'
    model.ClearSelection2(True)


def hide_reference_planes(model) -> None:
    'Hide construction planes before review to keep names/orange borders out of previews.'
    clear(model)
    try:
        if bool(get_com_member(model, "GetVisibilityOfConstructPlanes")):
            get_com_member(model, "ViewDispRefplanes")
    except Exception as exc:
        print(f"WARN Referans düzlemleri gizlenemedi / Could not hide reference planes: {exc}")
    clear(model)


def select_plane(model, aliases: tuple[str, ...]) -> None:
    'Select a reference plane using supported localized aliases.'
    clear(model)
    for name in aliases:
        selected = model.Extension.SelectByID2(
            name, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
        )
        if selected:
            return
    raise RuntimeError(f"Referans düzlemi seçilemiyor / Cannot select reference plane: {aliases}")


def current_sketch_name(model, fallback: str) -> str:
    'Read the active sketch name.'
    active = model.SketchManager.ActiveSketch
    return active.Name if active else fallback


def offset_front_plane(model, name: str, z_mm: float) -> str:
    'Create an offset plane parallel to the front plane.'
    if model.FeatureByName(name):
        return name
    select_plane(model, ("Front Plane", "Ön Düzlem", "\u524d\u89c6\u57fa\u51c6\u9762"))
    plane = assert_feature(
        model.FeatureManager.InsertRefPlane(8, mm(z_mm), 0, 0, 0, 0), name
    )
    plane.Name = name
    return name


def select_sketch(model, name: str) -> None:
    'Select a sketch by name.'
    clear(model)
    selected = model.Extension.SelectByID2(
        name, "SKETCH", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
    )
    if not selected:
        raise RuntimeError(f"Eskiz seçilemiyor / Cannot select sketch: {name}")


def extrude_boss(model, name: str, depth_mm: float, label: str):
    'Create and name a boss extrusion.'
    select_sketch(model, name)
    feature = assert_feature(
        model.FeatureManager.FeatureExtrusion3(
            True, False, False, 0, 0, mm(depth_mm), 0,
            False, False, False, False, 0, 0,
            False, False, False, False,
            True, False, True, 0, 0, False,
        ),
        label,
    )
    feature.Name = label
    return feature


def cut(
    model,
    name: str,
    depth_mm: float,
    label: str,
    *,
    through_all: bool = False,
    total_depth_mm: float,
):
    'Create and name an extruded cut.'
    select_sketch(model, name)
    end_condition = 1 if through_all else 0
    depth = mm(max(depth_mm, total_depth_mm + 4.0) if through_all else depth_mm)
    feature = assert_feature(
        model.FeatureManager.FeatureCut4(
            True, False, False, end_condition, 0, depth, 0,
            False, False, False, False, 0, 0,
            False, False, False, False, False,
            True, True, True, True,
            False, 0, 0, False, False,
        ),
        label,
    )
    feature.Name = label
    return feature


def edge_points(edge):
    'Read edge endpoints; closed circular edges may have none.'
    try:
        start = get_com_member(edge, "GetStartVertex")
        end = get_com_member(edge, "GetEndVertex")
        if not start or not end:
            return None
        return (
            tuple(float(value) for value in get_com_member(start, "GetPoint")),
            tuple(float(value) for value in get_com_member(end, "GetPoint")),
        )
    except Exception:
        return None


def midpoint(edge):
    'Compute the midpoint of an edge with endpoints.'
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    return tuple((start[index] + end[index]) / 2.0 for index in range(3))


def edge_direction(edge):
    'Determine the dominant axis of a straight edge.'
    try:
        curve = get_com_member(edge, "GetCurve")
        if not curve or not get_com_member(curve, "IsLine"):
            return None
    except Exception:
        return None
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    deltas = [abs(end[index] - start[index]) for index in range(3)]
    if max(deltas) < mm(SELECTION_TOLERANCE_MM):
        return None
    return "xyz"[deltas.index(max(deltas))]


def circle_center_radius(edge):
    'Read the center and radius of a circular edge/arc.'
    try:
        curve = get_com_member(edge, "GetCurve")
        if not curve or not get_com_member(curve, "IsCircle"):
            return None
        values = get_com_member(curve, "CircleParams")
        return (float(values[0]), float(values[1]), float(values[2])), float(values[6])
    except Exception:
        return None


def edge_signature(edge) -> dict[str, Any]:
    'Generate a geometric signature independent of temporary EdgeN names.'
    circle = circle_center_radius(edge)
    points = edge_points(edge)

    def point_mm(point):
        return [round(value * 1000.0, 6) for value in point]

    if circle:
        center, radius = circle
        result: dict[str, Any] = {
            "curve": "circle",
            "center_mm": point_mm(center),
            "radius_mm": round(radius * 1000.0, 6),
        }
        if points:
            result["endpoints_mm"] = [point_mm(points[0]), point_mm(points[1])]
        return result
    if points:
        return {
            "curve": "line" if edge_direction(edge) else "other",
            "endpoints_mm": [point_mm(points[0]), point_mm(points[1])],
        }
    return {"curve": "unknown"}


def all_edges(model):
    'Enumerate edges of all current bodies.'
    model.ForceRebuild3(False)
    edges = []
    for body in get_com_member(model, "GetBodies2", SW_SOLID_BODY, False) or []:
        edges.extend(list(get_com_member(body, "GetEdges") or []))
    return edges


def matching_edges(model, predicate: EdgePredicate) -> list[Any]:
    'Return edge objects matching a geometric predicate.'
    matched = []
    for edge in all_edges(model):
        try:
            if predicate(edge):
                matched.append(edge)
        except Exception:
            continue
    return matched


def select_exact_edges(
    model,
    predicate: EdgePredicate,
    label: str,
    expected_count: int,
) -> tuple[list[Any], list[dict[str, Any]]]:
    'Select an exact semantic edge set; stop rather than guess on a count mismatch.'
    clear(model)
    edges = matching_edges(model, predicate)
    signatures = [edge_signature(edge) for edge in edges]
    if len(edges) != expected_count:
        raise RuntimeError(
            f"{label} anlamsal kenar sayısı uyuşmuyor / semantic edge count mismatch: expected={expected_count}, actual={len(edges)}, "
            f"signatures={json.dumps(signatures, ensure_ascii=False)}"
        )
    for index, edge in enumerate(edges):
        if not edge.Select2(index > 0, 0):
            clear(model)
            raise RuntimeError(f"{label} kenar / edge {index + 1} için Select2 başarısız / Select2 failed")
    print(f"SELECT: {label} -> {len(edges)}")
    return edges, signatures


def planar_outer_loop_predicate(z_mm: float, half_x_mm: float, half_y_mm: float) -> EdgePredicate:
    'Create a closed-loop edge predicate for a given Z plane and outer envelope.'
    z_value = mm(z_mm)
    half_x = mm(half_x_mm)
    half_y = mm(half_y_mm)
    tolerance = mm(SELECTION_TOLERANCE_MM)

    def predicate(edge) -> bool:
        points = edge_points(edge)
        if not points or any(abs(point[2] - z_value) > tolerance for point in points):
            return False
        return any(
            abs(abs(point[0]) - half_x) <= tolerance
            or abs(abs(point[1]) - half_y) <= tolerance
            for point in points
        )

    return predicate


def vertical_corner_predicate(
    z_min_mm: float,
    z_max_mm: float,
    half_x_mm: float,
    half_y_mm: float,
) -> EdgePredicate:
    'Create a predicate for the four vertical corners of a rectangular body.'
    tolerance = mm(SELECTION_TOLERANCE_MM)
    half_x = mm(half_x_mm)
    half_y = mm(half_y_mm)
    z_min = mm(z_min_mm)
    z_max = mm(z_max_mm)

    def predicate(edge) -> bool:
        points = edge_points(edge)
        middle = midpoint(edge)
        if not points or not middle or edge_direction(edge) != "z":
            return False
        zs = sorted((points[0][2], points[1][2]))
        return (
            abs(zs[0] - z_min) <= tolerance
            and abs(zs[1] - z_max) <= tolerance
            and abs(abs(middle[0]) - half_x) <= tolerance
            and abs(abs(middle[1]) - half_y) <= tolerance
        )

    return predicate


def hole_mouth_predicate(params: MountParameters) -> EdgePredicate:
    'Create a predicate for counterbore and dowel-hole entry circular edges.'
    positions = parameter_positions(params)
    targets = [
        *((point, params.counterbore_diameter / 2.0) for point in positions["mount"]),
        *((point, params.dowel_hole_diameter / 2.0) for point in positions["dowel"]),
    ]
    z_top = mm(params.thickness)
    tolerance = mm(SELECTION_TOLERANCE_MM)

    def predicate(edge) -> bool:
        circle = circle_center_radius(edge)
        if not circle:
            return False
        center, radius = circle
        if abs(center[2] - z_top) > tolerance:
            return False
        return any(
            abs(center[0] - mm(point[0])) <= tolerance
            and abs(center[1] - mm(point[1])) <= tolerance
            and abs(radius - mm(expected_radius)) <= tolerance
            for point, expected_radius in targets
        )

    return predicate


def operation_predicate(name: str, params: MountParameters) -> EdgePredicate:
    'Map planned semantic targets to runtime geometric predicates.'
    predicates = {
        "Fillet_Base_Corners": vertical_corner_predicate(
            0.0, params.thickness, params.length / 2.0, params.width / 2.0
        ),
        "Fillet_Boss_Corners": vertical_corner_predicate(
            params.thickness,
            params.thickness + params.boss_height,
            params.boss_length / 2.0,
            params.boss_width / 2.0,
        ),
        "Chamfer_Top_Outer": planar_outer_loop_predicate(
            params.thickness, params.length / 2.0, params.width / 2.0
        ),
        "Chamfer_Bottom_Outer": planar_outer_loop_predicate(
            0.0, params.length / 2.0, params.width / 2.0
        ),
        "Chamfer_Boss_Top": planar_outer_loop_predicate(
            params.thickness + params.boss_height,
            params.boss_length / 2.0,
            params.boss_width / 2.0,
        ),
        "Chamfer_Hole_Mouths": hole_mouth_predicate(params),
    }
    try:
        return predicates[name]
    except KeyError as exc:
        raise ValueError(f"Bilinmeyen radyüs/pah işlemi / Unknown fillet/chamfer operation: {name}") from exc


def apply_treatment(model, operation: dict[str, Any], params: MountParameters) -> dict[str, Any]:
    'Execute planned fillets/chamfers and record every bounded fallback attempt.'
    attempts = []
    predicate = operation_predicate(operation["name"], params)
    for value_mm in operation["attempt_values_mm"]:
        _edges, signatures = select_exact_edges(
            model, predicate, operation["target"], operation["expected_edge_count"]
        )
        try:
            if operation["kind"] == "fillet":
                feature = model.FeatureManager.FeatureFillet(
                    195, mm(value_mm), 0, 0, None, None, None
                )
            else:
                feature = model.FeatureManager.InsertFeatureChamfer(
                    4, 1, mm(value_mm), math.radians(operation["angle_deg"]), 0, 0, 0, 0
                )
        except Exception as exc:
            clear(model)
            raise RuntimeError(
                f"{operation['name']} unsur API çağrısında hata; kısmi unsurların birikmesini önlemek için / feature API raised; to avoid accumulating partial features, "
                'otomatik yeniden deneme yasak / automatic retries prohibited'
            ) from exc
        if feature is None:
            attempts.append(
                {
                    "value_mm": value_mm,
                    "result": "feature_returned_none",
                    "selected_edges": signatures,
                }
            )
            clear(model)
            model.ForceRebuild3(False)
            continue
        try:
            feature.Name = operation["name"]
            clear(model)
            model.ForceRebuild3(False)
            if model.FeatureByName(operation["name"]) is None:
                raise RuntimeError('Unsur döndü ancak yeniden oluşturmadan sonra ağaçta kalmadı / Feature returned but did not persist after rebuild')
        except Exception as exc:
            clear(model)
            raise RuntimeError(
                f"{operation['name']} unsur nesnesi döndü ancak adlandırma veya yeniden oluşturma doğrulaması başarısız / feature returned but naming or rebuild readback failed; "
                'farklı boyutlarla devam etmek yasak / further dimension attempts prohibited'
            ) from exc
        attempts.append(
            {
                "value_mm": value_mm,
                "result": "created_and_persisted",
                "selected_edges": signatures,
            }
        )
        print(f"OK: {operation['name']} -> {value_mm:g} mm")
        return {
            "name": operation["name"],
            "status": "pass" if value_mm == operation["requested_value_mm"] else "degraded",
            "requested_value_mm": operation["requested_value_mm"],
            "actual_value_mm": value_mm,
            "expected_edge_count": operation["expected_edge_count"],
            "attempts": attempts,
        }
    raise RuntimeError(
        f"{operation['name']} sınırlı geri dönüş adımlarının tümü başarısız / all bounded fallback attempts failed: "
        f"{json.dumps(attempts, ensure_ascii=False)}"
    )


def create_centered_slot(
    model,
    center_x_mm: float,
    center_y_mm: float,
    size_x_mm: float,
    size_y_mm: float,
) -> None:
    'Create a horizontal/vertical obround slot with the specified envelope in the active sketch.'
    if size_x_mm >= size_y_mm:
        radius = size_y_mm / 2.0
        half_line = size_x_mm / 2.0 - radius
        sketch_slot(
            model,
            mm(center_x_mm - half_line),
            mm(center_y_mm),
            mm(center_x_mm + half_line),
            mm(center_y_mm),
            mm(radius),
        )
    else:
        radius = size_x_mm / 2.0
        half_line = size_y_mm / 2.0 - radius
        sketch_slot(
            model,
            mm(center_x_mm),
            mm(center_y_mm - half_line),
            mm(center_x_mm),
            mm(center_y_mm + half_line),
            mm(radius),
        )


def collect_feature_evidence(model, expected_names: list[str]) -> dict[str, Any]:
    'Read the top-level feature tree after rebuild and verify critical persistence.'
    model.ForceRebuild3(False)
    features = []
    feature = get_com_member(model, "FirstFeature")
    guard = 0
    while feature is not None and guard < 10000:
        features.append(
            {
                "name": str(get_com_member(feature, "Name") or ""),
                "type": str(get_com_member(feature, "GetTypeName2") or ""),
            }
        )
        feature = get_com_member(feature, "GetNextFeature")
        guard += 1
    names = {item["name"] for item in features}
    missing = [name for name in expected_names if name not in names]
    return {
        "status": "blocked" if missing else "pass",
        "expected_names": expected_names,
        "missing_names": missing,
        "features": features,
    }


def build_model(
    params: MountParameters,
    validation: dict[str, Any],
    output_dir: Path,
    basename: str,
    failure_policy: str,
) -> dict[str, Any]:
    'Build, save, export and review the model.'
    basename = validate_basename(basename)
    output_dir.mkdir(parents=True, exist_ok=True)
    part = output_dir / f"{basename}.SLDPRT"
    step = output_dir / f"{basename}.step"
    parameter_path = output_dir / f"{basename}_parameters.json"
    operation_plan = build_operation_plan(params, failure_policy)
    operations_by_name = {item["name"]: item for item in operation_plan}
    treatment_evidence = []
    expected_features = ["Base", "Boss"]

    session = SolidWorksSession(visible=True)
    try:
        session.close(title=part.name)
    except Exception:
        pass
    model = session.new_part()

    select_plane(model, ("Front Plane", "Ön Düzlem", "\u524d\u89c6\u57fa\u51c6\u9762"))
    model.SketchManager.InsertSketch(True)
    base_sketch = current_sketch_name(model, "Sketch_Base")
    model.SketchManager.CreateCenterRectangle(
        0, 0, 0, mm(params.length / 2.0), mm(params.width / 2.0), 0
    )
    model.SketchManager.InsertSketch(True)
    extrude_boss(model, base_sketch, params.thickness, "Base")
    offset_front_plane(model, "Plane_Base_Top", params.thickness)

    clear(model)
    model.Extension.SelectByID2(
        "Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
    )
    model.SketchManager.InsertSketch(True)
    boss_sketch = current_sketch_name(model, "Sketch_Boss")
    model.SketchManager.CreateCenterRectangle(
        0, 0, 0, mm(params.boss_length / 2.0), mm(params.boss_width / 2.0), 0
    )
    model.SketchManager.InsertSketch(True)
    extrude_boss(model, boss_sketch, params.boss_height, "Boss")

    for name in (
        "Fillet_Base_Corners",
        "Fillet_Boss_Corners",
        "Chamfer_Top_Outer",
        "Chamfer_Bottom_Outer",
        "Chamfer_Boss_Top",
    ):
        operation = operations_by_name.get(name)
        if operation:
            treatment_evidence.append(apply_treatment(model, operation, params))
            expected_features.append(name)

    clear(model)
    model.Extension.SelectByID2(
        "Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
    )
    model.SketchManager.InsertSketch(True)
    pocket_sketch = current_sketch_name(model, "Sketch_Pockets")
    for center_x in (-params.pocket_center_x, params.pocket_center_x):
        if params.pocket_shape == "rounded_slot":
            create_centered_slot(
                model, center_x, 0.0, params.pocket_length, params.pocket_width
            )
        else:
            model.SketchManager.CreateCenterRectangle(
                mm(center_x),
                0,
                0,
                mm(center_x + params.pocket_length / 2.0),
                mm(params.pocket_width / 2.0),
                0,
            )
    model.SketchManager.InsertSketch(True)
    cut(
        model,
        pocket_sketch,
        params.pocket_depth,
        "Lightening_Pockets",
        total_depth_mm=params.thickness + params.boss_height,
    )
    expected_features.append("Lightening_Pockets")

    positions = parameter_positions(params)
    hole_jobs = [
        ("Sketch_Mount_Holes", params.mount_hole_diameter / 2.0, positions["mount"], params.thickness, True, "Mount_Holes"),
        ("Sketch_Counterbores", params.counterbore_diameter / 2.0, positions["mount"], params.counterbore_depth, False, "Counterbores"),
        ("Sketch_Dowels", params.dowel_hole_diameter / 2.0, positions["dowel"], params.thickness, True, "Dowel_Holes"),
    ]
    for sketch_label, radius, hole_positions, depth, through_all, label in hole_jobs:
        clear(model)
        model.Extension.SelectByID2(
            "Plane_Base_Top", "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
        )
        model.SketchManager.InsertSketch(True)
        name = current_sketch_name(model, sketch_label)
        for x, y in hole_positions:
            model.SketchManager.CreateCircleByRadius(mm(x), mm(y), 0, mm(radius))
        model.SketchManager.InsertSketch(True)
        cut(
            model,
            name,
            depth,
            label,
            through_all=through_all,
            total_depth_mm=params.thickness + params.boss_height,
        )
        expected_features.append(label)

    boss_top_plane = offset_front_plane(
        model, "Plane_Boss_Top", params.thickness + params.boss_height
    )
    clear(model)
    model.Extension.SelectByID2(
        boss_top_plane, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
    )
    model.SketchManager.InsertSketch(True)
    slot_sketch = current_sketch_name(model, "Sketch_Center_Slot")
    create_centered_slot(model, 0.0, 0.0, params.slot_length, params.slot_width)
    model.SketchManager.InsertSketch(True)
    cut(
        model,
        slot_sketch,
        params.thickness + params.boss_height,
        "Center_Slot",
        through_all=True,
        total_depth_mm=params.thickness + params.boss_height,
    )
    expected_features.append("Center_Slot")

    hole_operation = operations_by_name.get("Chamfer_Hole_Mouths")
    if hole_operation:
        treatment_evidence.append(apply_treatment(model, hole_operation, params))
        expected_features.append("Chamfer_Hole_Mouths")

    set_document_appearance(model, "silver")
    model.ForceRebuild3(False)
    feature_evidence = collect_feature_evidence(model, expected_features)
    if feature_evidence["missing_names"]:
        raise RuntimeError(
            'Yeniden oluşturmadan sonra kritik unsur eksik; teslim durduruldu / Critical features missing after rebuild; delivery stopped: ' + ", ".join(feature_evidence["missing_names"])
        )
    hide_reference_planes(model)
    model.ViewZoomtofit2()

    payload = plan_payload(params, validation, failure_policy)
    payload.update(
        {
            "treatment_evidence": treatment_evidence,
            "feature_evidence": feature_evidence,
            "outputs": {"part": str(part), "step": str(step)},
        }
    )
    parameter_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not session.save(model, str(part)):
        raise RuntimeError(f"Kaydetme başarısız / Save failed: {part}")
    if not export_to_step(model, str(step)):
        raise RuntimeError(f"STEP dışa aktarma başarısız / STEP export failed: {step}")
    report, report_path = run_review(
        model,
        output_dir,
        basename=basename,
        expected_outputs=[str(part), str(step), str(parameter_path)],
    )
    print(
        f"review={report_path} status={report['evaluation']['status']} "
        f"score={report['evaluation']['score']}"
    )
    return {
        "part_path": str(part),
        "step_path": str(step),
        "parameter_path": str(parameter_path),
        "review_path": str(report_path),
        "review": report["evaluation"],
        "treatments": [
            {
                "name": item["name"],
                "status": item["status"],
                "actual_value_mm": item["actual_value_mm"],
            }
            for item in treatment_evidence
        ],
    }


def parse_args() -> argparse.Namespace:
    'Parse CLI arguments.'
    parser = argparse.ArgumentParser(
        description='Parametre kontrolü, anlamsal kenar seçimi ve geri dönüş kanıtıyla CNC montaj tabanı oluşturur / Generate a verified-plan CNC mounting base.'
    )
    parser.add_argument("--params-json", type=Path, help='JSON parametre dosyası; doğrudan alanlar veya parameters nesnesi / JSON parameter file, direct fields or parameters wrapper.')
    parser.add_argument(
        "--set",
        dest="set_values",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help='Parametreyi geçersiz kılın; tekrarlanabilir: --set base_corner_radius=6 / Repeatable parameter override.',
    )
    parser.add_argument("--length", type=float, help='Taban uzunluğu mm / Base length mm.')
    parser.add_argument("--width", type=float, help='Taban genişliği mm / Base width mm.')
    parser.add_argument("--thickness", type=float, help='Taban kalınlığı mm / Base thickness mm.')
    parser.add_argument("--base-corner-radius", type=float, help='Taban köşe radyüsü mm; 0 kapatır / Base corner radius mm; 0 disables.')
    parser.add_argument("--boss-corner-radius", type=float, help='Çıkıntı köşe radyüsü mm; 0 kapatır / Boss corner radius mm; 0 disables.')
    parser.add_argument("--top-chamfer", type=float, help='Taban üst dış kenar pahı mm; 0 kapatır / Base top-outline chamfer mm; 0 disables.')
    parser.add_argument("--pocket-shape", choices=("rounded_slot", "rectangle"), help='Hafifletme cebi biçimi / Weight-reduction pocket shape.')
    parser.add_argument(
        "--failure-policy",
        choices=("strict", "progressive"),
        default="progressive",
        help='strict yalnızca istenen boyutu dener; progressive 100%%/75%%/50%% adımlarına izin verir / strict uses requested dimensions; progressive allows bounded fallback.',
    )
    parser.add_argument("--basename", default="CNC_Mount_Template", help='Çıktı dosyası taban adı / Output basename.')
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "solidworks_fillet_chamfer_output",
        help='Çıktı dizini / Output directory.',
    )
    parser.add_argument("--dry-run", action="store_true", help="Yalnızca parametre kontrolü ve plan üretir; SolidWorks'e bağlanmaz / Validate and plan without connecting to SolidWorks.")
    return parser.parse_args()


def parameters_from_args(args: argparse.Namespace) -> tuple[MountParameters, dict[str, Any]]:
    'Build parameters in priority order: defaults, JSON, --set, explicit CLI.'
    overlays: list[dict[str, Any]] = []
    if args.params_json:
        overlays.append(load_parameter_file(args.params_json))
    overlays.append(parse_set_values(args.set_values))
    explicit = {
        "length": args.length,
        "width": args.width,
        "thickness": args.thickness,
        "base_corner_radius": args.base_corner_radius,
        "boss_corner_radius": args.boss_corner_radius,
        "top_chamfer": args.top_chamfer,
        "pocket_shape": args.pocket_shape,
    }
    overlays.append({name: value for name, value in explicit.items() if value is not None})
    return build_parameters(*overlays)


def main() -> int:
    'Command-line entry point.'
    args = parse_args()
    basename = validate_basename(args.basename)
    params, validation = parameters_from_args(args)
    if args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        plan_path = args.output_dir / f"{basename}_plan.json"
        plan_path.write_text(
            json.dumps(
                plan_payload(params, validation, args.failure_policy),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"status": "planned", "plan_path": str(plan_path)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    result = build_model(
        params, validation, args.output_dir, basename, args.failure_policy
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
