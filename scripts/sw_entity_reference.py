"""SOLIDWORKS semantic entity references.

Combine feature name, entity type, and geometry signature into auditable references, reducing dependence on Face1/Edge1 and screen coordinates. Do not guess COM APIs; callers supply candidate entity metadata.
"""
from __future__ import annotations

import hashlib
import json
import numbers
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class SemanticEntityReference:
    """@brief Serializable semantic entity reference."""

    entity_type: str
    feature_name: str | None = None
    geometry_signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """@brief Convert to task evidence JSON."""
        return asdict(self)


def geometry_signature(values: Any, precision: int = 6) -> str:
    """@brief Hash geometry summaries stably instead of storing screen coordinates in tasks."""

    def normalize(value: Any) -> Any:
        if isinstance(value, numbers.Real) and not isinstance(value, bool):
            return round(float(value), precision)
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): normalize(value[key]) for key in sorted(value, key=str)}
        return value

    canonical = json.dumps(normalize(values), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def reference_from_metadata(entity_type: str, feature_name: str | None = None, geometry: Any = None) -> SemanticEntityReference:
    """@brief Build a reference from feature name, type, and geometry summary."""
    return SemanticEntityReference(
        entity_type=str(entity_type),
        feature_name=str(feature_name) if feature_name else None,
        geometry_signature=geometry_signature(geometry) if geometry is not None else None,
    )


def resolve_semantic_reference(
    reference: SemanticEntityReference,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """@brief Resolve candidates by type, feature name, and geometry signature."""
    scored: list[tuple[int, Mapping[str, Any]]] = []
    for candidate in candidates:
        score = 0
        if str(candidate.get("entity_type", candidate.get("type", ""))) == reference.entity_type:
            score += 4
        if reference.feature_name and candidate.get("feature_name", candidate.get("name")) == reference.feature_name:
            score += 3
        if reference.geometry_signature and candidate.get("geometry_signature") == reference.geometry_signature:
            score += 5
        if score:
            scored.append((score, candidate))
    if not scored:
        return {"status": "not_found", "reference": reference.to_dict(), "candidates": []}
    best_score = max(score for score, _ in scored)
    best = [candidate for score, candidate in scored if score == best_score]
    if len(best) != 1:
        return {"status": "ambiguous", "score": best_score, "reference": reference.to_dict(), "candidates": [dict(item) for item in best]}
    return {"status": "resolved", "score": best_score, "reference": reference.to_dict(), "entity": dict(best[0])}
