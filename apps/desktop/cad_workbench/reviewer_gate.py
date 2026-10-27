"""@brief Artifact review gate based on Artifact Ledger."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .agent_contracts import safe_job_id
from .core import now_iso

KNOWN_FORMAT_EXTENSIONS = {".step", ".stp", ".stl", ".dxf", ".pdf", ".dwg", ".sldprt", ".sldasm"}
DIMENSION_TRIPLE_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm|mm)?",
    re.IGNORECASE,
)
DIAMETER_PATTERN = re.compile(r"(?:diameter|hole diameter|çap|delik çapı|[Ø⌀Φφ])\s*(\d+(?:\.\d+)?)\s*(?:mm|mm)?", re.IGNORECASE)


def review_dir(queue_dir: Path) -> Path:
    """@brief Return the Reviewer Gate report directory."""
    directory = Path(queue_dir) / "reviews"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def review_path_for(queue_dir: Path, job_id: Any) -> Path:
    """@brief Return the Reviewer Gate report path for the specified job."""
    return review_dir(queue_dir) / f"{safe_job_id(job_id)}.review.json"


def _read_file_sample(path: Path, limit: int = 1024 * 1024) -> bytes:
    """@brief Read a file-header sample instead of loading an entire large CAD file for format checks."""
    with Path(path).open("rb") as handle:
        return handle.read(limit)


def _artifact_extension(kind: str, path: Path) -> str:
    """@brief Infer artifact format from the path suffix or kind."""
    suffix = path.suffix.lower()
    if suffix:
        return suffix
    normalized = kind.lower().lstrip(".")
    return f".{normalized}" if f".{normalized}" in KNOWN_FORMAT_EXTENSIONS else ""


def _text_sample(sample: bytes) -> str:
    """@brief Decode a binary sample permissively for STEP, DXF, and STL text-signature checks."""
    return sample.decode("utf-8", errors="ignore").upper()


def validate_known_format(kind: str, path: Path) -> dict[str, Any] | None:
    """@brief Run lightweight openability and format-signature checks for common CAD delivery formats."""
    extension = _artifact_extension(kind, path)
    if extension not in KNOWN_FORMAT_EXTENSIONS:
        return None

    sample = _read_file_sample(path)
    text = _text_sample(sample)
    check_id = f"artifact-format-{kind}"

    if extension in {".step", ".stp"}:
        valid = "ISO-10303-21" in text and "END-ISO-10303-21" in text
        return {
            "id": check_id,
            "severity": "P0",
            "status": "pass" if valid else "fail",
            "message": f"STEP Dosya{'İçerir' if valid else 'Eksik'} ISO-10303-21 Yapısal işaretler: {path}",
        }

    if extension == ".stl":
        ascii_valid = text.lstrip().startswith("SOLID") and "ENDSOLID" in text
        binary_valid = len(sample) >= 84 and not text.lstrip().startswith("SOLID")
        valid = ascii_valid or binary_valid
        return {
            "id": check_id,
            "severity": "P0",
            "status": "pass" if valid else "fail",
            "message": f"STL Dosya{'İçerir: ' if valid else 'Eksik'}Recognizable  ASCII/Binary Yapı: {path}",
        }

    if extension == ".dxf":
        valid = "SECTION" in text and text.rstrip().endswith("EOF")
        return {
            "id": check_id,
            "severity": "P0",
            "status": "pass" if valid else "fail",
            "message": f"DXF Dosya{'İçerir' if valid else 'Eksik'} SECTION/EOF Yapısal işaretler: {path}",
        }

    if extension == ".pdf":
        valid = sample.startswith(b"%PDF-")
        return {
            "id": check_id,
            "severity": "P0",
            "status": "pass" if valid else "fail",
            "message": f"PDF Dosya{'İçerir' if valid else 'Eksik'} %PDF Dosya başlığı: {path}",
        }

    if extension == ".dwg":
        valid = sample.startswith(b"AC10")
        return {
            "id": check_id,
            "severity": "P0",
            "status": "pass" if valid else "fail",
            "message": f"DWG Dosya{'İçerir' if valid else 'Eksik'} AutoCAD AC10 Sürüm başlığı: {path}",
        }

    if extension in {".sldprt", ".sldasm"}:
        label = "SLDASM" if extension == ".sldasm" else "SLDPRT"
        return {
            "id": check_id,
            "severity": "P1",
            "status": "warning",
            "message": f"{label}  özel bir biçimdir. Şu anda yalnızca dosya düzeyinde kayıt tamamlandı; sonraki inceleme için  SolidWorks İncelemeyi aç: {path}",
        }

    return None


def _close_measurement(left: float, right: float, tolerance: float = 1e-6) -> bool:
    """@brief Compare mechanical specification values recorded in millimeters."""
    return abs(left - right) <= tolerance


def _same_envelope(left: tuple[float, float, float], right: tuple[float, float, float]) -> bool:
    """@brief Compare bounding-box dimensions independently of model axis order."""
    return all(
        _close_measurement(left_value, right_value)
        for left_value, right_value in zip(sorted(left), sorted(right))
    )


def _unique_triplets(values: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """@brief Remove repeated three-axis dimensions from the job description."""
    unique: list[tuple[float, float, float]] = []
    for value in values:
        if not any(_same_envelope(value, existing) for existing in unique):
            unique.append(value)
    return unique


def _dimension_triplets(text: str) -> list[tuple[float, float, float]]:
    """@brief Extract an L x W x H or thickness dimension triple from natural language."""
    return [tuple(float(value) for value in match) for match in DIMENSION_TRIPLE_PATTERN.findall(text)]


def _diameters(text: str) -> list[float]:
    """@brief Extract explicitly stated hole diameters from natural language."""
    return [float(value) for value in DIAMETER_PATTERN.findall(text)]


def _json_measurements(value: Any) -> tuple[list[tuple[float, float, float]], list[float]]:
    """@brief Recursively read bounding-box dimensions and hole-diameter evidence from acceptance JSON."""
    triplets: list[tuple[float, float, float]] = []
    diameters: list[float] = []

    def visit(item: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(item, dict):
            normalized = {str(key).lower().replace("-", "_").replace(" ", "_"): child for key, child in item.items()}
            length = normalized.get("length", normalized.get("length_mm"))
            width = normalized.get("width", normalized.get("width_mm"))
            thickness = normalized.get(
                "thickness",
                normalized.get("thickness_mm", normalized.get("height", normalized.get("height_mm"))),
            )
            if not all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in (length, width, thickness)):
                length = normalized.get("size_x", normalized.get("size_x_mm", length))
                width = normalized.get("size_y", normalized.get("size_y_mm", width))
                thickness = normalized.get("size_z", normalized.get("size_z_mm", thickness))
            if all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in (length, width, thickness)):
                triplets.append((float(length), float(width), float(thickness)))
            for key, child in normalized.items():
                is_hole_evidence = (
                    key.startswith("hole_")
                    or any(segment in {"hole", "holes", "Delik", "Delik"} for segment in path)
                    or normalized.get("internal") is True
                )
                if (
                    key in {"diameter", "diameter_mm", "hole_diameter", "hole_diameter_mm"}
                    and is_hole_evidence
                    and isinstance(child, (int, float))
                    and not isinstance(child, bool)
                ):
                    diameters.append(float(child))
                visit(child, (*path, key))
        elif isinstance(item, list):
            for child in item:
                visit(child, path)

    visit(value)
    return triplets, diameters


def _trusted_measurement_payload(value: Any) -> dict[str, Any] | None:
    """@brief Accept only declared structured specification reports read back through CAD/B-Rep APIs."""
    if not isinstance(value, dict):
        return None
    cad_spec = value.get("cad_spec")
    if not isinstance(cad_spec, dict):
        return None
    source = str(cad_spec.get("measurement_source") or value.get("measurement_source") or "")
    trusted_prefixes = ("SolidWorks API ", "AutoCAD ActiveX ", "OpenCascade B-Rep ")
    return cad_spec if source.startswith(trusted_prefixes) else None


def _artifact_measurements(artifacts: list[dict[str, Any]]) -> tuple[list[tuple[float, float, float]], list[float]]:
    """@brief Read specification evidence from this run's JSON artifacts independently of the Codex summary."""
    triplets: list[tuple[float, float, float]] = []
    diameters: list[float] = []
    for artifact in artifacts:
        path = Path(str(artifact.get("path") or ""))
        if (
            artifact.get("exists") is not True
            or artifact.get("isDirectory") is True
            or artifact.get("producedThisRun") is not True
            or path.suffix.lower() != ".json"
            or int(artifact.get("sizeBytes") or 0) > 1024 * 1024
        ):
            continue
        try:
            raw = path.read_bytes()
            expected_sha256 = str(artifact.get("sha256") or "")
            if not expected_sha256 or hashlib.sha256(raw).hexdigest() != expected_sha256:
                continue
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        payload = _trusted_measurement_payload(value)
        if payload is None:
            continue
        found_triplets, found_diameters = _json_measurements(payload)
        triplets.extend(found_triplets)
        diameters.extend(found_diameters)
    return triplets, diameters


