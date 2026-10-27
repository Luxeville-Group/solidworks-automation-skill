'Offline contracts and local capability probes for advanced SolidWorks fillets. Strictly validates variable-radius, hold-line, curvature-continuous face, full-round, setback and distance-distance chamfers. This module does not connect to SolidWorks; type-library probing reads local COM metadata only.'

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ADVANCED_KINDS = (
    "variable",
    "face",
    "hold_line",
    "surface_combo",
    "full_round",
    "setback",
    "width_width_chamfer",
)

REQUIRED_INTERFACES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "variable": {
        "IFeatureManager": ("FeatureFillet3",),
        "IVariableFilletFeatureData2": (
            "GetControlPointsCount",
            "GetControlPointRadiusAtIndex",
            "SetControlPointRadiusAtIndex",
        ),
    },
    "face": {
        "IFeatureManager": ("CreateDefinition", "CreateFeature"),
        "ISimpleFilletFeatureData2": ("Initialize", "SetFaces"),
    },
    "hold_line": {
        "IFeatureManager": ("CreateDefinition", "CreateFeature"),
        "ISimpleFilletFeatureData2": (
            "Initialize",
            "SetFaces",
            "HoldLines",
            "GetHoldLineCount",
        ),
    },
    "surface_combo": {
        "IFeatureManager": ("CreateDefinition", "CreateFeature"),
        "ISimpleFilletFeatureData2": (
            "Initialize",
            "SetFaces",
            "CurvatureContinuous",
        ),
    },
    "full_round": {
        "IFeatureManager": ("CreateDefinition", "CreateFeature"),
        "ISimpleFilletFeatureData2": ("Initialize", "SetFaces"),
    },
    "setback": {
        "IFeatureManager": ("FeatureFillet3",),
        "ISimpleFilletFeatureData2": ("GetSetbackVerticesCount",),
    },
    "width_width_chamfer": {
        "IFeatureManager": ("InsertFeatureChamfer",),
        "IChamferFeatureData2": (
            "GetEdgeChamferDistance",
            "Type",
        ),
    },
}


@dataclass(frozen=True)
class VariableFilletSpec:
    'Single-edge variable-radius fillet parameters, with lengths in millimeters.'

    start_radius: float = 2.0
    end_radius: float = 5.0
    control_points: tuple[tuple[float, float], ...] = ()
    transition: str = "smooth"
    overflow: str = "default"


@dataclass(frozen=True)
class FaceFilletSpec:
    'Face-fillet parameters for two adjacent face sets.'

    radius: float = 4.0
    propagate_tangent: bool = False
    overflow: str = "default"


@dataclass(frozen=True)
class HoldLineFilletSpec:
    'Face fillet defined by two face sets and one or more hold lines.'

    radius: float = 4.0
    hold_line_count: int = 1
    tangent_hold_line: bool = False
    propagate_tangent: bool = False


@dataclass(frozen=True)
class SurfaceCombinationSpec:
    'Curvature-continuous fillet parameters for plane/cylinder combinations.'

    radius: float = 3.0
    curvature_continuous: bool = True
    propagate_tangent: bool = False


@dataclass(frozen=True)
class FullRoundFilletSpec:
    'Full-round parameters for side set 1, center set and side set 2.'

    propagate_tangent: bool = False


@dataclass(frozen=True)
class SetbackFilletSpec:
    'Constant radius and per-edge setback distances for a three-edge corner.'

    radius: float = 3.0
    distances: tuple[float, float, float] = (4.0, 4.0, 4.0)
    overflow: str = "default"


@dataclass(frozen=True)
class WidthWidthChamferSpec:
    'Asymmetric distance-distance chamfer parameters.'

    width1: float = 2.0
    width2: float = 4.0
    propagate_tangent: bool = True


def _finite_positive(name: str, value: Any) -> float:
    'Return a finite positive number or raise a readable error.'
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} sayısal olmalıdır / must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} sonlu ve pozitif olmalıdır / must be finite and positive")
    return number


