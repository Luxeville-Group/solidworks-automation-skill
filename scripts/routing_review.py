"""@brief Neutral Routing validation and SOLIDWORKS 2026 preflight.

Do not guess long SOLIDWORKS Routing signatures or equate a type library with a usable add-in. Validate backend-independent endpoint, segment, length, and bend-radius evidence first. The preflight report then determines whether native IRouteManager / IAutoRoute writes are allowed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .cad_installation import discover_installation
    from .sw_capability_probe import _find_typelib, _type_names, TYPELIB_PATTERNS
    from .sw_preflight import import_com_dependencies, missing_com_dependencies
except ImportError:
    from cad_installation import discover_installation
    from sw_capability_probe import _find_typelib, _type_names, TYPELIB_PATTERNS
    from sw_preflight import import_com_dependencies, missing_com_dependencies


ROUTE_TYPES = {"pipe", "tube", "cable", "wire", "electrical", "hydraulic", "pneumatic"}
ROUTING_INTERFACES = {"IRouteManager", "IRouteProperty", "IAutoRoute"}
ROUTING_UNITS = {"mm", "cm", "m", "in", "inch"}
_MAX_INPUT_BYTES = 16 * 1024 * 1024


def _now_iso() -> str:
    """@brief Return a UTC timestamp with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _point(value: Any, label: str) -> tuple[float, float, float]:
    """@brief Read a three-dimensional point and reject non-finite values."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} üç sayıdan oluşan koordinat olmalı.")
    if any(isinstance(item, bool) for item in value):
        raise ValueError(f"{label} koordinatlarında boolean kullanılamaz.")
    point = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in point):
        raise ValueError(f"{label} sonlu olmayan koordinat içeriyor.")
    return point


def _finite_number(value: Any, label: str, *, minimum: float | None = None, positive: bool = False) -> float:
    """@brief Read a finite scalar; reject booleans and out-of-range values."""
    if isinstance(value, bool):
        raise ValueError(f"{label} sonlu sayısal değer olmalı.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} sonlu sayısal değer olmalı.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} sonlu sayısal değer olmalı.")
    if positive and number <= 0:
        raise ValueError(f"{label} sıfırdan büyük olmalı.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} şu değerden küçük olamaz: {minimum:g}.")
    return number


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    """@brief Return the Euclidean distance between two points."""
    return math.dist(first, second)


def _segment_hits_box(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    clearance: float,
) -> bool:
    """@brief Use the three-axis slab method to test a segment against an expanded AABB."""
    lower = tuple(value - clearance for value in minimum)
    upper = tuple(value + clearance for value in maximum)
    start, end = 0.0, 1.0
    for axis in range(3):
        delta = second[axis] - first[axis]
        if abs(delta) < 1e-12:
            if first[axis] < lower[axis] or first[axis] > upper[axis]:
                return False
            continue
        near = (lower[axis] - first[axis]) / delta
        far = (upper[axis] - first[axis]) / delta
        if near > far:
            near, far = far, near
        start = max(start, near)
        end = min(end, far)
        if start > end:
            return False
    return True


def _path_points(item: dict[str, Any], start: tuple[float, float, float], end: tuple[float, float, float], segment_id: str) -> list[tuple[float, float, float]]:
    """@brief Return a polyline including both endpoints."""
    raw_points = item.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        return [start, end]
    points = [_point(value, f"{segment_id}.points[{index}]") for index, value in enumerate(raw_points)]
    if points[0] != start:
        points.insert(0, start)
    if points[-1] != end:
        points.append(end)
    return points


def _native_addin_registration() -> list[dict[str, Any]]:
    """@brief Read-only lookup of Routing add-in registration; return an empty list outside Windows."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    rows: list[dict[str, Any]] = []
    roots = ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU"))
    for root, root_name in roots:
        try:
            with winreg.OpenKey(root, r"SOFTWARE\SOLIDWORKS\AddIns") as addins:
                count = winreg.QueryInfoKey(addins)[0]
                for index in range(count):
                    clsid = winreg.EnumKey(addins, index)
                    try:
                        with winreg.OpenKey(addins, clsid) as item:
                            title = str(winreg.QueryValueEx(item, "Title")[0]) if _registry_has(item, "Title") else ""
                            description = str(winreg.QueryValueEx(item, "Description")[0]) if _registry_has(item, "Description") else ""
                    except OSError:
                        continue
                    combined = f"{title} {description}".casefold()
                    if any(token in combined for token in ("routing", "route", "\u7ba1\u8def", "\u7ebf\u8def", "\u8def\u7531")):
                        rows.append({"root": root_name, "clsid": clsid, "title": title, "description": description})
        except OSError:
            continue
    return rows


