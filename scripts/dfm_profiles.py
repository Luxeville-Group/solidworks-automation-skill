"""@brief Validate, safely load and merge DFM process profiles.

Profiles describe traceable manufacturing capability boundaries. Never execute
profile paths, URLs or code. Later profiles cannot relax existing constraints.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


PROFILE_SCHEMA = "cadstudio.dfm-profile"
PROFILE_VERSION = "1.0"
MAX_PROFILE_BYTES = 1024 * 1024
SUPPORTED_PROCESSES = {"machining", "sheet_metal", "laser_cutting", "3d_printing", "injection_molding"}
TOP_LEVEL_FIELDS = {"schema", "version", "id", "source", "limits", "processes", "description"}
SOURCE_FIELDS = {"type", "name", "revision", "reference"}
LIMIT_FIELDS = {
    "minimumDraftAngleDeg", "maximumRibWallRatio", "maximumWallThicknessVariation", "minimumEjectorWaterClearance",
    "allowedMaterials",
    "minimumWallThickness",
    "maximumEnvelope",
    "workEnvelope",
    "formingEnvelope",
    "buildVolume",
    "minimumDrillDiameter",
    "minimumInternalCornerRadius",
    "availableToolDiameters",
    "maximumHoleDepthDiameterRatio",
    "minimumThickness",
    "maximumThickness",
    "minimumBendRadius",
    "minimumBendRadiusRatio",
    "minimumKerf",
    "maximumKerf",
    "minimumHoleOrSlot",
    "maximumUnsupportedOverhangDeg",
    "requiresBrepEvidence",
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MINIMUM_LIMITS = {
    "minimumDraftAngleDeg", "minimumEjectorWaterClearance",
    "minimumWallThickness",
    "minimumDrillDiameter",
    "minimumInternalCornerRadius",
    "minimumThickness",
    "minimumBendRadius",
    "minimumBendRadiusRatio",
    "minimumKerf",
    "minimumHoleOrSlot",
}
_MAXIMUM_LIMITS = {
    "maximumRibWallRatio", "maximumWallThicknessVariation",
    "maximumHoleDepthDiameterRatio",
    "maximumThickness",
    "maximumKerf",
    "maximumUnsupportedOverhangDeg",
}
_ENVELOPE_LIMITS = {"maximumEnvelope", "workEnvelope", "formingEnvelope", "buildVolume"}


class DfmProfileError(ValueError):
    """@brief Untrusted, malformed or mutually inconsistent profile."""


def _canonical_hash(payload: dict[str, Any]) -> str:
    """@brief Compute stable SHA-256 over normalized JSON."""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _positive_number(value: Any, field: str) -> float:
    """@brief Validate a finite positive number."""
    if isinstance(value, bool):
        raise DfmProfileError(f"Profile limits.{field} pozitif sayı olmalı; boolean olamaz.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DfmProfileError(f"Profile limits.{field} pozitif sayı olmalı.") from exc
    if not 0 < number < float("inf"):
        raise DfmProfileError(f"Profile limits.{field} pozitif sonlu sayı olmalı.")
    return number


def _positive_vector(value: Any, field: str) -> list[float]:
    """@brief Validate a three-axis capability envelope."""
    if not isinstance(value, list) or len(value) != 3:
        raise DfmProfileError(f"Profile limits.{field} üç pozitif sayıdan oluşan dizi olmalı.")
    return [_positive_number(item, field) for item in value]


def validate_profile(payload: Any) -> dict[str, Any]:
    """@brief Strictly validate and normalize one DFM Profile.

    @param payload JSON object to validate.
    @return Normalized profile that can be safely merged.
    @raises DfmProfileError For unknown fields, unsafe values or unsupported versions.
    """
    if not isinstance(payload, dict):
        raise DfmProfileError("DFM Profile bir JSON object olmalıdır.")
    unknown = sorted(set(payload) - TOP_LEVEL_FIELDS)
    if unknown:
        raise DfmProfileError("DFM Profile bilinmeyen üst düzey alanlar içeriyor: " + ", ".join(unknown))
    for field in ("schema", "version", "id", "source", "limits"):
        if field not in payload:
            raise DfmProfileError(f"DFM Profile gerekli alanı eksik: {field}.")
    if payload.get("schema") != PROFILE_SCHEMA or str(payload.get("version")) != PROFILE_VERSION:
        raise DfmProfileError(f"Yalnızca desteklenen: {PROFILE_SCHEMA} {PROFILE_VERSION}.")
    profile_id = str(payload.get("id") or "")
    if not _IDENTIFIER.fullmatch(profile_id):
        raise DfmProfileError("DFM Profile id yalnızca harf, rakam, nokta, alt çizgi ve tire içerebilir.")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise DfmProfileError("DFM Profile source bir object olmalıdır.")
    unknown_source = sorted(set(source) - SOURCE_FIELDS)
    if unknown_source:
        raise DfmProfileError("DFM Profile source bilinmeyen alanlar içeriyor: " + ", ".join(unknown_source))
    if not str(source.get("type") or "").strip() or not str(source.get("name") or "").strip():
        raise DfmProfileError("DFM Profile source boş olmayan type ve name içermelidir.")

    processes = payload.get("processes", [])
    if processes is None:
        processes = []
    if not isinstance(processes, list) or any(item not in SUPPORTED_PROCESSES for item in processes):
        raise DfmProfileError("DFM Profile processes desteklenmeyen bir süreç içeriyor.")
    if len(set(processes)) != len(processes):
        raise DfmProfileError("DFM Profile processes yinelenemez.")

    limits = payload.get("limits")
    if not isinstance(limits, dict) or not limits:
        raise DfmProfileError("DFM Profile limits boş olmayan bir object olmalıdır.")
    unknown_limits = sorted(set(limits) - LIMIT_FIELDS)
    if unknown_limits:
        raise DfmProfileError("DFM Profile limits bilinmeyen veya geçersiz kılınamayan alanlar içeriyor: " + ", ".join(unknown_limits))
    normalized_limits: dict[str, Any] = {}
    for key, value in limits.items():
        if key in _MINIMUM_LIMITS | _MAXIMUM_LIMITS:
            normalized_limits[key] = _positive_number(value, key)
        elif key in _ENVELOPE_LIMITS:
            normalized_limits[key] = _positive_vector(value, key)
        elif key == "requiresBrepEvidence":
            if not isinstance(value, bool):
                raise DfmProfileError("Profile limits.requiresBrepEvidence boolean olmalıdır.")
            normalized_limits[key] = value
        elif key in {"allowedMaterials"}:
            if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
                raise DfmProfileError(f"Profile limits.{key} boş olmayan malzeme adı dizisi olmalı.")
            normalized_limits[key] = sorted({str(item).strip() for item in value}, key=str.casefold)
        elif key == "availableToolDiameters":
            if not isinstance(value, list) or not value:
                raise DfmProfileError("Profile limits.availableToolDiameters boş olmayan pozitif sayı array olmalıdır.")
            normalized_limits[key] = sorted({_positive_number(item, key) for item in value})

    normalized = {
        "schema": PROFILE_SCHEMA,
        "version": PROFILE_VERSION,
        "id": profile_id,
        "source": {key: source[key] for key in sorted(source) if source[key] not in (None, "")},
        "limits": normalized_limits,
        "processes": list(processes),
    }
    if str(payload.get("description") or "").strip():
        normalized["description"] = str(payload["description"]).strip()
    normalized["sha256"] = _canonical_hash(normalized)
    return normalized


def _resolve_profile_path(path: Path, allowed_root: Path | None) -> Path:
    """@brief Resolve profile paths and prevent relative-path escape."""
    raw = Path(path).expanduser()
    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        if allowed_root is None:
            raise DfmProfileError("Göreli Profile yolu için allowed_root belirtilmelidir.")
        root = allowed_root.expanduser().resolve()
        resolved = (root / raw).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise DfmProfileError("Göreli Profile yolu allowed_root dışına çıkıyor; reddedildi.") from exc
    if resolved.suffix.lower() != ".json" or not resolved.is_file():
        raise DfmProfileError("DFM Profile mevcut bir .json dosyası olmalıdır.")
    if resolved.stat().st_size > MAX_PROFILE_BYTES:
        raise DfmProfileError("DFM Profile 1 MiB güvenlik sınırını aşıyor.")
    return resolved


def load_profile(value: str | Path | dict[str, Any], *, allowed_root: Path | None = None) -> dict[str, Any]:
    """@brief Load a Profile from memory or a restricted JSON file."""
    if isinstance(value, dict):
        return validate_profile(value)
    path = _resolve_profile_path(Path(value), allowed_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DfmProfileError(f"DFM Profile okunamadı: {exc}") from exc
    profile = validate_profile(payload)
    profile["profilePath"] = str(path)
    profile["fileSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return profile


def load_profiles(
    values: Iterable[str | Path | dict[str, Any]] | None,
    *,
    allowed_root: Path | None = None,
) -> list[dict[str, Any]]:
    """@brief Load profiles and reject duplicate IDs."""
    profiles = [load_profile(value, allowed_root=allowed_root) for value in (values or [])]
    ids = [profile["id"] for profile in profiles]
    if len(ids) != len(set(ids)):
        raise DfmProfileError("DFM Profile id yinelenemez.")
    return profiles


def _intersect_casefold(left: list[str], right: list[str]) -> list[str]:
    """@brief Intersect material sets case-insensitively."""
    right_tokens = {item.casefold() for item in right}
    return [item for item in left if item.casefold() in right_tokens]


def merge_profiles(profiles: list[dict[str, Any]], process: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """@brief Intersect applicable profile capabilities for a process.

    Maximize minimum requirements, minimize maximum capabilities and per-axis
    equipment space, and intersect materials/tools. Later profiles therefore
    cannot silently weaken earlier constraints.
    """
    effective: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for profile in profiles:
        applicable = not profile["processes"] or process in profile["processes"]
        record = {
            "id": profile["id"],
            "schema": profile["schema"],
            "version": profile["version"],
            "source": profile["source"],
            "sha256": profile["sha256"],
            "fileSha256": profile.get("fileSha256"),
            "applicable": applicable,
            "processes": profile["processes"],
            "appliedLimits": [],
        }
        if not applicable:
            record["reason"] = f"Profile şu öğe için uygun değil: {process}."
            records.append(record)
            continue
        for key, value in profile["limits"].items():
            if key in _MINIMUM_LIMITS:
                effective[key] = max(float(effective.get(key, 0)), float(value))
            elif key in _MAXIMUM_LIMITS:
                effective[key] = min(float(effective.get(key, value)), float(value))
            elif key in _ENVELOPE_LIMITS:
                current = effective.get(key)
                effective[key] = list(value) if current is None else [min(current[index], value[index]) for index in range(3)]
            elif key == "allowedMaterials":
                effective[key] = list(value) if key not in effective else _intersect_casefold(effective[key], value)
            elif key == "availableToolDiameters":
                current = effective.get(key)
                effective[key] = list(value) if current is None else sorted(set(current) & set(value))
            elif key == "requiresBrepEvidence":
                effective[key] = bool(effective.get(key, False) or value)
            record["appliedLimits"].append(key)
        records.append(record)

    if "minimumThickness" in effective and "maximumThickness" in effective:
        if effective["minimumThickness"] > effective["maximumThickness"]:
            raise DfmProfileError("Birleştirilmiş minimum kalınlık maksimumdan büyük; Profile capability kesişimi boş.")
    if "minimumKerf" in effective and "maximumKerf" in effective:
        if effective["minimumKerf"] > effective["maximumKerf"]:
            raise DfmProfileError("Birleştirilmiş minimum kerf maksimumdan büyük; Profile capability kesişimi boş.")
    if "allowedMaterials" in effective and not effective["allowedMaterials"]:
        raise DfmProfileError("Profile malzeme capability kesişimi boş.")
    if "availableToolDiameters" in effective and not effective["availableToolDiameters"]:
        raise DfmProfileError("Profile takım çapı kesişimi boş.")
    return effective, records


__all__ = [
    "DfmProfileError",
    "PROFILE_SCHEMA",
    "PROFILE_VERSION",
    "load_profile",
    "load_profiles",
    "merge_profiles",
    "validate_profile",
]