def validate_variable_spec(spec: VariableFilletSpec, *, edge_length_mm: float) -> dict[str, Any]:
    'Validate endpoint radii, control-point positions and transition mode.'
    edge_length = _finite_positive("edge_length_mm", edge_length_mm)
    radii = [
        _finite_positive("start_radius", spec.start_radius),
        _finite_positive("end_radius", spec.end_radius),
    ]
    controls: list[dict[str, float]] = []
    last_location = 0.0
    for index, item in enumerate(spec.control_points):
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(f"control_points[{index}] (konum oranı, yarıçap) olmalıdır / must be (position fraction, radius)")
        location = float(item[0])
        radius = _finite_positive(f"control_points[{index}].radius", item[1])
        if not math.isfinite(location) or not 0.0 < location < 1.0:
            raise ValueError('Kontrol noktası oranı 0 ile 1 arasında olmalıdır / Control-point fraction must be strictly between 0 and 1')
        if location <= last_location:
            raise ValueError('Kontrol noktası konumları kesin artan sırada olmalıdır / Control-point positions must strictly increase')
        last_location = location
        radii.append(radius)
        controls.append({"location": location, "radius_mm": radius})
    if spec.transition not in {"smooth", "straight"}:
        raise ValueError('transition, smooth veya straight olmalıdır / transition must be smooth or straight')
    if spec.overflow not in {"default", "keep_edge", "keep_surface"}:
        raise ValueError('Geçersiz overflow değeri / Invalid overflow value')
    if max(radii) * 2.0 >= edge_length:
        raise ValueError('En büyük radyüs çapı hedef kenardan kısa olmalıdır / Maximum fillet diameter must be smaller than the target edge length')
    return {
        "status": "pass",
        "kind": "variable",
        "endpoint_radii_mm": radii[:2],
        "control_points": controls,
        "edge_length_mm": edge_length,
    }


def validate_face_spec(spec: FaceFilletSpec, *, clearance_mm: float) -> dict[str, Any]:
    'Validate face-fillet radius against the available adjacent-face envelope.'
    radius = _finite_positive("radius", spec.radius)
    clearance = _finite_positive("clearance_mm", clearance_mm)
    if radius >= clearance:
        raise ValueError('Yüz radyüsü iki yüzün boşluğundan küçük olmalıdır / Face-fillet radius must be below both face clearances')
    if spec.overflow not in {"default", "keep_edge", "keep_surface"}:
        raise ValueError('Geçersiz overflow değeri / Invalid overflow value')
    return {"status": "pass", "kind": "face", "radius_mm": radius}


def validate_hold_line_spec(
    spec: HoldLineFilletSpec,
    *,
    clearance_mm: float,
    available_hold_lines: int,
) -> dict[str, Any]:
    'Validate hold-line count and face-set clearance.'
    radius = _finite_positive("radius", spec.radius)
    clearance = _finite_positive("clearance_mm", clearance_mm)
    requested = int(spec.hold_line_count)
    available = int(available_hold_lines)
    if requested <= 0:
        raise ValueError('hold_line_count pozitif tam sayı olmalıdır / hold_line_count must be a positive integer')
    if available != requested:
        raise ValueError('Aday tutma çizgisi adedi istekle eşleşmelidir / Candidate hold-line count must match the request')
    if radius >= clearance:
        raise ValueError('Tutma çizgisi radyüsü iki yüzün boşluğundan küçük olmalıdır / Hold-line radius must be below both face clearances')
    return {
        "status": "pass",
        "kind": "hold_line",
        "radius_mm": radius,
        "hold_line_count": requested,
        "tangent_hold_line": bool(spec.tangent_hold_line),
    }


def validate_surface_combination_spec(
    spec: SurfaceCombinationSpec,
    *,
    clearance_mm: float,
    surface_types: tuple[str, str],
) -> dict[str, Any]:
    'Validate two explicit surface types for a curvature-continuous fillet.'
    radius = _finite_positive("radius", spec.radius)
    clearance = _finite_positive("clearance_mm", clearance_mm)
    normalized = tuple(str(item).strip().lower() for item in surface_types)
    if len(normalized) != 2 or any(not item for item in normalized):
        raise ValueError('İki tanınabilir yüzey türü gerekir / Two identifiable surface types are required')
    if len(set(normalized)) != 2:
        raise ValueError('İki farklı yüzey türü gerekir / Two different surface types are required')
    if radius >= clearance:
        raise ValueError('Yüzey birleşimi radyüsü kullanılabilir boşluktan küçük olmalıdır / Surface-combination radius must be below available clearance')
    if not spec.curvature_continuous:
        raise ValueError('surface_combo için eğrilik sürekliliği etkin olmalıdır / surface_combo requires curvature continuity')
    return {
        "status": "pass",
        "kind": "surface_combo",
        "radius_mm": radius,
        "curvature_continuous": True,
        "surface_types": list(normalized),
    }


def validate_full_round_spec(
    _spec: FullRoundFilletSpec,
    *,
    face_set_counts: tuple[int, int, int],
) -> dict[str, Any]:
    'Validate nonempty, distinct full-round face sets.'
    if len(face_set_counts) != 3 or any(int(count) <= 0 for count in face_set_counts):
        raise ValueError('Full-round için iki yan ve bir merkez yüz grubu boş olmamalıdır / Full-round requires nonempty side set 1, center and side set 2')
    return {
        "status": "pass",
        "kind": "full_round",
        "face_set_counts": list(face_set_counts),
    }