def _spec_conformance_checks(ledger: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """@brief Compare explicit requested dimensions with actual acceptance JSON specifications, preventing incorrect models from reaching manual approval."""
    strict_rules = ledger.get("strictRules") if isinstance(ledger.get("strictRules"), list) else []
    requirement_text = "\n".join(
        [
            str(ledger.get("objective") or ""),
            str(ledger.get("detail") or ""),
            *(str(item) for item in strict_rules),
        ]
    )
    expected_triplets = _dimension_triplets(requirement_text)
    expected_diameters = _diameters(requirement_text)
    evidence_triplets, evidence_diameters = _artifact_measurements(artifacts)
    expected_triplets = _unique_triplets(expected_triplets)
    checks: list[dict[str, Any]] = []

    if expected_triplets:
        missing_envelopes = [
            expected
            for expected in expected_triplets
            if not any(_same_envelope(expected, actual) for actual in evidence_triplets)
        ]
        checks.append(
            {
                "id": "spec-envelope-dimensions",
                "severity": "P0",
                "status": "pass" if evidence_triplets and not missing_envelopes else "fail",
                "message": (
                    f"Dış ölçü kanıtı görevle uyumlu: {expected_triplets} mm."
                    if evidence_triplets and not missing_envelopes
                    else "Bağımsız, makinece okunabilir dış ölçü kanıtı eksik."
                    if not evidence_triplets
                    else f"Dış ölçüler görevle uyuşmuyor; eksik:  {missing_envelopes} mm, Kabul kanıtı raporu {evidence_triplets} mm."
                ),
            }
        )

    if expected_diameters:
        unique_expected = sorted(set(expected_diameters))
        unique_actual = sorted(set(evidence_diameters))
        missing = [
            expected
            for expected in unique_expected
            if not any(_close_measurement(expected, actual) for actual in unique_actual)
        ]
        checks.append(
            {
                "id": "spec-hole-diameters",
                "severity": "P0",
                "status": "pass" if evidence_diameters and not missing else "fail",
                "message": (
                    f"Delik çapı kanıtı görevle uyumlu: {unique_expected} mm."
                    if evidence_diameters and not missing
                    else "Görev açık bir delik çapı belirtiyor ancak teslim dosyalarında bağımsız, makinece okunabilir çap kanıtı yok."
                    if not evidence_diameters
                    else f"Delik çapı görevle uyuşmuyor; gerekli çap eksik {missing} mm, Kabul kanıtı raporu {unique_actual} mm."
                ),
            }
        )
    return checks


def evaluate_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """@brief Generate the artifact review conclusion from the ledger."""
    artifacts = ledger.get("artifacts") if isinstance(ledger.get("artifacts"), list) else []
    checks: list[dict[str, Any]] = []
    delivery_artifacts = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and str(artifact.get("kind") or "") != "codex_output"
    ]
    checks.extend(_spec_conformance_checks(ledger, delivery_artifacts))

    verification = ledger.get("verification") if isinstance(ledger.get("verification"), list) else []
    if ledger.get("executor") == "codex" and not verification:
        checks.append(
            {
                "id": "executor-verification-present",
                "severity": "P1",
                "status": "warning",
                "message": "Yürütücü doğrulama kaydı döndürmedi; üretim adımının ilgili kontrolleri tamamladığı doğrulanamıyor.",
            }
        )
    for index, item in enumerate(verification):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "skipped")
        review_status = "pass" if status == "passed" else "warning" if status == "skipped" else "fail"
        checks.append(
            {
                "id": f"executor-verification-{index}",
                "severity": "P0" if review_status == "fail" else "P1",
                "status": review_status,
                "message": f"Yürütme doğrulaması {status}: {item.get('command') or 'Adsız kontrol'}; {item.get('note') or ''}",
            }
        )

    risks = ledger.get("risks") if isinstance(ledger.get("risks"), list) else []
    if risks:
        checks.append(
            {
                "id": "executor-residual-risks",
                "severity": "P1",
                "status": "warning",
                "message": "Yürütücü kalan riskler bildiriyor: " + "; ".join(str(item) for item in risks),
            }
        )

    expected_output = str(ledger.get("expectedOutput") or "")
    expected_groups: list[tuple[str, set[str]]] = []
    format_groups = [
        ("SLDPRT", {".sldprt"}),
        ("SLDASM", {".sldasm"}),
        ("STEP", {".step", ".stp"}),
        ("STL", {".stl"}),
        ("DWG", {".dwg"}),
        ("DXF", {".dxf"}),
        ("PDF", {".pdf"}),
    ]
    for label, extensions in format_groups:
        if label in expected_output:
            expected_groups.append((label, extensions))

    for label, expected_extensions in expected_groups:
        matching = []
        for artifact in delivery_artifacts:
            if Path(str(artifact.get("path") or "")).suffix.lower() not in expected_extensions:
                continue
            if artifact.get("exists") is not True:
                continue
            if ledger.get("executor") == "codex" and artifact.get("producedThisRun") is not True:
                continue
            matching.append(artifact)
        checks.append(
            {
                "id": f"expected-cad-deliverable-{label.lower()}",
                "severity": "P0",
                "status": "pass" if matching else "fail",
                "message": (
                    f"Bu yürütmede üretilen dosya bulundu:  {label}  çıktı, toplam  {len(matching)}  adet."
                    if matching
                    else f"Beklenen çıktı şunları içerir:  {label},  ancak bu yürütmede oluşturulan eşleşen dosya bulunamadı; AI JSON  acknowledgements or old files cannot replace delivery artifacts."
                ),
            }
        )
    cad_extensions = {extensions for _, group in format_groups for extensions in group}
    current_run_cad = [
        artifact
        for artifact in delivery_artifacts
        if Path(str(artifact.get("path") or "")).suffix.lower() in cad_extensions
        and artifact.get("exists") is True
        and (ledger.get("executor") != "codex" or artifact.get("producedThisRun") is True)
    ]
    target = str(ledger.get("target") or "")
    expects_non_cad = "Araştırma raporu" in expected_output or "Skills" in target or "Standart" in target
    if not expected_groups and ledger.get("localCadAutomation") is True and not expects_non_cad and not current_run_cad:
        checks.append(
            {
                "id": "cad-deliverable-not-declared",
                "severity": "P1",
                "status": "warning",
                "message": "Bu görevde yerel CAD otomasyonuna izin verildi ancak bu yürütmede CAD veya çizim dosyası üretilmedi. TXT, Markdown ve AI sonuç bildirimleri CAD teslim dosyalarının yerini tutmaz.",
            }
        )

    if not artifacts:
        checks.append(
            {
                "id": "artifact-present",
                "severity": "P1",
                "status": "warning",
                "message": "Görev teslim dosyası belirtmiyor. Yalnızca iş akışının tamamlandığı doğrulanabilir; üretim dosyalarının eksiksizliği doğrulanamaz.",
            }
        )

    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            continue
        kind = str(artifact.get("kind") or f"artifact_{index}")
        if artifact.get("exists") is not True:
            checks.append(
                {
                    "id": f"artifact-exists-{kind}",
                    "severity": "P0",
                    "status": "fail",
                    "message": f"Teslim dosyası mevcut değil: {artifact.get('path')}",
                }
            )
            continue
        if artifact.get("isDirectory") is True:
            checks.append(
                {
                    "id": f"artifact-directory-{kind}",
                    "severity": "P2",
                    "status": "warning",
                    "message": f"Çıktı bir klasör; şu anda yalnızca yol kaydedildi, içeriği özyinelemeli doğrulanmadı: {artifact.get('path')}",
                }
            )
            continue
        size_bytes = int(artifact.get("sizeBytes") or 0)
        if size_bytes <= 0:
            checks.append(
                {
                    "id": f"artifact-nonempty-{kind}",
                    "severity": "P0",
                    "status": "fail",
                    "message": f"Teslim dosyası boş: {artifact.get('path')}",
                }
            )
        elif not artifact.get("sha256"):
            checks.append(
                {
                    "id": f"artifact-hash-{kind}",
                    "severity": "P1",
                    "status": "warning",
                    "message": f"Teslim dosyalarında eksik:  SHA-256: {artifact.get('path')}",
                }
            )
        else:
            checks.append(
                {
                    "id": f"artifact-file-{kind}",
                    "severity": "P2",
                    "status": "pass",
                    "message": f"Teslim dosyaları mevcut ve kayıtlı hash: {artifact.get('path')}",
                }
            )
            format_check = validate_known_format(kind, Path(str(artifact.get("path"))))
            if format_check:
                checks.append(format_check)

    statuses = {check["status"] for check in checks}
    overall = "fail" if "fail" in statuses else "warning" if "warning" in statuses else "pass"
    return {
        "schemaVersion": "1.0",
        "jobId": ledger.get("jobId"),
        "runId": ledger.get("runId"),
        "status": overall,
        "reviewedAt": now_iso(),
        "artifactCount": len(artifacts),
        "checks": checks,
    }


def write_reviewer_gate(queue_dir: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    """@brief Write the Reviewer Gate report and return it."""
    review = evaluate_ledger(ledger)
    path = review_path_for(queue_dir, ledger.get("jobId"))
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    review["reviewPath"] = str(path)
    return review
