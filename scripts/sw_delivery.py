"""SOLIDWORKS BOM inventory and Pack and Go delivery tools."""
from __future__ import annotations

import csv
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pywintypes
from win32com.client import gencache

try:
    from .sw_connect import get_com_member, get_sw_version, _LaunchGuard, SolidWorksConnectionError, close_owned_solidworks
    from .sw_process import solidworks_processes
    from .sw_document_data import read_custom_property
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member, get_sw_version, _LaunchGuard, SolidWorksConnectionError, close_owned_solidworks
    from sw_process import solidworks_processes
    from sw_document_data import read_custom_property
    from sw_preflight import import_com_dependencies


pythoncom, win32com_client, _VARIANT = import_com_dependencies()
SLDWORKS_TYPELIB_ID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"
SW_DOC_TYPES = {
    ".sldprt": 1,
    ".sldasm": 2,
    ".slddrw": 3,
}


def _file_signature(path: Path):
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _property_value(model, configuration_name: str, names: tuple[str, ...]) -> str:
    if model is None:
        return ""
    for scope in (configuration_name, ""):
        for name in names:
            try:
                value = read_custom_property(model, name, configuration_name=scope)
            except Exception:
                continue
            if value["exists"]:
                return value["resolved"] or value["raw"]
    return ""


def collect_assembly_bom(model, *, include_excluded: bool = False) -> list[dict[str, Any]]:
    """Collect top-level assembly components and aggregate quantities by file path and configuration."""
    if int(get_com_member(model, "GetType")) != 2:
        raise ValueError("BOM listesi yalnızca montaj belgelerini destekler")
    components = get_com_member(model, "GetComponents", False) or []
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for component in components:
        excluded = bool(get_com_member(component, "ExcludeFromBOM"))
        if excluded and not include_excluded:
            continue
        path = str(get_com_member(component, "GetPathName") or "")
        configuration = str(get_com_member(component, "ReferencedConfiguration") or "")
        name = str(get_com_member(component, "Name2") or Path(path).stem or "Sanal bileşen")
        key = ((path or name).casefold(), configuration.casefold())
        if key in grouped:
            grouped[key]["quantity"] += 1
            continue
        referenced_model = get_com_member(component, "GetModelDoc2")
        part_number = _property_value(
            referenced_model,
            configuration,
            ("PartNumber", "Part Number", "Parça Kodu", "Parça Numarası", "\u96f6\u4ef6\u4ee3\u53f7", "\u96f6\u4ef6\u53f7"),
        ) or Path(path).stem or name
        grouped[key] = {
            "item": 0,
            "part_number": part_number,
            "description": _property_value(referenced_model, configuration, ("Description", "Açıklama", "\u63cf\u8ff0")),
            "material": _property_value(referenced_model, configuration, ("Material", "Malzeme", "\u6750\u6599")),
            "quantity": 1,
            "file": path,
            "configuration": configuration,
            "component": name,
            "excluded_from_bom": excluded,
        }
    rows = sorted(grouped.values(), key=lambda row: (row["part_number"].casefold(), row["configuration"].casefold()))
    for index, row in enumerate(rows, start=1):
        row["item"] = index
    return rows