def _registry_has(key: Any, name: str) -> bool:
    """@brief Check whether a registry value exists."""
    try:
        import winreg

        winreg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def probe_solidworks_routing() -> dict[str, Any]:
    """@brief Probe type libraries, actual interface coverage, add-in registration, and installed files."""
    installation = discover_installation("solidworks")
    typelib = _find_typelib(TYPELIB_PATTERNS["routing"])
    interfaces: list[str] = []
    error = None
    missing = missing_com_dependencies()
    if typelib and not missing:
        try:
            pythoncom, _client, _variant = import_com_dependencies(allow_install=False)
            names = set(_type_names(pythoncom, typelib))
            interfaces = sorted(ROUTING_INTERFACES.intersection(names))
        except Exception as exc:
            error = str(exc)
    install_dir = Path(str(installation.get("executable") or "")).parent
    files = [
        str(path)
        for name in ("SWRoutingLib.tlb", "SolidWorks.Interop.SWRoutingLib.dll", "sldroutingdveu.dll")
        if (path := install_dir / name).is_file()
    ]
    addins = _native_addin_registration()
    ready = bool(
        installation.get("installed")
        and typelib
        and set(interfaces) == ROUTING_INTERFACES
        and addins
        and not missing
    )
    blockers = []
    if not installation.get("installed"):
        blockers.append("SOLIDWORKS kurulumu bulunamadı.")
    if not typelib:
        blockers.append("SWRoutingLib.tlb bulunamadı.")
    if set(interfaces) != ROUTING_INTERFACES:
        blockers.append("Routing type library arayüz kapsamı eksik.")
    if not addins:
        blockers.append("SOLIDWORKS Routing Add-in kaydı veya kullanılabilir lisans kanıtı bulunamadı.")
    if missing:
        blockers.append("Eksik Python COM bağımlılığı: " + ", ".join(missing))
    return {
        "backend": "solidworks-routing",
        "status": "pilot" if ready else "blocked",
        "stage": "preflight",
        "solidworks": installation,
        "typeLibrary": str(typelib) if typelib else None,
        "interfacesFound": interfaces,
        "interfaceCoverage": len(interfaces) / len(ROUTING_INTERFACES),
        "routingFiles": files,
        "addins": addins,
        "blockers": blockers,
        "readyForNativeWrite": ready,
        "retryable": bool(installation.get("installed")),
        "error_code": None if ready else "routing_addin_or_license_unavailable",
        "error": error,
        "generatedAt": _now_iso(),
    }


