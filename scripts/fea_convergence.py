"""@brief Execute CalculiX multi-mesh convergence sequences and collect evidence."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .fea_analysis import run_analysis, validate_analysis
except ImportError:
    from fea_analysis import run_analysis, validate_analysis


def _now_iso() -> str:
    """@brief Return a UTC timestamp with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _finite_positive(value: Any, field: str, *, maximum: float | None = None) -> float:
    """@brief Validate finite positive values and optional upper bounds."""
    if isinstance(value, bool):
        raise ValueError(f"{field} sonlu pozitif sayı olmalı.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} sonlu pozitif sayı olmalı.") from exc
    if not math.isfinite(number) or number <= 0 or (maximum is not None and number > maximum):
        raise ValueError(f"{field} izin verilen aralık dışında.")
    return number


def _identifier(value: Any, field: str) -> str:
    """@brief Validate identifiers against path or solver-keyword injection."""
    token = str(value or "")
    if not token or len(token) > 64 or not token[0].isalpha() or not all(char.isalnum() or char == "_" for char in token):
        raise ValueError(f"{field} yalnızca harfle başlayan 1–64 harf, rakam veya alt çizgi içerebilir.")
    return token


def _load_request(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    """@brief Read convergence requests from a dictionary or JSON file up to 128 MiB."""
    if isinstance(value, dict):
        return dict(value)
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".json" or not path.is_file():
        raise ValueError("Mesh convergence isteği mevcut bir JSON dosyası olmalıdır.")
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Mesh convergence isteği 128 MiB güvenlik sınırını aşıyor.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Mesh convergence isteği bir JSON object olmalıdır.")
    return payload


def _physics_fingerprint(analysis: dict[str, Any]) -> str:
    """@brief Fingerprint physical conditions excluding mesh and task IDs."""
    payload = {
        key: analysis.get(key)
        for key in (
            "analysisType", "solver", "units", "material", "constraints", "loads",
            "nonlinearControls", "surfaces", "contacts",
        )
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_convergence_request(value: str | Path | dict[str, Any]) -> dict[str, Any]:
    """@brief Validate at least three meshes with identical physics and strictly increasing refinement."""
    request = _load_request(value)
    allowed = {"schemaVersion", "studyId", "tolerancePercent", "cases"}
    if set(request) - allowed:
        raise ValueError(f"Convergence isteğinde izin verilmeyen alanlar var: {', '.join(sorted(set(request) - allowed))}")
    if request.get("schemaVersion") != "1.0":
        raise ValueError("schemaVersion 1.0 olmalıdır.")
    _identifier(request.get("studyId"), "studyId")
    _finite_positive(request.get("tolerancePercent"), "tolerancePercent", maximum=25.0)
    cases = request.get("cases")
    if not isinstance(cases, list) or not 3 <= len(cases) <= 8:
        raise ValueError("cases 3-8 mesh seviyesi içermelidir.")
    case_ids: set[str] = set()
    previous_size = math.inf
    previous_nodes = 0
    previous_elements = 0
    fingerprint = None
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {"id", "characteristicSizeMm", "analysis"}:
            raise ValueError(f"cases[{index}] yapısı geçersiz.")
        case_id = _identifier(case.get("id"), f"cases[{index}].id")
        if case_id in case_ids:
            raise ValueError(f"Yinelenen convergence case ID: {case_id}")
        case_ids.add(case_id)
        size = _finite_positive(case.get("characteristicSizeMm"), f"cases[{index}].characteristicSizeMm")
        if size >= previous_size:
            raise ValueError("characteristicSizeMm kabadan inceye doğru kesin azalmalıdır.")
        previous_size = size
        analysis = validate_analysis(case.get("analysis"))
        if analysis["analysisType"] not in {"static_linear", "static_nonlinear"} or analysis["solver"] not in {"auto", "calculix"}:
            raise ValueError("Mesh convergence şu anda yalnızca CalculiX static_linear/static_nonlinear kabul eder.")
        node_count = len(analysis["mesh"]["nodes"])
        element_count = len(analysis["mesh"]["elements"])
        if node_count <= previous_nodes or element_count <= previous_elements:
            raise ValueError("Mesh inceldikçe node ve element sayıları kesin artmalıdır.")
        previous_nodes = node_count
        previous_elements = element_count
        current_fingerprint = _physics_fingerprint(analysis)
        if fingerprint is None:
            fingerprint = current_fingerprint
        elif current_fingerprint != fingerprint:
            raise ValueError("Tüm convergence case malzeme, yük ve constraint verileri aynı olmalıdır.")
    return request


def _versioned_directory(path: Path) -> Path:
    """@brief Return a versioned directory without overwriting existing directories."""
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.name}_v{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _relative_change_percent(previous: float, current: float) -> float:
    """@brief Calculate percentage relative change between adjacent mesh results."""
    return abs(current - previous) / max(abs(current), abs(previous), 1e-15) * 100.0


def run_convergence_study(
    value: str | Path | dict[str, Any],
    output_dir: str | Path,
    *,
    timeout_seconds_per_case: int = 600,
) -> dict[str, Any]:
    """@brief Solve each mesh sequentially and collect displacement/stress convergence evidence."""
    try:
        request = validate_convergence_request(value)
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": "1.0", "status": "blocked", "stage": "validate",
            "studyId": None, "cases": [], "artifacts": [], "manual_review_required": True,
            "retryable": False, "error_code": "fea_convergence_invalid_request",
            "message": str(exc), "generatedAt": _now_iso(),
        }
    root = _versioned_directory(Path(output_dir).expanduser().resolve() / request["studyId"])
    root.mkdir(parents=True, exist_ok=False)
    case_results = []
    artifacts = []
    for case in request["cases"]:
        analysis = dict(case["analysis"])
        analysis["analysisId"] = f"{request['studyId']}_{case['id']}"
        result = run_analysis(analysis, root, timeout_seconds=timeout_seconds_per_case)
        summary = result.get("resultEvidence", {}).get("summary", {})
        record = {
            "id": case["id"],
            "characteristicSizeMm": float(case["characteristicSizeMm"]),
            "nodeCount": len(analysis["mesh"]["nodes"]),
            "elementCount": len(analysis["mesh"]["elements"]),
            "status": result.get("status"),
            "error_code": result.get("error_code"),
            "maximumDisplacementMm": summary.get("maximumDisplacementMm"),
            "maximumVonMisesStressMPa": summary.get("maximumVonMisesStressMPa"),
            "maximumEquivalentPlasticStrain": summary.get("maximumEquivalentPlasticStrain"),
            "maximumPenetrationMm": summary.get("maximumPenetrationMm"),
            "maximumContactPressureMPa": summary.get("maximumContactPressureMPa"),
            "maximumContactSlipMm": summary.get("maximumContactSlipMm"),
            "solverVersion": summary.get("solverVersion"),
        }
        case_results.append(record)
        artifacts.extend(result.get("artifacts", []))
        if result.get("status") != "review_required":
            return {
                "schemaVersion": "1.0", "status": "failed", "stage": "solve",
                "studyId": request["studyId"], "cases": case_results, "artifacts": artifacts,
                "manual_review_required": True, "retryable": True,
                "error_code": "fea_convergence_case_failed", "failedCase": case["id"],
                "caseResult": result, "generatedAt": _now_iso(),
            }
    changes = []
    for previous, current in zip(case_results, case_results[1:]):
        displacement_change = _relative_change_percent(
            float(previous["maximumDisplacementMm"]), float(current["maximumDisplacementMm"])
        )
        stress_change = _relative_change_percent(
            float(previous["maximumVonMisesStressMPa"]), float(current["maximumVonMisesStressMPa"])
        )
        changes.append({
            "from": previous["id"], "to": current["id"],
            "displacementChangePercent": displacement_change,
            "stressChangePercent": stress_change,
            "plasticStrainChangePercent": (
                _relative_change_percent(
                    float(previous["maximumEquivalentPlasticStrain"]),
                    float(current["maximumEquivalentPlasticStrain"]),
                )
                if max(
                    float(previous.get("maximumEquivalentPlasticStrain") or 0.0),
                    float(current.get("maximumEquivalentPlasticStrain") or 0.0),
                ) > 0 else None
            ),
            "penetrationChangePercent": (
                _relative_change_percent(
                    float(previous["maximumPenetrationMm"]),
                    float(current["maximumPenetrationMm"]),
                )
                if max(
                    float(previous.get("maximumPenetrationMm") or 0.0),
                    float(current.get("maximumPenetrationMm") or 0.0),
                ) > 0 else None
            ),
            "contactPressureChangePercent": (
                _relative_change_percent(
                    float(previous["maximumContactPressureMPa"]),
                    float(current["maximumContactPressureMPa"]),
                )
                if max(
                    float(previous.get("maximumContactPressureMPa") or 0.0),
                    float(current.get("maximumContactPressureMPa") or 0.0),
                ) > 0 else None
            ),
        })
    tolerance = float(request["tolerancePercent"])
    last_change = changes[-1]
    required_metrics = [last_change["displacementChangePercent"], last_change["stressChangePercent"]]
    required_metrics.extend(
        last_change[key]
        for key in ("plasticStrainChangePercent", "penetrationChangePercent", "contactPressureChangePercent")
        if last_change[key] is not None
    )
    converged = all(value <= tolerance for value in required_metrics)
    report = {
        "schemaVersion": "1.0", "status": "review_required", "stage": "review",
        "studyId": request["studyId"], "solver": "calculix", "cases": case_results,
        "changes": changes, "tolerancePercent": tolerance, "converged": converged,
        "artifacts": artifacts, "manual_review_required": True,
        "retryable": not converged,
        "error_code": None if converged else "fea_mesh_convergence_not_reached",
        "limitations": [
            "Convergence son iki mesh seviyesindeki displacement/stress sonuçlarını ve varsa plastic strain/contact penetration/contact pressure değerlerini karşılaştırır; singularity, load path ve yerel sonuçlar ayrıca incelenmelidir.",
        ],
        "generatedAt": _now_iso(),
    }
    report_path = root / "convergence_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
