"""@brief Validate neutral plans for advanced surfaces and molds and enforce execution preconditions.

A parameter plan is not geometry. A specialized executor may promote status only after
a concrete backend generates and reads back the geometry. Current output remains
pilot or blocked and preserves evidence from golden failure cases.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_OPERATIONS = {"loft", "sweep", "knit", "thicken", "continuity_check", "draft", "parting", "core_cavity"}
_ENTITY_TYPES = {"profile", "path", "surface", "face", "edge", "solid", "direction"}
_TOP_FIELDS = {"schemaVersion", "planId", "units", "entities", "operations"}
_OP_FIELDS = {
    "id", "type", "profiles", "path", "surfaces", "surface", "faces", "edges", "solid", "direction",
    "continuity", "toleranceMm", "thicknessMm", "angleDeg", "partingSurfaces", "partingEdges", "output",
    "allowOpenShell", "checkSelfIntersection", "referenceSurface", "moldBlocks", "shrinkagePercent",
}


def _now_iso() -> str:
    """@brief Return a UTC timestamp with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _versioned_target(path: Path) -> Path:
    """@brief Return a versioned path without overwriting existing artifacts."""
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_v{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _sha256(path: Path) -> str:
    """@brief Compute a file SHA-256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _id(value: Any, field: str) -> str:
    """@brief Validate a stable entity or operation ID."""
    token = str(value or "")
    if not _ID.fullmatch(token):
        raise ValueError(f"{field} yalnızca harfle başlayan 1–64 harf, rakam veya alt çizgi içerebilir.")
    return token


def _positive(value: Any, field: str, *, maximum: float | None = None) -> float:
    """@brief Validate a finite positive number and optional upper bound."""
    if isinstance(value, bool):
        raise ValueError(f"{field} sonlu pozitif sayı olmalı.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} sonlu pozitif sayı olmalı.") from exc
    if not math.isfinite(number) or number <= 0 or (maximum is not None and number > maximum):
        raise ValueError(f"{field} sıfırdan büyük olmalı" + (f" ve üst sınırı aşmamalı: {maximum:g}" if maximum is not None else "") + ".")
    return number


def _load_plan(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    """@brief Read a neutral plan from a dictionary or a JSON file up to 4 MiB."""
    if isinstance(value, dict):
        return dict(value)
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".json" or not path.is_file():
        raise ValueError("Karmaşık geometri planı mevcut bir JSON dosyası olmalıdır.")
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Karmaşık geometri planı 4 MiB güvenlik sınırını aşıyor.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Karmaşık geometri planı bir JSON object olmalıdır.")
    return payload


def _refs(operation: dict[str, Any], field: str) -> list[str]:
    """@brief Normalize one reference or an array into a string array."""
    value = operation.get(field)
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [_id(item, f"{operation['id']}.{field}") for item in values]


def validate_geometry_plan(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    """@brief Strictly validate loft/sweep/knit/thicken, continuity and mold plans."""
    plan = _load_plan(value)
    unknown = set(plan) - _TOP_FIELDS
    if unknown:
        raise ValueError(f"Planda izin verilmeyen alanlar var: {', '.join(sorted(unknown))}")
    if plan.get("schemaVersion") != "1.0" or plan.get("units") != "mm":
        raise ValueError("schemaVersion 1.0, units mm olmalıdır.")
    _id(plan.get("planId"), "planId")
    entities = plan.get("entities")
    operations = plan.get("operations")
    if not isinstance(entities, list) or not entities:
        raise ValueError("entities en az bir öğe içermelidir.")
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations en az bir öğe içermelidir.")
    entity_types: dict[str, str] = {}
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict) or set(entity) != {"id", "type", "source"}:
            raise ValueError(f"entities[{index}] tam olarak id, type ve source içermeli.")
        entity_id = _id(entity["id"], f"entities[{index}].id")
        if entity_id in entity_types:
            raise ValueError(f"Yinelenen gövde ID: {entity_id}")
        if entity.get("type") not in _ENTITY_TYPES or not str(entity.get("source") or "").strip():
            raise ValueError(f"entities[{index}] türü veya kaynağı geçersiz.")
        entity_types[entity_id] = entity["type"]
    known = dict(entity_types)
    operation_ids: set[str] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or set(operation) - _OP_FIELDS:
            raise ValueError(f"operations[{index}] yapısı geçersiz veya izin verilmeyen alanlar içeriyor.")
        operation_id = _id(operation.get("id"), f"operations[{index}].id")
        if operation_id in operation_ids or operation_id in known:
            raise ValueError(f"Yinelenen işlem veya gövde ID: {operation_id}")
        operation_ids.add(operation_id)
        kind = operation.get("type")
        if kind not in _OPERATIONS:
            raise ValueError(f"operations[{index}].type desteklenmiyor.")
        _validate_operation(operation, known)
        output = operation.get("output")
        if output is not None:
            output_id = _id(output, f"{operation_id}.output")
            if output_id in known or output_id in operation_ids:
                raise ValueError(f"Yinelenen çıktı ID: {output_id}")
            known[output_id] = "solid" if kind in {"thicken", "core_cavity"} else "surface"
    return plan


def _require_types(operation: dict[str, Any], field: str, known: dict[str, str], allowed: set[str], *, minimum: int = 1) -> list[str]:
    """@brief Validate reference existence, counts and entity types."""
    refs = _refs(operation, field)
    if len(refs) < minimum:
        raise ValueError(f"{operation['id']}.{field} için en az {minimum} referans gerekli.")
    invalid = [ref for ref in refs if known.get(ref) not in allowed]
    if invalid:
        raise ValueError(f"{operation['id']}.{field} mevcut olmayan veya yanlış türdeki gövdeye başvuruyor: {', '.join(invalid)}")
    return refs


def _validate_operation(operation: dict[str, Any], known: dict[str, str]) -> None:
    """@brief Validate engineering-required fields for an advanced surface or mold operation."""
    kind = operation["type"]
    if kind == "loft":
        _require_types(operation, "profiles", known, {"profile", "edge"}, minimum=2)
        if operation.get("continuity") not in {"G0", "G1", "G2"}:
            raise ValueError(f"{operation['id']}.continuity G0/G1/G2 belirtmeli.")
    elif kind == "sweep":
        _require_types(operation, "profiles", known, {"profile"})
        _require_types(operation, "path", known, {"path", "edge"})
        if operation.get("checkSelfIntersection") is not True:
            raise ValueError(f"{operation['id']} checkSelfIntersection etkinleştirmeli.")
    elif kind == "knit":
        _require_types(operation, "surfaces", known, {"surface"}, minimum=2)
        _positive(operation.get("toleranceMm"), f"{operation['id']}.toleranceMm", maximum=1.0)
        if operation.get("allowOpenShell") not in {True, False}:
            raise ValueError(f"{operation['id']}.allowOpenShell açıkça belirtilmeli.")
    elif kind == "thicken":
        _require_types(operation, "surface", known, {"surface"})
        _positive(operation.get("thicknessMm"), f"{operation['id']}.thicknessMm")
        _require_types(operation, "direction", known, {"direction"})
    elif kind == "continuity_check":
        _require_types(operation, "edges", known, {"edge"})
        if operation.get("continuity") not in {"G0", "G1", "G2"}:
            raise ValueError(f"{operation['id']}.continuity G0/G1/G2 belirtmeli.")
        _positive(operation.get("toleranceMm"), f"{operation['id']}.toleranceMm", maximum=1.0)
    elif kind == "draft":
        _require_types(operation, "faces", known, {"face", "surface"})
        _require_types(operation, "direction", known, {"direction"})
        _positive(operation.get("angleDeg"), f"{operation['id']}.angleDeg", maximum=30.0)
    elif kind == "parting":
        _require_types(operation, "solid", known, {"solid"})
        _require_types(operation, "direction", known, {"direction"})
        _require_types(operation, "partingEdges", known, {"edge"})
    elif kind == "core_cavity":
        _require_types(operation, "solid", known, {"solid"})
        _require_types(operation, "partingSurfaces", known, {"surface"})
        blocks = _refs(operation, "moldBlocks")
        if len(blocks) != 2 or any(known.get(item) != "solid" for item in blocks):
            raise ValueError(f"{operation['id']}.moldBlocks iki geçerli kalıp bloğu gövdesine başvurmalı.")
        shrinkage = _positive(operation.get("shrinkagePercent"), f"{operation['id']}.shrinkagePercent", maximum=10.0)
        if shrinkage <= 0:
            raise ValueError("Çekme oranı (shrinkage) sıfırdan büyük olmalıdır.")


def geometry_preflight(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    """@brief Generate an advanced-geometry execution gate report without claiming geometry creation."""
    try:
        plan = validate_geometry_plan(value)
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": "1.0", "status": "blocked", "stage": "validate", "checks": [], "artifacts": [],
            "manual_review_required": True, "retryable": False, "error_code": "advanced_geometry_invalid_plan",
            "message": str(exc), "generatedAt": _now_iso(), "geometryProduced": False,
        }
    ocp_available = importlib.util.find_spec("OCP") is not None
    kinds = sorted({item["type"] for item in plan["operations"]})
    checks = [
        {"id": "plan_valid", "status": "pass", "message": "Karmaşık geometri referansları, birimler ve gerekli mühendislik parametreleri yapı doğrulamasını geçti."},
        {"id": "ocp_runtime", "status": "pass" if ocp_available else "warning", "message": "OCP runtime bulundu." if ocp_available else "OCP runtime bulunamadı."},
        {"id": "backend_implementation", "status": "fail", "message": "Golden sample ve hata kanıtı regresyonlarıyla doğrulanmış loft/sweep/knit/thicken/mold yürütme adaptörü henüz yok."},
    ]
    return {
        "schemaVersion": "1.0", "status": "pilot" if ocp_available else "blocked", "stage": "preflight",
        "checks": checks, "artifacts": [], "manual_review_required": True, "retryable": False,
        "error_code": "advanced_geometry_backend_unverified" if ocp_available else "advanced_geometry_runtime_missing",
        "planId": plan["planId"], "operationTypes": kinds, "backend": "headless_ocp" if ocp_available else None,
        "geometryProduced": False, "generatedAt": _now_iso(),
        "limitations": ["Yapılandırılmış plan bir B-Rep çıktısı değildir; geometri ancak üretim, yeniden açma, topoloji/süreklilik denetimi ve golden sample doğrulamasından sonra tamamlanmış sayılır."],
    }


def write_preflight_report(value: str | Path | dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    """@brief Write advanced-geometry preflight evidence without overwriting earlier reports."""
    report = geometry_preflight(value)
    target = _versioned_target(Path(output_path).expanduser().resolve())
    if target.suffix.lower() != ".json":
        raise ValueError("Karmaşık geometri raporu uzantısı .json olmalıdır.")
    target.parent.mkdir(parents=True, exist_ok=True)
    report["reportPath"] = str(target)
    report["artifacts"] = [{"kind": "advanced_geometry_preflight", "path": str(target), "producedThisRun": True}]
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["artifacts"][0].update({"sha256": _sha256(target), "sizeBytes": target.stat().st_size})
    return report


def main(argv: list[str] | None = None) -> int:
    """@brief Command-line entry point."""
    parser = argparse.ArgumentParser(description="CAD Studio gelişmiş yüzey/mold neutral plan ön denetimi")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = write_preflight_report(args.input, args.output) if args.output else geometry_preflight(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