def build_routing_report(document: dict[str, Any]) -> dict[str, Any]:
    """@brief Validate neutral Routing graph structure, endpoints, lengths, bend radii, and endpoint table."""
    routing = document.get("routing") if isinstance(document.get("routing"), dict) else document
    route_type = str(routing.get("routeType") or "").strip().lower()
    units = str(routing.get("units") or document.get("units") or "mm")
    endpoints = routing.get("endpoints") if isinstance(routing.get("endpoints"), list) else []
    segments = routing.get("segments") if isinstance(routing.get("segments"), list) else []
    obstacles = routing.get("obstacles") if isinstance(routing.get("obstacles"), list) else []
    supports = routing.get("supports") if isinstance(routing.get("supports"), list) else []
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    endpoint_map: dict[str, tuple[float, float, float]] = {}
    for index, item in enumerate(endpoints):
        if not isinstance(item, dict):
            issues.append({"code": "routing_endpoint_invalid", "severity": "critical", "message": f"endpoint[{index}] object değil."})
            continue
        endpoint_id = str(item.get("id") or "").strip()
        if not endpoint_id:
            issues.append({"code": "routing_endpoint_invalid", "severity": "critical", "message": f"endpoint[{index}] id eksik."})
            continue
        if endpoint_id in endpoint_map:
            issues.append({"code": "routing_endpoint_duplicate", "severity": "critical", "message": f"Yinelenen endpoint id: {endpoint_id}"})
            continue
        try:
            endpoint_map[endpoint_id] = _point(item.get("position"), f"endpoint {endpoint_id}")
        except (TypeError, ValueError) as exc:
            issues.append({"code": "routing_endpoint_invalid", "severity": "critical", "message": str(exc)})
    if route_type not in ROUTE_TYPES:
        issues.append({"code": "routing_type_invalid", "severity": "critical", "message": f"Desteklenmeyen routeType: {route_type or 'missing'}"})
    if units not in ROUTING_UNITS:
        issues.append({"code": "routing_units_invalid", "severity": "critical", "message": f"Desteklenmeyen Routing birimi: {units}"})
    if len(endpoint_map) < 2:
        issues.append({"code": "routing_endpoints_missing", "severity": "critical", "message": "Routing en az iki geçerli uç nokta gerektirir."})
    if not segments:
        issues.append({"code": "routing_segments_missing", "severity": "critical", "message": "Routing içinde segments eksik."})

    segment_evidence: list[dict[str, Any]] = []
    collision_evidence: list[dict[str, Any]] = []
    support_evidence: list[dict[str, Any]] = []
    bom_index: dict[tuple[str, float, str, str], dict[str, Any]] = {}
    used_endpoints: set[str] = set()
    segment_ids: set[str] = set()
    route_graph: dict[str, set[str]] = {endpoint_id: set() for endpoint_id in endpoint_map}
    valid_supports: list[dict[str, Any]] = []
    support_ids: set[str] = set()
    for index, support in enumerate(supports):
        if not isinstance(support, dict):
            issues.append({"code": "routing_support_invalid", "severity": "critical", "message": f"support[{index}] object değil."})
            continue
        support_id = str(support.get("id") or "").strip()
        segment_ref = str(support.get("segmentId") or "").strip()
        if not support_id or not segment_ref:
            issues.append({"code": "routing_support_invalid", "severity": "critical", "message": f"support[{index}] id veya segmentId eksik."})
            continue
        if support_id in support_ids:
            issues.append({"code": "routing_support_duplicate", "severity": "critical", "message": f"Yinelenen destek id: {support_id}"})
            continue
        support_ids.add(support_id)
        valid_supports.append(support)
    total_length = 0.0
    for index, item in enumerate(segments):
        if not isinstance(item, dict):
            issues.append({"code": "routing_segment_invalid", "severity": "critical", "message": f"segment[{index}] object değil."})
            continue
        segment_id = str(item.get("id") or f"segment-{index + 1}")
        if segment_id in segment_ids:
            issues.append({"code": "routing_segment_duplicate", "severity": "critical", "message": f"Yinelenen segment id: {segment_id}"})
            continue
        segment_ids.add(segment_id)
        start_id = str(item.get("start") or "")
        end_id = str(item.get("end") or "")
        start = endpoint_map.get(start_id)
        end = endpoint_map.get(end_id)
        if not start or not end:
            issues.append({"code": "routing_endpoint_reference_missing", "severity": "critical", "message": f"{segment_id} mevcut olmayan uç noktaya başvuruyor."})
            continue
        used_endpoints.update((start_id, end_id))
        route_graph[start_id].add(end_id)
        route_graph[end_id].add(start_id)
        try:
            points = _path_points(item, start, end, segment_id)
        except ValueError as exc:
            issues.append({"code": "routing_path_point_invalid", "severity": "critical", "message": str(exc)})
            continue
        legs = list(zip(points, points[1:]))
        if any(_distance(first, second) <= 1e-12 for first, second in legs):
            issues.append({"code": "routing_zero_length_leg", "severity": "critical", "message": f"{segment_id} yinelenen yol noktası veya sıfır uzunluklu segment içeriyor."})
        length = sum(_distance(first, second) for first, second in legs)
        try:
            bend_radius = _finite_number(item.get("bendRadius", routing.get("minimumBendRadius", 0)), f"{segment_id}.bendRadius", minimum=0)
            required_radius = _finite_number(routing.get("minimumBendRadius", 0), "minimumBendRadius", minimum=0)
            clearance = _finite_number(item.get("clearance", routing.get("minimumClearance", 0)), f"{segment_id}.clearance", minimum=0)
        except ValueError as exc:
            issues.append({"code": "routing_scalar_invalid", "severity": "critical", "message": str(exc)})
            continue
        if length <= 0:
            issues.append({"code": "routing_zero_length", "severity": "critical", "message": f"{segment_id} uzunluğu sıfır."})
        if required_radius <= 0 or bend_radius <= 0:
            issues.append({"code": "routing_bend_radius_missing", "severity": "high", "message": f"{segment_id} geçerli büküm yarıçapı eksik."})
        elif bend_radius < required_radius:
            issues.append({"code": "routing_bend_radius_too_small", "severity": "high", "message": f"{segment_id} büküm yarıçapı {bend_radius:g} gereken değerden küçük: {required_radius:g} {units}."})
        total_length += length
        collisions = []
        for obstacle in obstacles:
            if not isinstance(obstacle, dict):
                continue
            try:
                minimum = _point(obstacle.get("min"), f"obstacle {obstacle.get('id')}.min")
                maximum = _point(obstacle.get("max"), f"obstacle {obstacle.get('id')}.max")
            except ValueError as exc:
                issues.append({"code": "routing_obstacle_invalid", "severity": "critical", "message": str(exc)})
                continue
            if any(minimum[axis] > maximum[axis] for axis in range(3)):
                issues.append({"code": "routing_obstacle_bounds_invalid", "severity": "critical", "message": f"Engel {obstacle.get('id')} min/max sırası ters."})
                continue
            if any(_segment_hits_box(first, second, minimum, maximum, clearance) for first, second in legs):
                collisions.append(str(obstacle.get("id") or "obstacle"))
        if collisions:
            issues.append({"code": "routing_collision_or_clearance", "severity": "critical", "message": f"{segment_id} engel veya gerekli boşluk alanıyla kesişiyor.", "obstacles": collisions})
        collision_evidence.append({"segmentId": segment_id, "clearance": clearance, "obstacles": collisions, "status": "fail" if collisions else "pass"})

        try:
            max_support_spacing = _finite_number(
                item.get("maximumSupportSpacing", routing.get("maximumSupportSpacing", 0)),
                f"{segment_id}.maximumSupportSpacing",
                minimum=0,
            )
        except ValueError as exc:
            issues.append({"code": "routing_support_spacing_invalid", "severity": "critical", "message": str(exc)})
            max_support_spacing = 0.0
        segment_supports = [support for support in valid_supports if str(support.get("segmentId") or "") == segment_id]
        required_support_count = max(math.ceil(length / max_support_spacing) - 1, 0) if max_support_spacing > 0 else 0
        if max_support_spacing <= 0:
            issues.append({"code": "routing_support_spacing_missing", "severity": "high", "message": f"{segment_id} maksimum destek aralığı eksik."})
        elif len(segment_supports) < required_support_count:
            issues.append({"code": "routing_supports_insufficient", "severity": "high", "message": f"{segment_id} için en az {required_support_count} ara destek gerekli; mevcut {len(segment_supports)} adet."})
        support_positions = []
        for support in segment_supports:
            try:
                position = _finite_number(support.get("distanceAlong"), f"{segment_id}.support.distanceAlong", minimum=0)
            except ValueError as exc:
                issues.append({"code": "routing_support_position_invalid", "severity": "high", "message": str(exc)})
                continue
            if position > length:
                issues.append({"code": "routing_support_position_out_of_range", "severity": "high", "message": f"{segment_id} destek konumu {position:g} segment uzunluğunu aşıyor: {length:g}."})
                continue
            support_positions.append(position)
        support_positions.sort()
        gaps = [right - left for left, right in zip([0.0, *support_positions], [*support_positions, length])]
        maximum_actual_spacing = max(gaps, default=length)
        if max_support_spacing > 0 and maximum_actual_spacing > max_support_spacing + 1e-9:
            issues.append({"code": "routing_support_spacing_exceeded", "severity": "high", "message": f"{segment_id} gerçek maksimum destek aralığı {maximum_actual_spacing:g} gereksinimi aşıyor: {max_support_spacing:g}."})
        support_evidence.append({
            "segmentId": segment_id,
            "maximumSpacing": max_support_spacing,
            "maximumActualSpacing": maximum_actual_spacing,
            "required": required_support_count,
            "actual": len(segment_supports),
            "validPositions": len(support_positions),
            "status": "pass" if max_support_spacing > 0 and len(segment_supports) >= required_support_count and maximum_actual_spacing <= max_support_spacing + 1e-9 else "warning",
        })

        try:
            diameter = _finite_number(item.get("diameter", routing.get("diameter", 0)), f"{segment_id}.diameter", minimum=0)
        except ValueError as exc:
            issues.append({"code": "routing_diameter_invalid", "severity": "high", "message": str(exc)})
            diameter = 0.0
        material = str(item.get("material") or routing.get("material") or "Onay bekliyor")
        part_number = str(item.get("partNumber") or routing.get("partNumber") or "")
        bom_key = (route_type, diameter, material, part_number)
        bom_row = bom_index.setdefault(bom_key, {"routeType": route_type, "diameter": diameter, "material": material, "partNumber": part_number, "segmentCount": 0, "totalLength": 0.0, "units": units})
        bom_row["segmentCount"] += 1
        bom_row["totalLength"] += length
        segment_evidence.append({
            "id": segment_id,
            "start": start_id,
            "end": end_id,
            "length": length,
            "bendRadius": bend_radius,
            "pointCount": len(points),
            "clearance": clearance,
        })
    disconnected = sorted(set(endpoint_map).difference(used_endpoints))
    if disconnected:
        issues.append({"code": "routing_disconnected_endpoints", "severity": "high", "message": "Bağlanmamış uç noktalar var.", "endpoints": disconnected})
    orphan_supports = sorted(str(item.get("id")) for item in valid_supports if str(item.get("segmentId")) not in segment_ids)
    if orphan_supports:
        issues.append({"code": "routing_support_segment_missing", "severity": "critical", "message": "Destek, mevcut olmayan bir segmente başvuruyor.", "supports": orphan_supports})
    if used_endpoints:
        pending = {next(iter(used_endpoints))}
        reached: set[str] = set()
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.update(route_graph.get(current, set()).difference(reached))
        disconnected_network = sorted(used_endpoints.difference(reached))
        if disconnected_network:
            issues.append({"code": "routing_disconnected_graph", "severity": "critical", "message": "Routing segmentleri birbirinden kopuk alt ağlar oluşturuyor.", "endpoints": disconnected_network})
    checks.append({"id": "routing_endpoint_table", "status": "pass" if len(endpoint_map) >= 2 else "fail", "count": len(endpoint_map)})
    checks.append({"id": "routing_segment_lengths", "status": "pass" if segment_evidence else "fail", "totalLength": total_length, "segments": segment_evidence})
    checks.append({"id": "routing_collision_clearance", "status": "fail" if any(item["status"] == "fail" for item in collision_evidence) else "pass", "segments": collision_evidence})
    checks.append({"id": "routing_support_spacing", "status": "warning" if any(item["status"] != "pass" for item in support_evidence) else "pass", "segments": support_evidence})
    preflight = probe_solidworks_routing()
    status = "blocked" if any(item["severity"] == "critical" for item in issues) else "review_required"
    return {
        "schemaVersion": "1.0",
        "status": status,
        "stage": "routing_review",
        "routeType": route_type,
        "units": units,
        "checks": checks,
        "reviewFindings": issues,
        "endpointTable": [{"id": key, "position": list(value)} for key, value in endpoint_map.items()],
        "segmentEvidence": segment_evidence,
        "collisionEvidence": collision_evidence,
        "supportEvidence": support_evidence,
        "routingBom": list(bom_index.values()),
        "totalLength": total_length,
        "nativePreflight": preflight,
        "manual_review_required": True,
        "retryable": status == "blocked",
        "error_code": "routing_document_invalid" if status == "blocked" else None,
        "limitations": [
            "Nötr rota doğrulaması, yerel SOLIDWORKS Routing özelliği anlamına gelmez.",
            "Çarpışma ve boşluk kabulü için montaj B-Rep verisi ve gerçek Routing özelliği regresyonu gerekir.",
        ],
        "generatedAt": _now_iso(),
    }


