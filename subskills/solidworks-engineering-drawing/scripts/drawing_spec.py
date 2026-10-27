"""DrawingSpec v1 parsing and manufacturing-delivery preflight checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - supplied by installed dependencies; retain an explicit runtime gate
    Draft202012Validator = None


SCHEMA_VERSION = "1.0"
PAPER_SIZES = {"A4", "A3", "A2", "A1", "A0"}
PROJECTIONS = {"first_angle", "third_angle"}
DOCUMENT_TYPES = {"part", "assembly", "sheet_metal"}
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "drawing_spec.schema.json"


def load_drawing_spec(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Read DrawingSpec JSON or copy an in-memory specification."""
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source).expanduser().resolve()
    if path.suffix.lower() != ".json" or not path.is_file():
        raise ValueError(f"DrawingSpec mevcut bir JSON dosyası olmalıdır: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"DrawingSpec JSON geçersiz: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("DrawingSpec kök düğümü bir nesne olmalıdır")
    return payload


def _issue(code: str, message: str, severity: str = "error", path: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity, "path": path}


def _schema_issues(spec: Mapping[str, Any]) -> list[dict[str, str]]:
    """Validate basic types, fields, and coordinates against the official JSON Schema."""
    if Draft202012Validator is None:
        return [_issue("DRAWING_SPEC_SCHEMA_VALIDATOR_MISSING", "jsonschema bağımlılığı eksik; DrawingSpec güvenle doğrulanamıyor.")]
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        issues = []
        for error in sorted(validator.iter_errors(spec), key=lambda item: tuple(str(part) for part in item.absolute_path)):
            path = ".".join(str(part) for part in error.absolute_path)
            issues.append(_issue("DRAWING_SPEC_SCHEMA_INVALID", error.message, path=path))
        return issues
    except (OSError, json.JSONDecodeError) as exc:
        return [_issue("DRAWING_SPEC_SCHEMA_INVALID", f"DrawingSpec Schema okunamadı: {exc}")]


def validate_drawing_spec(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Validate a drawing specification and return a traceable blocked/pass report."""
    try:
        spec = load_drawing_spec(source)
    except ValueError as exc:
        return {"status": "blocked", "schema_version": SCHEMA_VERSION, "issues": [_issue("DRAWING_SPEC_INVALID", str(exc))]}

    issues: list[dict[str, str]] = _schema_issues(spec)
    required = ("schemaVersion", "sourceModel", "documentType", "standard", "projection", "paperSize", "modelSizeMm", "views", "outputs")
    for field in required:
        if field not in spec:
            issues.append(_issue("DRAWING_SPEC_REQUIRED_FIELD_MISSING", f"Zorunlu alan eksik: {field}", path=field))
    if spec.get("schemaVersion") != SCHEMA_VERSION:
        issues.append(_issue("DRAWING_SPEC_VERSION_UNSUPPORTED", f"Desteklenen tek schemaVersion={SCHEMA_VERSION}", path="schemaVersion"))
    if spec.get("documentType") not in DOCUMENT_TYPES:
        issues.append(_issue("DRAWING_SPEC_DOCUMENT_TYPE_INVALID", "documentType, part, assembly veya sheet_metal olmalıdır", path="documentType"))
    if spec.get("paperSize") not in PAPER_SIZES:
        issues.append(_issue("DRAWING_SPEC_PAPER_SIZE_INVALID", "paperSize, A4/A3/A2/A1/A0 olmalıdır", path="paperSize"))
    standard = spec.get("standard")
    projection = spec.get("projection")
    if standard not in {"GB_T", "ISO"}:
        issues.append(_issue("DRAWING_SPEC_STANDARD_INVALID", "standard, GB_T veya ISO olmalıdır", path="standard"))
    if projection not in PROJECTIONS:
        issues.append(_issue("DRAWING_SPEC_PROJECTION_INVALID", "projection, first_angle veya third_angle olmalıdır", path="projection"))
    if standard == "GB_T" and projection == "third_angle":
        issues.append(_issue("DRAWING_GBT_PROJECTION_CONFLICT", "GB/T çizimleri varsayılan olarak birinci açı izdüşümünü kullanır; üçüncü açı yerleşimi kullanılamaz"))

    views = spec.get("views")
    if not isinstance(views, dict) or not isinstance(views.get("front"), dict):
        issues.append(_issue("DRAWING_SPEC_FRONT_VIEW_MISSING", "views.front zorunlu ön görünüş tanımıdır", path="views.front"))

    outputs = spec.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("slddrw") is not True or outputs.get("pdf") is not True or outputs.get("report") is not True:
        issues.append(_issue("DRAWING_SPEC_DELIVERY_OUTPUTS_INCOMPLETE", "outputs en az slddrw, pdf ve report istemelidir", path="outputs"))

    bom = spec.get("bom") or {}
    if spec.get("documentType") == "assembly" and bom.get("required", True):
        template_path = bom.get("templatePath")
        if not template_path or not Path(str(template_path)).expanduser().is_file():
            issues.append(_issue("DRAWING_BOM_TEMPLATE_MISSING", "Montaj çiziminde BOM istendiğinde mevcut bir .sldbomtbt şablonu sağlanmalıdır", path="bom.templatePath"))

    for index, item in enumerate(spec.get("requiredDimensions", []) or []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("kind") or not item.get("view"):
            issues.append(_issue("DRAWING_DIMENSION_SPEC_INCOMPLETE", "Zorunlu ölçüler id, kind ve view alanlarını içermelidir", path=f"requiredDimensions[{index}]"))
    for index, item in enumerate(spec.get("holeRequirements", []) or []):
        valid = isinstance(item, dict) and item.get("id") and item.get("specification") and isinstance(item.get("count"), int) and item.get("count", 0) > 0
        locations = item.get("locationsMm") if isinstance(item, dict) else None
        if not valid or not isinstance(locations, list) or len(locations) != item.get("count", -1):
            issues.append(_issue("DRAWING_HOLE_REQUIREMENT_INCOMPLETE", "Delik/kanal gereksinimleri özellik, adet ve her delik için konum koordinatlarını içermelidir", path=f"holeRequirements[{index}]"))

    center_mark_views: dict[str, int] = {}
    orientation_aliases = {"front": "front", "frontview": "front", "ön": "front", "öngörünüş": "front", "\u524d\u89c6": "front", "\u4e3b\u89c6": "front",
                           "top": "top", "topview": "top", "üst": "top", "üstgörünüş": "top", "\u4e0a\u89c6": "top", "\u4fef\u89c6": "top",
                           "right": "right", "rightview": "right", "sağ": "right", "sağgörünüş": "right", "\u53f3\u89c6": "right"}
    professional_annotations = spec.get("professionalAnnotations") or {}
    center_mark_specs = professional_annotations.get("centerMarks", []) if isinstance(professional_annotations, dict) else []
    for index, item in enumerate(center_mark_specs or []):
        if not isinstance(item, dict):
            continue
        compact_view = "".join(character for character in str(item.get("view") or "").casefold() if character.isalnum() or "\u4e00" <= character <= "\u9fff")
        semantic_view = orientation_aliases.get(compact_view, compact_view)
        if semantic_view in center_mark_views:
            issues.append(_issue(
                "DRAWING_CENTER_MARK_VIEW_DUPLICATE",
                "Her standart görünüş için yalnızca bir otomatik merkez işareti grubu tanımlanabilir; targets alanlarını birleştirip toplam adedi kullanın.",
                path=f"professionalAnnotations.centerMarks[{index}].view",
            ))
        else:
            center_mark_views[semantic_view] = index

    if spec.get("documentType") == "sheet_metal":
        sheet_metal = spec.get("sheetMetal") or {}
        evidence = sheet_metal.get("flatPatternEvidencePath")
        if not evidence or not Path(str(evidence)).expanduser().is_file():
            issues.append(_issue("DRAWING_SHEET_METAL_FLAT_PATTERN_EVIDENCE_MISSING", "Sac çiziminde güvenilir açınım kanıtı eksik; görev engellenmeli veya pilot incelemesine alınmalıdır", "warning", "sheetMetal.flatPatternEvidencePath"))

    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    status = "blocked" if errors else "pilot" if warnings else "pass"
    return {
        "status": status,
        "schema_version": SCHEMA_VERSION,
        "spec": spec,
        "issues": issues,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "manual_review_required": True,
        "capability": "solidworks-engineering-drawing",
    }