def validate_setback_spec(
    spec: SetbackFilletSpec,
    *,
    incident_edge_lengths_mm: Iterable[float],
) -> dict[str, Any]:
    'Validate one-to-one correspondence between three intersecting edges and setbacks.'
    radius = _finite_positive("radius", spec.radius)
    lengths = [_finite_positive("incident_edge_length", item) for item in incident_edge_lengths_mm]
    distances = [_finite_positive("setback_distance", item) for item in spec.distances]
    if len(lengths) != 3 or len(distances) != 3:
        raise ValueError('Setback yolu tam üç kenar ve üç mesafe gerektirir / Stable setback path requires exactly three edges and three distances')
    for index, (distance, length) in enumerate(zip(distances, lengths)):
        if distance >= length:
            raise ValueError(f"Setback mesafesi / distance[{index}] ilgili kenardan kısa olmalıdır / must be smaller than the corresponding edge length")
    if radius >= min(lengths) / 2.0:
        raise ValueError('Setback radyüsü en kısa kenarın yarısından küçük olmalıdır / Setback radius must be below half the shortest intersecting edge')
    return {
        "status": "pass",
        "kind": "setback",
        "radius_mm": radius,
        "distances_mm": distances,
        "incident_edge_lengths_mm": lengths,
    }


def validate_width_width_chamfer_spec(
    spec: WidthWidthChamferSpec,
    *,
    adjacent_clearances_mm: tuple[float, float],
) -> dict[str, Any]:
    'Validate both chamfer distances against adjacent-face clearance.'
    width1 = _finite_positive("width1", spec.width1)
    width2 = _finite_positive("width2", spec.width2)
    if len(adjacent_clearances_mm) != 2:
        raise ValueError('Mesafe-mesafe pah için iki tarafın boşluğu gerekir / Distance-distance chamfer requires both side clearances')
    clearances = tuple(
        _finite_positive(f"adjacent_clearances_mm[{index}]", value)
        for index, value in enumerate(adjacent_clearances_mm)
    )
    for index, (width, clearance) in enumerate(zip((width1, width2), clearances), start=1):
        if width >= clearance:
            raise ValueError(f"width{index} ilgili taraf boşluğundan küçük olmalıdır / must be below the corresponding side clearance")
    return {
        "status": "pass",
        "kind": "width_width_chamfer",
        "widths_mm": [width1, width2],
        "adjacent_clearances_mm": list(clearances),
        "asymmetric": not math.isclose(width1, width2),
    }


def inspect_typelib_members(type_library_path: Path) -> dict[str, set[str]]:
    'Read the SolidWorks type library and return interface member sets.'
    try:
        import pythoncom
    except ImportError as exc:  # pragma: no cover - non-Windows CI path
        raise RuntimeError('pywin32 eksik; SolidWorks tür kitaplığı okunamıyor / Missing pywin32; cannot read SolidWorks type library') from exc
    path = Path(type_library_path)
    if not path.is_file():
        raise FileNotFoundError(f"SolidWorks tür kitaplığı bulunamadı / Type library missing: {path}")
    library = pythoncom.LoadTypeLib(str(path))
    interfaces: dict[str, set[str]] = {}
    wanted = {name for requirements in REQUIRED_INTERFACES.values() for name in requirements}
    for index in range(library.GetTypeInfoCount()):
        info = library.GetTypeInfo(index)
        name = library.GetDocumentation(index)[0]
        if name not in wanted:
            continue
        attributes = info.GetTypeAttr()
        interfaces[name] = {
            info.GetNames(info.GetFuncDesc(member_index).memid)[0]
            for member_index in range(attributes.cFuncs)
        }
    return interfaces


def build_capability_report(
    interfaces: Mapping[str, Iterable[str]],
    *,
    source: str,
) -> dict[str, Any]:
    'Generate auditable per-capability reports against exact interface contracts.'
    normalized = {name: set(members) for name, members in interfaces.items()}
    capabilities: dict[str, Any] = {}
    for kind, requirements in REQUIRED_INTERFACES.items():
        missing: list[str] = []
        present: list[str] = []
        for interface, members in requirements.items():
            found = normalized.get(interface, set())
            for member in members:
                qualified = f"{interface}.{member}"
                (present if member in found else missing).append(qualified)
        capabilities[kind] = {
            "status": "interface_ready" if not missing else "blocked",
            "present": present,
            "missing": missing,
        }
    return {
        "schema_version": 1,
        "source": source,
        "capabilities": capabilities,
        "note": 'interface_ready yalnızca arayüzün varlığını gösterir; verified için gerçek CAD kanıtı gerekir / interface_ready only proves interface availability; verified requires native modeling evidence.',
    }


def spec_payload(spec: Any, validation: Mapping[str, Any]) -> dict[str, Any]:
    'Convert immutable parameters to a JSON-friendly execution plan.'
    return {
        "schema_version": 1,
        "spec": asdict(spec),
        "validation": dict(validation),
    }