def review_routing_file(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """@brief Read Routing JSON and write a structured report without overwriting earlier files."""
    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()

    def blocked(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
        """@brief Return a stable input-stage blocked report without writing untrusted content."""
        return {
            "schemaVersion": "1.0",
            "status": "blocked",
            "stage": "input_validation",
            "checks": [{"id": "routing_input", "status": "fail", "error_code": code}],
            "reviewFindings": [{"code": code, "severity": "critical", "message": message}],
            "artifacts": [],
            "manual_review_required": False,
            "retryable": retryable,
            "error_code": code,
            "sourceDocument": str(source),
            "reportPath": None,
            "generatedAt": _now_iso(),
        }

    try:
        if not source.is_file():
            return blocked("routing_input_missing", f"Routing giriş dosyası yok: {source}", retryable=True)
        if source.stat().st_size > _MAX_INPUT_BYTES:
            return blocked("routing_input_too_large", f"Routing giriş dosyası şu sınırı aşıyor: {_MAX_INPUT_BYTES} bayt.")
    except OSError as exc:
        return blocked("routing_input_unreadable", f"Routing giriş dosyası okunamadı: {exc}", retryable=True)

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return blocked("routing_input_invalid_json", f"Routing girdisi geçerli UTF-8 JSON değil: {exc}")
    if not isinstance(payload, dict):
        return blocked("routing_input_root_invalid", "Routing girişinin kök düğümü bir JSON object olmalı.")

    if target.exists():
        index = 2
        while target.with_name(f"{target.stem}_v{index}{target.suffix}").exists():
            index += 1
        target = target.with_name(f"{target.stem}_v{index}{target.suffix}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        report = blocked("routing_output_unwritable", f"Routing rapor dizini yazılamıyor: {exc}", retryable=True)
        report["reportPath"] = str(target)
        return report
    report = build_routing_report(payload)
    report["sourceDocument"] = str(source)
    report["reportPath"] = str(target)
    try:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    except OSError as exc:
        return blocked("routing_output_write_failed", f"Routing raporu yazılamadı: {exc}", retryable=True)
    return report


def main(argv: list[str] | None = None) -> int:
    """@brief Command-line entry point."""
    parser = argparse.ArgumentParser(description="CAD Studio Routing nötr doğrulama ve SOLIDWORKS ön denetimi")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.preflight:
        report = probe_solidworks_routing()
    else:
        if not args.input or not args.output:
            parser.error("preflight dışındaki modlarda --input ve --output gereklidir")
        report = review_routing_file(args.input, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("status") in {"blocked", "failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