def export_assembly_bom_csv(
    model,
    output_path,
    *,
    include_excluded: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export a UTF-8 BOM CSV with file-size and SHA-256 evidence."""
    target = Path(os.path.expandvars(str(output_path))).expanduser().resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"BOM dosyası mevcut; üzerine yazmaya izin verilmedi: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _file_signature(target)
    rows = collect_assembly_bom(model, include_excluded=include_excluded)
    headers = [
        "item", "part_number", "description", "material", "quantity",
        "file", "configuration", "component", "excluded_from_bom",
    ]
    with target.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    after = _file_signature(target)
    produced = after is not None and after != before
    return {
        "success": produced,
        "path": str(target),
        "rows": rows,
        "row_count": len(rows),
        "quantity_total": sum(row["quantity"] for row in rows),
        "size_bytes": after[0] if after else 0,
        "sha256": _sha256(target) if produced else "",
        "produced_this_run": produced,
        "review_required": True,
        "limitations": ["CSV, montaj bileşeni özellik listesidir; yerel SOLIDWORKS BOM ve teknik çizim ile elle karşılaştırılmalıdır"],
    }


def build_bom_traceability(bom_rows, *, model_path="", drawing_path="", review_path="") -> dict[str, Any]:
    """@brief Establish traceability between BOM, model, drawing, and review report."""
    rows = list(bom_rows or [])
    checks = [
        {"id": "bom-not-empty", "status": "pass" if rows else "warning", "message": "BOM bileşen satırları içeriyor" if rows else "BOM boş; tek parça mı yoksa okuma hatası mı olduğunu doğrulayın"},
        {"id": "model-reference", "status": "pass" if model_path else "warning", "message": "Model yolu ilişkilendirildi" if model_path else "Model yolu verilmedi"},
        {"id": "drawing-reference", "status": "pass" if drawing_path else "warning", "message": "Teknik çizim yolu ilişkilendirildi" if drawing_path else "Teknik çizim yolu verilmedi"},
        {"id": "review-reference", "status": "pass" if review_path else "warning", "message": "İnceleme raporu ilişkilendirildi" if review_path else "İnceleme raporu verilmedi"},
    ]
    return {
        "status": "pass" if rows and model_path and drawing_path else "warning",
        "stage": "review",
        "bom_row_count": len(rows),
        "quantity_total": sum(int(row.get("quantity") or 0) for row in rows),
        "model_path": str(model_path or ""),
        "drawing_path": str(drawing_path or ""),
        "review_path": str(review_path or ""),
        "rows": [{"item": row.get("item"), "part_number": row.get("part_number"), "file": row.get("file"), "configuration": row.get("configuration"), "quantity": row.get("quantity")} for row in rows],
        "checks": checks,
        "manual_review_required": True,
        "retryable": False,
        "error_code": None,
    }


def _status_codes(value) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [int(item) for item in value]
    try:
        return [int(item) for item in value]
    except TypeError:
        return [int(value)]


def _collect_new_outputs(target: Path, existing_files: dict[str, tuple[int, int] | None]) -> list[dict[str, Any]]:
    """@brief Collect output files actually created or overwritten by this Pack and Go run."""
    outputs = []
    for path in sorted(item for item in target.rglob("*") if item.is_file()):
        after = _file_signature(path)
        before = existing_files.get(str(path))
        produced = after is not None and after != before
        if produced:
            outputs.append({
                "path": str(path),
                "size_bytes": after[0],
                "sha256": _sha256(path),
                "produced_this_run": True,
            })
    return outputs


def _document_dependency_paths(model, source_path: str) -> list[str]:
    """@brief Read current document dependencies to detect missing Pack and Go files."""
    try:
        dependencies = get_com_member(model, "GetDependencies2", False, True, False) or []
    except Exception:
        return []
    values = list(dependencies)
    source_name = Path(source_path).name.casefold()
    paths = []
    for index in range(1, len(values), 2):
        path = str(values[index] or "")
        if not path or Path(path).name.casefold() == source_name:
            continue
        paths.append(path)
    return paths


def _optional_com_member(obj, name, *args, default=None):
    """@brief Safely read COM audit members and retain unknown when indeterminate."""
    if obj is None:
        return default
    try:
        value = get_com_member(obj, name, *args)
        return default if value is None else value
    except Exception:
        return default


def _is_external_reference(path: str, source_path: str) -> bool | None:
    """@brief Check whether a reference lies outside the assembly directory tree."""
    try:
        Path(path).expanduser().resolve().relative_to(Path(source_path).expanduser().resolve().parent)
        return False
    except ValueError:
        return True
    except (OSError, RuntimeError):
        return None


def _toolbox_state(component, referenced_model, path: str) -> tuple[str, str]:
    """@brief Read ToolboxPartType; when unavailable, use paths only as candidate evidence."""
    extension = _optional_com_member(referenced_model, "Extension")
    raw_type = _optional_com_member(extension, "ToolboxPartType")
    mapping = {0: "not_toolbox", 1: "standard", 2: "copied"}
    try:
        if raw_type is not None and int(raw_type) in mapping:
            return mapping[int(raw_type)], "IModelDocExtension.ToolboxPartType"
    except (TypeError, ValueError):
        pass
    normalised = str(path).replace("/", "\\").casefold()
    if "\\toolbox\\" in normalised or "\\solidworks data\\" in normalised or "\\browser\\" in normalised:
        return "candidate", "path_heuristic"
    return "unknown", "unavailable"


def _suppression_state(component) -> tuple[str, int | None]:
    """@brief Record component loading state using swComponentSuppressionState_e."""
    raw_state = _optional_com_member(component, "GetSuppression")
    mapping = {
        0: "suppressed",
        1: "lightweight",
        2: "fully_resolved",
        3: "resolved",
        4: "fully_lightweight",
        5: "internal_id_mismatch",
    }
    try:
        state = int(raw_state)
    except (TypeError, ValueError):
        suppressed = _optional_com_member(component, "IsSuppressed")
        if isinstance(suppressed, bool):
            return ("suppressed" if suppressed else "unknown"), None
        return "unknown", None
    return mapping.get(state, "unknown"), state


def _collect_component_audit_records(model, source_path: str) -> list[dict[str, Any]]:
    """@brief Collect configuration, Toolbox, and suppression audit evidence for Pack and Go."""
    components = _optional_com_member(model, "GetComponents", False, default=[]) or []
    records = []
    for component in components:
        path = str(_optional_com_member(component, "GetPathName", default="") or "")
        referenced_model = _optional_com_member(component, "GetModelDoc2")
        toolbox_state, toolbox_evidence = _toolbox_state(component, referenced_model, path)
        load_state, suppression_code = _suppression_state(component)
        records.append({
            "component": str(_optional_com_member(component, "Name2", default="") or Path(path).stem or "virtual"),
            "path": path,
            "configuration": str(_optional_com_member(component, "ReferencedConfiguration", default="") or ""),
            "load_state": load_state,
            "suppression_code": suppression_code,
            "is_suppressed": load_state == "suppressed",
            "is_lightweight": load_state in {"lightweight", "fully_lightweight"},
            "toolbox_state": toolbox_state,
            "toolbox_evidence": toolbox_evidence,
            "external_reference": _is_external_reference(path, source_path) if path else None,
            "source_exists": Path(path).is_file() if path else False,
        })
    return records


def _associated_drawing_paths(source_path: str, dependencies: list[str]) -> list[str]:
    """@brief Find an existing same-name SLDDrw alongside the model."""
    found = []
    seen = set()
    for raw_path in [source_path, *dependencies]:
        model_path = Path(raw_path).expanduser()
        if model_path.suffix.casefold() not in {".sldprt", ".sldasm"} or not model_path.parent.is_dir():
            continue
        try:
            matches = [
                candidate
                for candidate in model_path.parent.iterdir()
                if candidate.is_file()
                and candidate.stem.casefold() == model_path.stem.casefold()
                and candidate.suffix.casefold() == ".slddrw"
            ]
        except OSError:
            matches = []
        for candidate in matches:
            key = str(candidate.resolve()).casefold()
            if key not in seen:
                seen.add(key)
                found.append(str(candidate.resolve()))
    return found


def _required_pack_dependency_paths(
    dependencies: list[str],
    component_records: list[dict[str, Any]],
    associated_drawings: list[str],
    *,
    include_drawings: bool,
    include_toolbox_components: bool,
    include_suppressed: bool,
) -> list[str]:
    """@brief Determine references that must be written for the selected Pack and Go options."""
    metadata: dict[str, list[dict[str, Any]]] = {}
    for record in component_records:
        if record["path"]:
            metadata.setdefault(str(Path(record["path"]).resolve()).casefold(), []).append(record)
    required = []
    seen = set()
    for raw_path in dependencies:
        path = str(Path(raw_path).expanduser().resolve())
        records = metadata.get(path.casefold(), [])
        if records and not include_suppressed and all(record["is_suppressed"] for record in records):
            continue
        if records and not include_toolbox_components and all(record["toolbox_state"] in {"standard", "copied", "candidate"} for record in records):
            continue
        if path.casefold() not in seen:
            seen.add(path.casefold())
            required.append(path)
    if include_drawings:
        for raw_path in associated_drawings:
            path = str(Path(raw_path).expanduser().resolve())
            if path.casefold() not in seen:
                seen.add(path.casefold())
                required.append(path)
    return required


def build_pack_and_go_audit_matrix(
    source_path: str,
    dependencies: list[str],
    component_records: list[dict[str, Any]],
    associated_drawings: list[str],
    outputs: list[dict[str, Any]],
    *,
    include_drawings: bool,
    include_toolbox_components: bool,
    include_suppressed: bool,
) -> dict[str, Any]:
    """@brief Build an audit matrix for external references, Toolbox, configurations, suppressed components, and drawings."""
    required_dependencies = _required_pack_dependency_paths(
        dependencies,
        component_records,
        associated_drawings,
        include_drawings=include_drawings,
        include_toolbox_components=include_toolbox_components,
        include_suppressed=include_suppressed,
    )
    required_keys = {str(Path(path).resolve()).casefold() for path in required_dependencies}
    output_by_name: dict[str, list[dict[str, Any]]] = {}
    for output in outputs:
        output_by_name.setdefault(Path(output["path"]).name.casefold(), []).append(output)
    metadata_by_path: dict[str, list[dict[str, Any]]] = {}
    for record in component_records:
        if record["path"]:
            metadata_by_path.setdefault(str(Path(record["path"]).resolve()).casefold(), []).append(record)

    source = str(Path(source_path).expanduser().resolve())
    candidate_paths = [source, *[str(Path(item).expanduser().resolve()) for item in dependencies], *associated_drawings]
    seen = set()
    rows = []
    blocking_codes = []
    review_codes = []
    for raw_path in candidate_paths:
        path = str(Path(raw_path).expanduser().resolve())
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        records = metadata_by_path.get(key, [])
        is_source = key == source.casefold()
        is_drawing = Path(path).suffix.casefold() == ".slddrw"
        required = is_source or key in required_keys
        matches = output_by_name.get(Path(path).name.casefold(), [])
        if len(matches) > 1:
            blocking_codes.append("SW_PACK_AUDIT_OUTPUT_NAME_AMBIGUOUS")
        included = len(matches) == 1
        source_exists = Path(path).is_file()
        configurations = sorted({record["configuration"] for record in records if record["configuration"]})
        load_states = sorted({record["load_state"] for record in records})
        toolbox_states = sorted({record["toolbox_state"] for record in records})
        external_reference = any(record["external_reference"] is True for record in records) if records else _is_external_reference(path, source)
        if not source_exists:
            blocking_codes.append("SW_PACK_AUDIT_SOURCE_REFERENCE_MISSING")
        if required and not included:
            if is_source:
                blocking_codes.append("SW_PACK_AUDIT_SOURCE_OUTPUT_MISSING")
            elif is_drawing:
                blocking_codes.append("SW_PACK_AUDIT_ASSOCIATED_DRAWING_MISSING")
            elif external_reference:
                blocking_codes.append("SW_PACK_AUDIT_EXTERNAL_REFERENCE_MISSING")
            elif any(state in {"standard", "copied", "candidate"} for state in toolbox_states):
                blocking_codes.append("SW_PACK_AUDIT_TOOLBOX_COMPONENT_MISSING")
            elif any(state == "suppressed" for state in load_states):
                blocking_codes.append("SW_PACK_AUDIT_SUPPRESSED_COMPONENT_MISSING")
            else:
                blocking_codes.append("SW_PACK_AUDIT_REQUIRED_FILE_MISSING")
        if external_reference:
            review_codes.append("SW_PACK_AUDIT_EXTERNAL_REFERENCE_REVIEW_REQUIRED")
        if configurations:
            review_codes.append("SW_PACK_AUDIT_CONFIGURATION_CONTENT_REVIEW_REQUIRED")
        if any(state in {"lightweight", "fully_lightweight", "suppressed", "internal_id_mismatch"} for state in load_states):
            review_codes.append("SW_PACK_AUDIT_COMPONENT_STATE_REVIEW_REQUIRED")
        if include_toolbox_components and any(state in {"standard", "copied", "candidate", "unknown"} for state in toolbox_states):
            review_codes.append("SW_PACK_AUDIT_TOOLBOX_REVIEW_REQUIRED")
        rows.append({
            "source_path": path,
            "file_name": Path(path).name,
            "reference_kind": "source" if is_source else "associated_drawing" if is_drawing else "model_dependency",
            "required": required,
            "source_exists": source_exists,
            "included": included,
            "output_path": matches[0]["path"] if included else None,
            "produced_this_run": bool(matches[0].get("produced_this_run")) if included else False,
            "external_reference": external_reference,
            "configurations": configurations,
            "load_states": load_states or ["unknown"],
            "toolbox_states": toolbox_states or ["unknown"],
        })

    tracked_names = {row["file_name"].casefold() for row in rows}
    for output in outputs:
        if Path(output["path"]).name.casefold() not in tracked_names:
            rows.append({
                "source_path": None,
                "file_name": Path(output["path"]).name,
                "reference_kind": "untracked_output",
                "required": False,
                "source_exists": None,
                "included": True,
                "output_path": output["path"],
                "produced_this_run": bool(output.get("produced_this_run")),
                "external_reference": None,
                "configurations": [],
                "load_states": ["unknown"],
                "toolbox_states": ["unknown"],
            })
    blocking_codes = list(dict.fromkeys(blocking_codes))
    review_codes = list(dict.fromkeys(review_codes))
    status = "blocked" if blocking_codes else "review_required" if review_codes else "pass"
    required_rows = [row for row in rows if row["required"]]
    checks = [
        {"id": "pack-required-files", "status": "pass" if all(row["included"] for row in required_rows) else "fail", "message": f"Gerekli dosya {sum(row['included'] for row in required_rows)}/{len(required_rows)} diske yazıldı"},
        {"id": "pack-external-references", "status": "warning" if any(row["external_reference"] for row in rows) else "pass", "message": "Dış referanslar elle yeniden açılarak doğrulanmalı" if any(row["external_reference"] for row in rows) else "Proje dizini dışında referans bulunamadı"},
        {"id": "pack-toolbox", "status": "warning" if any("unknown" in row["toolbox_states"] or any(item in {"standard", "copied", "candidate"} for item in row["toolbox_states"]) for row in rows if row["reference_kind"] == "model_dependency") else "pass", "message": "Toolbox durumu kaydedildi; aday veya bilinmeyen öğeler elle doğrulanmalı"},
        {"id": "pack-configurations", "status": "warning" if any(row["configurations"] for row in rows) else "pass", "message": "Konfigürasyon referansları kaydedildi; içerik yeniden açılarak doğrulanmalı"},
        {"id": "pack-component-states", "status": "warning" if any(any(state in {"lightweight", "fully_lightweight", "suppressed", "internal_id_mismatch"} for state in row["load_states"]) for row in rows) else "pass", "message": "Suppressed, lightweight ve hatalı bileşen durumları matrise eklendi"},
        {"id": "pack-associated-drawings", "status": "pass" if all(row["included"] for row in rows if row["reference_kind"] == "associated_drawing" and row["required"]) else "fail", "message": "Yerelde mevcut aynı adlı ilişkili teknik çizimler denetlendi"},
    ]
    return {
        "schema_version": "1.0",
        "status": status,
        "stage": "review",
        "rows": rows,
        "checks": checks,
        "summary": {
            "row_count": len(rows),
            "required_count": len(required_rows),
            "included_required_count": sum(row["included"] for row in required_rows),
            "external_reference_count": sum(row["external_reference"] is True for row in rows),
            "toolbox_candidate_count": sum(any(state in {"standard", "copied", "candidate"} for state in row["toolbox_states"]) for row in rows),
            "configuration_reference_count": sum(len(row["configurations"]) for row in rows),
            "suppressed_or_lightweight_count": sum(any(state in {"suppressed", "lightweight", "fully_lightweight"} for state in row["load_states"]) for row in rows),
            "associated_drawing_count": sum(row["reference_kind"] == "associated_drawing" for row in rows),
        },
        "blocking_error_codes": blocking_codes,
        "review_codes": review_codes,
        "manual_review_required": True,
        "retryable": bool(blocking_codes),
        "error_code": blocking_codes[0] if blocking_codes else None,
    }


def _missing_dependency_paths(dependencies: list[str], outputs: list[dict[str, Any]]) -> list[str]:
    """@brief Check native Pack and Go output names for missing dependencies."""
    produced_names = {Path(item["path"]).name.casefold() for item in outputs}
    missing = []
    seen = set()
    for path in dependencies:
        name = Path(path).name.casefold()
        if name in seen:
            continue
        seen.add(name)
        if name not in produced_names:
            missing.append(path)
    return missing


def _safe_staged_destination(source: Path, sources: list[Path], target: Path, *, flatten: bool) -> Path:
    """@brief Compute dependency staging paths and prevent writes outside the destination directory."""
    target_root = target.resolve()
    if flatten:
        relative = Path(source.name)
    else:
        try:
            common_root = Path(os.path.commonpath([str(item.resolve()) for item in sources]))
            relative = source.resolve().relative_to(common_root)
        except (OSError, ValueError):
            # Use a stable external-reference directory when different drives or external references lack a common root.
            relative = Path("external") / hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:12] / source.name
    destination = (target_root / relative).resolve()
    try:
        destination.relative_to(target_root)
    except ValueError as exc:
        raise RuntimeError(f"Pack and Go hazırlama yolu sınır dışında: {destination}") from exc
    return destination


def _stage_pack_and_go_dependencies(
    source_path: str,
    dependencies: list[str],
    target: Path,
    existing_files: dict[str, tuple[int, int] | None],
    *,
    flatten: bool,
) -> dict[str, Any]:
    """@brief Create an auditable dependency staging package when the native manifest is incomplete.

    Copy only source files reported by SOLIDWORKS. Do not modify CAD contents or claim this is native Pack and Go. Each file and manifest carries current-run and SHA-256 evidence.
    """
    raw_sources = [str(Path(source_path).expanduser().resolve()), *dependencies]
    source_paths: list[Path] = []
    seen_sources: set[str] = set()
    for raw in raw_sources:
        path = Path(raw).expanduser().resolve()
        key = str(path).casefold()
        if key in seen_sources:
            continue
        seen_sources.add(key)
        if not path.is_file():
            raise FileNotFoundError(f"Pack and Go hazırlama kaynak dosyası yok: {path}")
        source_paths.append(path)

    destinations: dict[str, Path] = {}
    for source in source_paths:
        destination = _safe_staged_destination(source, source_paths, target, flatten=flatten)
        key = str(destination).casefold()
        previous = destinations.get(key)
        if previous is not None and previous.resolve() != source.resolve():
            raise RuntimeError(f"Pack and Go hazırlama dosya adı çakışması: {previous.name} <- {previous}, {source}")
        destinations[key] = source

    staged_files: list[dict[str, Any]] = []
    for key, source in destinations.items():
        destination = _safe_staged_destination(source, source_paths, target, flatten=flatten)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() == destination.resolve():
            raise RuntimeError(f"Pack and Go hazırlama hedefi kaynak dosyanın üzerine yazamaz: {source}")
        shutil.copy2(source, destination)
        signature = _file_signature(destination)
        if signature is None or signature[0] <= 0:
            raise RuntimeError(f"Pack and Go hazırlama dosyası boş: {destination}")
        staged_files.append({
            "source": str(source),
            "path": str(destination),
            "size_bytes": signature[0],
            "sha256": _sha256(destination),
            "produced_this_run": str(destination) not in existing_files or existing_files.get(str(destination)) != signature,
        })

    manifest_path = target / "cadstudio-pack-manifest.json"
    if manifest_path.exists() and str(manifest_path) in existing_files:
        raise FileExistsError(f"Pack and Go hazırlama manifest mevcut; üzerine yazmaya izin verilmedi: {manifest_path}")
    manifest = {
        "schemaVersion": "1.0",
        "backend": "staged_dependencies",
        "nativeFormat": "SolidWorks",
        "source": str(Path(source_path).expanduser().resolve()),
        "dependencies": [str(Path(item).expanduser().resolve()) for item in dependencies],
        "files": staged_files,
        "limitations": [
            "Bu, SOLIDWORKS GetDependencies2 tabanlı yerel hazırlama paketidir; yerel IPackAndGo listesi değildir",
            "Dış referanslar, Toolbox, konfigürasyonlar ve teknik çizimler SOLIDWORKS içinde elle incelenmeli",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_signature = _file_signature(manifest_path)
    if manifest_signature is None or manifest_signature[0] <= 0:
        raise RuntimeError(f"Pack and Go hazırlama manifest boş: {manifest_path}")
    staged_files.append({
        "path": str(manifest_path),
        "size_bytes": manifest_signature[0],
        "sha256": _sha256(manifest_path),
        "produced_this_run": str(manifest_path) not in existing_files or existing_files.get(str(manifest_path)) != manifest_signature,
        "kind": "manifest",
    })
    return {
        "backend": "staged_dependencies",
        "outputs": staged_files,
        "produced_count": len(staged_files),
        "manifest": str(manifest_path),
    }


def _comtypes_document_names(package, document_count: int) -> list[str]:
    """@brief Read a fixed-length native array through IPackAndGo::IGetDocumentNames.

    SW2024 Automation GetDocumentNames returns only the top-level document with some Python COM proxies. The official IGetDocumentNames uses GetDocumentNamesCount; allocate a BSTR array explicitly to avoid SAFEARRAY marshaling differences.
    """
    if document_count <= 0:
        return []
    names = (ctypes.c_wchar_p * document_count)()
    # comtypes allocates the [out] array automatically; only Count is required.
    result = package.IGetDocumentNames(document_count)
    # comtypes may return [out, retval] VARIANT_BOOL as bool or tuple.
    if result is False:
        raise RuntimeError("IPackAndGo.IGetDocumentNames False döndü")
    returned_names = result[0] if isinstance(result, tuple) and result else result
    if isinstance(returned_names, (list, tuple)):
        return [str(item) for item in returned_names if item]
    # Some generators still populate a local buffer; preserve that compatibility path.
    return [str(item) for item in names if item]


def _active_solidworks_major() -> int | None:
    """@brief Return the current SOLIDWORKS type library major version, such as 32 for SW2024."""
    try:
        sw = win32com_client.GetActiveObject("SldWorks.Application")
        revision = str(get_com_member(sw, "RevisionNumber"))
        return int(revision.split(".", 1)[0])
    except Exception:
        return None


def _load_sldworks_typelib_module():
    """@brief Load the current or most recently registered strongly typed pywin32 SOLIDWORKS module."""
    detected = _active_solidworks_major()
    candidates = [detected] if detected is not None else []
    candidates.extend(major for major in range(40, 19, -1) if major != detected)
    type_library_id = pywintypes.IID(SLDWORKS_TYPELIB_ID)
    errors = []
    for major in candidates:
        try:
            typelib = pythoncom.LoadRegTypeLib(type_library_id, major, 0, 0)
            attributes = typelib.GetLibAttr()
            return gencache.EnsureModule(
                attributes[0],
                attributes[1],
                attributes[3],
                attributes[4],
            )
        except Exception as exc:
            errors.append(f"{major}: {exc}")
    detail = "; ".join(errors[:3]) or "Kayıtlı sürüm bulunamadı"
    raise RuntimeError(f"SOLIDWORKS type library yüklenemedi: {detail}")


def _model_doc_extension(model):
    """@brief Obtain the correct IModelDocExtension from strongly typed IModelDoc2."""
    ole_object = getattr(model, "_oleobj_", None)
    if ole_object is None:
        return model.Extension
    module = _load_sldworks_typelib_module()
    typed_model = module.IModelDoc2(ole_object)
    extension = typed_model.Extension
    if extension is None:
        raise RuntimeError("SOLIDWORKS IModelDocExtension döndürmedi")
    return extension


def _coerce_dispatch(value):
    """@brief Wrap raw IDispatch as a pywin32 object; return ordinary test doubles unchanged."""
    if value is None:
        return None
    if hasattr(value, "_oleobj_") or hasattr(value, "SetSaveToName"):
        return value
    try:
        return win32com_client.Dispatch(value)
    except Exception:
        return value


def _get_pack_and_go(extension):
    """@brief Obtain IPackAndGo, preferring the current type library no-argument return-value signature."""
    errors: list[str] = []
    try:
        package = get_com_member(extension, "GetPackAndGo")
        if package is not None:
            return package
    except Exception as exc:
        errors.append(f"zero-arg: {exc}")

    ole_object = getattr(extension, "_oleobj_", None)
    if ole_object is not None:
        try:
            dispid = ole_object.GetIDsOfNames("GetPackAndGo")
            result = ole_object.InvokeTypes(
                dispid,
                0,
                pythoncom.DISPATCH_METHOD,
                (pythoncom.VT_DISPATCH, 0),
                (),
            )
            package = _coerce_dispatch(result)
            if package is not None:
                return package
        except Exception as exc:
            errors.append(f"noarg-invoketypes: {exc}")

        # SW2024 SP5 IDispatch::Invoke requires IPackAndGo in a by-ref dispatch output argument
        # (comtypes vtable calls do not have this restriction); the return value itself is empty.
        if dispid is not None:
            output = _VARIANT(pythoncom.VT_BYREF | pythoncom.VT_DISPATCH, None)
            try:
                ole_object.Invoke(
                    dispid,
                    0,
                    pythoncom.DISPATCH_METHOD | pythoncom.DISPATCH_PROPERTYGET,
                    1,
                    output,
                )
                package = _coerce_dispatch(output.value)
                if package is not None:
                    return package
            except Exception as exc:
                errors.append(f"byref-dispatch-out: {exc}")

    # Compatibility only for older anomalous wrappers; the current official type library is not by-ref.
    output = _VARIANT(pythoncom.VT_BYREF | pythoncom.VT_DISPATCH, None)
    member = getattr(extension, "GetPackAndGo", None)
    if callable(member):
        try:
            result = member(output)
            package = _coerce_dispatch(result) or _coerce_dispatch(output.value)
            if package is not None:
                return package
        except Exception as exc:
            errors.append(f"legacy-byref-method: {exc}")

    detail = "; ".join(errors) or "Nesne döndürülmedi"
    raise RuntimeError(f"SOLIDWORKS IPackAndGo nesnesi döndürmedi: {detail}")


def _pywin32_pack_and_go(
    extension,
    target: Path,
    existing_files: dict[str, tuple[int, int] | None],
    *,
    include_drawings: bool,
    include_simulation_results: bool,
    include_toolbox_components: bool,
    include_suppressed: bool,
    flatten: bool,
) -> dict[str, Any]:
    """@brief Call native SOLIDWORKS Pack and Go through pywin32."""
    package = _get_pack_and_go(extension)
    package.IncludeDrawings = bool(include_drawings)
    package.IncludeSimulationResults = bool(include_simulation_results)
    package.IncludeToolboxComponents = bool(include_toolbox_components)
    package.IncludeSuppressed = bool(include_suppressed)
    package.FlattenToSingleFolder = bool(flatten)
    document_count = int(get_com_member(package, "GetDocumentNamesCount"))
    if not package.SetSaveToName(True, str(target) + os.sep):
        raise RuntimeError("IPackAndGo.SetSaveToName hedef dizini reddetti")

    status_codes = _status_codes(extension.SavePackAndGo(package))
    outputs = _collect_new_outputs(target, existing_files)
    return {
        "backend": "pywin32",
        "document_count": document_count,
        "status_codes": status_codes,
        "outputs": outputs,
        "produced_count": len(outputs),
    }


def _comtypes_module():
    """@brief Load the early-bound SOLIDWORKS comtypes module."""
    import comtypes.client

    # This fallback is validated only for 2026; do not guess another major-version type library when ROT state is unknown.
    return comtypes.client.GetModule((SLDWORKS_TYPELIB_ID, 34, 0))


def _extract_comtypes_model(value):
    """@brief Extract an IModelDoc2 pointer from the comtypes OpenDoc6 result."""
    candidates = []

    def walk(item):
        if hasattr(item, "QueryInterface"):
            candidates.append(item)
        if isinstance(item, (list, tuple)):
            for child in item:
                walk(child)

    walk(value)
    if not candidates:
        raise RuntimeError(f"comtypes OpenDoc6 ModelDoc2 döndürmedi: {value!r}")
    from comtypes.gen import SldWorks

    for candidate in candidates:
        try:
            return candidate.QueryInterface(SldWorks.IModelDoc2)
        except Exception:
            continue
    return candidates[0]


def _comtypes_active_model(sw, source_path: str):
    """@brief Validate and return the active document when OpenDoc6 returns empty."""
    from comtypes.gen import SldWorks

    try:
        active = sw.ActiveDoc
    except Exception as exc:
        raise RuntimeError(f"comtypes ActiveDoc okunamadı: {exc}") from exc
    if not active:
        raise RuntimeError("comtypes ActiveDoc boş")
    document = active.QueryInterface(SldWorks.IModelDoc2)
    active_path = str(document.GetPathName() or "")
    if Path(active_path).resolve() != Path(source_path).resolve():
        raise RuntimeError(f"comtypes ActiveDoc hedef belge değil: {active_path}")
    return document


def _connect_comtypes_solidworks(client, progids: list[str], *, expected_pid=None):
    """@brief Prefer attaching to an active instance; return application, ownership flag, and last error."""
    def identity(app):
        """@brief Verify actual PID/version; constructor return values do not establish ownership."""
        try:
            pid = int(get_com_member(app, "GetProcessID"))
            version = get_sw_version(app)
        except Exception as error:
            raise SolidWorksConnectionError("SW_PROCESS_STATE_UNAVAILABLE", "pack_and_go", "Fallback örneğinin kimliği doğrulanamadı") from error
        if pid <= 0 or version["year"] != 2026:
            raise SolidWorksConnectionError("SW_VERSION_MISMATCH", "pack_and_go", "Pack and Go fallback yalnızca SOLIDWORKS 2026 için doğrulandı")
        if expected_pid is not None and pid != int(expected_pid):
            raise SolidWorksConnectionError("SW_INSTANCE_MISMATCH", "pack_and_go", "Fallback başka bir CAD örneğine bağlandı")
        return pid

    last_error = None
    with _LaunchGuard():
        before = solidworks_processes()
        for progid in progids:
            try:
                app = client.GetActiveObject(progid)
                identity(app)
                return app, False, last_error
            except SolidWorksConnectionError:
                raise
            except Exception as exc:
                last_error = exc
        if before is None:
            raise SolidWorksConnectionError("SW_PROCESS_STATE_UNAVAILABLE", "pack_and_go", "Süreç listesi okunamıyor; belirsiz örnek oluşturma engellendi")
        if expected_pid is not None and int(expected_pid) not in before:
            raise SolidWorksConnectionError("SW_INSTANCE_NOT_READY", "pack_and_go", "Ana örnek doğrulanamıyor; fallback başlatma engellendi")
        for progid in progids:
            try:
                app = client.CreateObject(progid)
                pid = identity(app)
                return app, pid not in before, last_error
            except SolidWorksConnectionError:
                raise
            except Exception as exc:
                last_error = exc
    return None, False, last_error


def _comtypes_pack_and_go(
    source_path: str,
    target: Path,
    existing_files: dict[str, tuple[int, int] | None],
    *,
    include_drawings: bool,
    include_simulation_results: bool,
    include_toolbox_components: bool,
    include_suppressed: bool,
    flatten: bool,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """@brief Run the comtypes Pack and Go fallback in an isolated process.

    Isolate Python COM marshaling and output. RPC_E_DISCONNECTED can also result from accidentally quitting a shared CAD service, so the child must bind to the parent PID; process isolation does not prove instance ownership.
    """
    # The parent verifies identity read-only; the child must attach to the same 2026 instance, never launch a replacement.
    expected_pid = _pack_parent_pid()
    payload = {
        "expected_pid": expected_pid,
        "source_path": source_path,
        "target": str(target),
        "existing_files": {key: list(value) if value is not None else None for key, value in existing_files.items()},
        "include_drawings": include_drawings,
        "include_simulation_results": include_simulation_results,
        "include_toolbox_components": include_toolbox_components,
        "include_suppressed": include_suppressed,
        "flatten": flatten,
        "dependencies": dependencies,
    }
    worker_script = Path(__file__).resolve().parent / "sw_delivery_comtypes_worker.py"
    try:
        completed = subprocess.run(
            [sys.executable, str(worker_script)],
            input=json.dumps(payload, ensure_ascii=True),
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
            timeout=120, cwd=str(Path(__file__).resolve().parent.parent),
        )
    except subprocess.TimeoutExpired as error:
        raise SolidWorksConnectionError("SW_PACK_AND_GO_TIMEOUT", "pack_and_go", "Fallback zaman aşımına uğradı; CAD çıktı durumu elle doğrulanmalı; otomatik yeniden deneme veya üzerine yazma yasak") from error
    stdout = (completed.stdout or "").strip()
    try:
        if len(stdout) > 8 * 1024 * 1024:
            raise ValueError("Fallback çıktısı çok büyük")
        decoded = json.loads(stdout)
        if not isinstance(decoded, dict):
            raise ValueError("Fallback sonucu JSON nesnesi olmalı")
    except Exception as exc:
        raise SolidWorksConnectionError("SW_PACK_AND_GO_WORKER_PROTOCOL", "pack_and_go", "Fallback çıktısı tam bir JSON sonucu değil") from exc
    if "error" in decoded:
        if decoded.get("code"):
            raise SolidWorksConnectionError(str(decoded["code"]), "pack_and_go", str(decoded["error"]))
        raise RuntimeError(f"comtypes worker iç hatası: {decoded['error']}")
    result = decoded.get("result")
    if completed.returncode != 0 or not isinstance(result, dict) or result.get("process_id") != expected_pid:
        raise SolidWorksConnectionError("SW_PACK_AND_GO_WORKER_PROTOCOL", "pack_and_go", "Fallback sonucu ana örneğin kimliğiyle eşleşmiyor")
    return result


def _comtypes_pack_and_go_impl(
    source_path: str,
    target: Path,
    existing_files: dict[str, tuple[int, int] | None],
    *,
    include_drawings: bool,
    include_simulation_results: bool,
    include_toolbox_components: bool,
    include_suppressed: bool,
    flatten: bool,
    dependencies: list[str] | None = None,
    expected_pid=None,
) -> dict[str, Any]:
    """@brief Run native SOLIDWORKS Pack and Go using the early-bound comtypes fallback."""
    import comtypes.client

    _comtypes_module()
    from comtypes.gen import SldWorks
    major = _active_solidworks_major()
    progids = [f"SldWorks.Application.{major}"] if major is not None else []
    progids.append("SldWorks.Application")
    sw, started_here, last_error = _connect_comtypes_solidworks(comtypes.client, progids, expected_pid=expected_pid)
    if sw is None:
        raise RuntimeError(f"comtypes SOLIDWORKS uygulamasını oluşturamadı: {last_error}")
    pid = int(get_com_member(sw, "GetProcessID"))
    before = _comtypes_documents(sw)
    source_resolved = Path(source_path).resolve()
    before_paths = [str(get_com_member(item, "GetPathName") or "") for item in before]
    opened_here = source_resolved not in {Path(path).resolve() for path in before_paths if path}
    if expected_pid is not None and opened_here:
        raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "pack_and_go", "Ana örneğin hedef belgesi okunan listede yok; belirsiz açma/kapatma engellendi")
    if opened_here and len(before) >= int(os.environ.get("SW_MAX_DOCUMENTS", "8")):
        raise SolidWorksConnectionError("SW_DOCUMENT_BUDGET", "pack_and_go", "Fallback belge açma işlemi bütçeyi aşacak")
    document = None
    result = None
    try:
        document_type = SW_DOC_TYPES.get(Path(source_path).suffix.casefold())
        if document_type is None:
            raise ValueError(f"Pack and Go belge türünü desteklemiyor: {source_path}")
        # Force full-model loading and override lightweight defaults, otherwise Pack and Go sees only the top-level document.
        open_result = sw.OpenDoc6(str(source_path), document_type, 1 | 16 | 64 | 512 | (2 if opened_here else 0), "")
        try:
            document = _extract_comtypes_model(open_result)
        except RuntimeError:
            document = _comtypes_active_model(sw, source_path)
        if Path(str(document.GetPathName())).resolve() != source_resolved:
            raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "pack_and_go", "Fallback tarafından döndürülen belge belirtilen kaynak dosya değil")
        # The 2026 Pack and Go manifest depends on the active document; OpenDoc6 does not activate an already open file.
        sw.ActivateDoc3(str(document.GetTitle()), False, 0)
        extension = document.Extension.QueryInterface(SldWorks.IModelDocExtension)
        if document_type == 2:
            try:
                document.QueryInterface(SldWorks.IAssemblyDoc).ResolveAllLightWeightComponents(True)
                document.ForceRebuild3(False)
            except Exception:
                pass
        package = extension.GetPackAndGo()
        package.IncludeDrawings = bool(include_drawings)
        package.IncludeSimulationResults = bool(include_simulation_results)
        package.IncludeToolboxComponents = bool(include_toolbox_components)
        package.IncludeSuppressed = bool(include_suppressed)
        package.FlattenToSingleFolder = bool(flatten)
        document_count = int(package.GetDocumentNamesCount())
        enumerated_names = _comtypes_document_names(package, document_count)
        enumerated_paths = {Path(path).resolve() for path in enumerated_names if path}
        enumeration_missing = [
            str(Path(path).resolve())
            for path in (dependencies or [])
            if Path(path).resolve() not in enumerated_paths
        ]
        # AddExternalDocuments adds non-model dependencies and is not guaranteed to accept native assembly part references.
        # Save natively even if enumeration is incomplete, then audit actual files for missing dependencies.
        if not package.SetSaveToName(True, str(target) + os.sep):
            raise RuntimeError("IPackAndGo.SetSaveToName hedef dizini reddetti")

        status_codes = _status_codes(extension.SavePackAndGo(package))
        outputs = _collect_new_outputs(target, existing_files)
        result = {
            "backend": "comtypes",
            "process_id": pid,
            "started_by_cad_studio": started_here,
            "opened_document_here": opened_here,
            "document_count": document_count,
            "status_codes": status_codes,
            "outputs": outputs,
            "produced_count": len(outputs),
            "enumeration_missing": enumeration_missing,
        }
        return result
    finally:
        if opened_here and document is not None:
            if int(get_com_member(sw, "GetProcessID")) != pid or Path(str(document.GetPathName())).resolve() != source_resolved:
                raise SolidWorksConnectionError("SW_INSTANCE_MISMATCH", "pack_and_go", "Temizlemeden önce belge veya örnek kimliği değişti; kapatma engellendi")
            sw.CloseDoc(str(document.GetTitle()))
            if result is not None:
                result["closed_owned_document"] = True
        if started_here and not _comtypes_documents(sw):
            close_owned_solidworks(sw, True, pid)


def _comtypes_documents(sw):
    """@brief Read actual document objects; never assume an empty instance when readback fails."""
    try:
        # comtypes incompletely unpacks VT_ARRAY|VT_DISPATCH. Reuse the verified pywin32
        # read-only inventory; writes still use comtypes in the child without changing parent library state.
        try:
            observer = win32com_client.GetActiveObject("SldWorks.Application")
        except Exception:
            observer = win32com_client.Dispatch("SldWorks.Application.34")
        if int(get_com_member(observer, "GetProcessID")) != int(get_com_member(sw, "GetProcessID")):
            raise ValueError("Liste gözlemcisi mevcut fallback örneği değil")
        return list(get_com_member(observer, "GetDocuments") or [])
    except Exception as error:
        raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "pack_and_go", f"Fallback belge listesi okunamadı: {type(error).__name__}: {error}") from error


def _pack_parent_pid():
    """@brief Prefer ROT identity; hidden instances without ROT registration require one unambiguous 2026 PID."""
    for progid in ("SldWorks.Application.34", "SldWorks.Application"):
        try:
            active = win32com_client.GetActiveObject(progid)
            if get_sw_version(active)["year"] == 2026:
                return int(get_com_member(active, "GetProcessID"))
        except Exception:
            continue
    processes = solidworks_processes()
    if processes is None or len(processes) != 1 or next(iter(processes.values())) != 2026:
        raise SolidWorksConnectionError("SW_PROCESS_STATE_UNAVAILABLE", "pack_and_go", "Ana örneğin PID değeri tekil olarak doğrulanamadı; fallback engellendi")
    return next(iter(processes))


def pack_and_go(
    model,
    output_dir,
    *,
    include_drawings: bool = True,
    include_simulation_results: bool = False,
    include_toolbox_components: bool = True,
    include_suppressed: bool = False,
    flatten: bool = False,
    overwrite: bool = False,
    fallback_policy: str = "stage_dependencies",
) -> dict[str, Any]:
    """Run native Pack and Go and apply the selected policy to missing dependency enumeration.

    fallback_policy=stage_dependencies produces an explicitly labeled local staging package if native save omits dependencies. blocked enforces the strict native gate.
    """
    if fallback_policy not in {"stage_dependencies", "blocked"}:
        raise ValueError("fallback_policy stage_dependencies veya blocked olmalı")
    source_path = str(get_com_member(model, "GetPathName") or "")
    if not source_path or not Path(source_path).is_file():
        raise ValueError("Pack and Go öncesinde etkin belge diske kaydedilmeli")
    target = Path(os.path.expandvars(str(output_dir))).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    existing_files = {str(path): _file_signature(path) for path in target.rglob("*") if path.is_file()}
    if existing_files and not overwrite:
        raise FileExistsError(f"Pack and Go hedef dizini boş değil; üzerine yazmaya izin verilmedi: {target}")

    dependencies = _document_dependency_paths(model, source_path)
    component_records = _collect_component_audit_records(model, source_path)
    associated_drawings = _associated_drawing_paths(source_path, dependencies)
    required_dependencies = _required_pack_dependency_paths(
        dependencies,
        component_records,
        associated_drawings,
        include_drawings=include_drawings,
        include_toolbox_components=include_toolbox_components,
        include_suppressed=include_suppressed,
    )
    fallback_errors = []
    native_error: str | None = None
    result: dict[str, Any]
    try:
        extension = _model_doc_extension(model)
        result = _pywin32_pack_and_go(
            extension,
            target,
            existing_files,
            include_drawings=include_drawings,
            include_simulation_results=include_simulation_results,
            include_toolbox_components=include_toolbox_components,
            include_suppressed=include_suppressed,
            flatten=flatten,
        )
    except Exception as exc:
        fallback_errors.append(f"pywin32: {exc}")
        try:
            result = _comtypes_pack_and_go(
                source_path,
                target,
                existing_files,
                include_drawings=include_drawings,
                include_simulation_results=include_simulation_results,
                include_toolbox_components=include_toolbox_components,
                include_suppressed=include_suppressed,
                flatten=flatten,
                dependencies=required_dependencies,
            )
        except Exception as comtypes_exc:
            if isinstance(comtypes_exc, SolidWorksConnectionError):
                # Timeout or unknown identity may leave CAD operations running; never start staging that could overwrite this delivery.
                raise
            fallback_errors.append(f"comtypes: {comtypes_exc}")
            native_error = str(comtypes_exc)
            result = {
                "backend": "native_unavailable",
                "document_count": 0,
                "status_codes": [],
                "outputs": [],
                "produced_count": 0,
                "enumeration_missing": required_dependencies,
            }

    native_outputs = list(result["outputs"])
    native_missing_dependencies = _missing_dependency_paths(required_dependencies, native_outputs)
    native_audit = build_pack_and_go_audit_matrix(
        source_path,
        dependencies,
        component_records,
        associated_drawings,
        native_outputs,
        include_drawings=include_drawings,
        include_toolbox_components=include_toolbox_components,
        include_suppressed=include_suppressed,
    )
    missing_dependencies = list(native_missing_dependencies)
    success = (
        bool(result["status_codes"])
        and all(code == 0 for code in result["status_codes"])
        and bool(result["outputs"])
        and not missing_dependencies
        and not native_audit["blocking_error_codes"]
    )
    staged = None
    native_status = "pass" if success else "blocked" if (missing_dependencies or native_audit["blocking_error_codes"]) and result["status_codes"] and all(code == 0 for code in result["status_codes"]) else "failed"
    if success:
        status = "pass"
        stage = "save"
        error_code = None
        retryable = False
        manual_review_required = True
        limitations = ["Pack and Go çıktılarında dış referanslar, Toolbox ve teknik çizimler elle örneklenerek denetlenmeli"]
    elif (missing_dependencies or native_audit["blocking_error_codes"]) and fallback_policy == "stage_dependencies":
        try:
            staged = _stage_pack_and_go_dependencies(
                source_path,
                required_dependencies,
                target,
                existing_files,
                flatten=flatten,
            )
        except Exception as exc:
            fallback_errors.append(f"staged_dependencies: {exc}")
            staged = None
        if staged is not None:
            success = True
            status = "pilot"
            stage = "review"
            error_code = "SW_PACK_AND_GO_NATIVE_ENUMERATION_INCOMPLETE"
            retryable = True
            manual_review_required = True
            limitations = [
                "Yerel IPackAndGo tüm bağımlılıkları listelemedi; GetDependencies2 tabanlı hazırlama paketi oluşturuldu",
                "Hazırlama paketi yerel Pack and Go değildir; dış referanslar, Toolbox, konfigürasyonlar ve teknik çizimler elle incelenmeli",
            ]
            result = {
                **result,
                "backend": "solidworks-native+staged_dependencies",
                "outputs": staged["outputs"],
                "produced_count": staged["produced_count"],
                "manifest": staged["manifest"],
            }
            missing_dependencies = []
        else:
            # Preserve evidence of native omissions if staging fails; never convert a failure into success.
            status = "blocked"
            stage = "review"
            error_code = "SW_PACK_AND_GO_DEPENDENCY_ENUMERATION_INCOMPLETE"
            retryable = True
            manual_review_required = True
            limitations = ["Yerel SOLIDWORKS Pack and Go tüm bağımlılıkları listelemedi ve hazırlama fallback tamamlanamadı"]
    elif (missing_dependencies or native_audit["blocking_error_codes"]) and result["status_codes"] and all(code == 0 for code in result["status_codes"]):
        # Strict native policy: preserve evidence and prevent an incorrect delivery.
        status = "blocked"
        stage = "review"
        error_code = "SW_PACK_AND_GO_DEPENDENCY_ENUMERATION_INCOMPLETE"
        retryable = True
        manual_review_required = True
        limitations = ["Yerel SOLIDWORKS Pack and Go tüm bağımlılıkları listelemedi; fallback_policy=blocked nedeniyle eksikler kopyalanmadı"]
    else:
        if fallback_policy == "stage_dependencies" and (required_dependencies or native_audit["blocking_error_codes"]):
            try:
                staged = _stage_pack_and_go_dependencies(
                    source_path,
                    required_dependencies,
                    target,
                    existing_files,
                    flatten=flatten,
                )
            except Exception as exc:
                fallback_errors.append(f"staged_dependencies: {exc}")
                staged = None
            if staged is not None:
                success = True
                status = "pilot"
                stage = "review"
                error_code = "SW_PACK_AND_GO_NATIVE_FAILED_STAGED"
                retryable = True
                manual_review_required = True
                limitations = [
                    "Yerel Pack and Go çağrısı başarısız; GetDependencies2 ile hazırlama paketi oluşturuldu",
                    "Hazırlama paketi yerel Pack and Go değildir; elle incelenmeli",
                ]
                result = {
                    **result,
                    "backend": "solidworks-native+staged_dependencies",
                    "outputs": staged["outputs"],
                    "produced_count": staged["produced_count"],
                    "manifest": staged["manifest"],
                }
                missing_dependencies = []
            else:
                status = "failed"
                stage = "save"
                error_code = "SW_PACK_AND_GO_SAVE_FAILED"
                retryable = True
                manual_review_required = False
                limitations = []
        else:
            status = "failed"
            stage = "save"
            error_code = "SW_PACK_AND_GO_SAVE_FAILED"
            retryable = True
            manual_review_required = False
            limitations = []
    final_audit = build_pack_and_go_audit_matrix(
        source_path,
        dependencies,
        component_records,
        associated_drawings,
        result["outputs"],
        include_drawings=include_drawings,
        include_toolbox_components=include_toolbox_components,
        include_suppressed=include_suppressed,
    )
    return {
        "success": success,
        "status": status,
        "stage": stage,
        "error_code": error_code,
        "retryable": retryable,
        "manual_review_required": manual_review_required,
        "limitations": limitations,
        "source": source_path,
        "output_dir": str(target),
        "backend": result["backend"],
        "native_backend": result.get("backend") if staged is None else "solidworks-native",
        "native_status": native_status,
        "document_count": result["document_count"],
        "status_codes": result["status_codes"],
        "outputs": result["outputs"],
        "produced_count": result["produced_count"],
        "dependencies": dependencies,
        "required_dependencies": required_dependencies,
        "component_audit": component_records,
        "associated_drawings": associated_drawings,
        "audit_matrix": final_audit,
        "native_audit_matrix": native_audit,
        "missing_dependencies": missing_dependencies,
        "native_missing_dependencies": native_missing_dependencies,
        "fallback_policy": fallback_policy,
        "fallback_used": staged is not None,
        "manifest": result.get("manifest"),
        "fallback_errors": fallback_errors,
        "options": {
            "include_drawings": include_drawings,
            "include_simulation_results": include_simulation_results,
            "include_toolbox_components": include_toolbox_components,
            "include_suppressed": include_suppressed,
            "flatten": flatten,
        },
    }
