"""Design-specification validation regression tests."""
import json

import pytest

from scripts.design_spec import (
    DesignSpecError,
    compare_verification,
    load_design_spec,
    to_mm,
    unit_scale,
    validate_design_spec,
)


def minimal_spec(**overrides):
    """Build a minimal valid specification."""
    spec = {
        "schema_version": "1.0",
        "part_name": "bracket",
        "units": "mm",
        "base": {"type": "rect_plate", "width": 100, "height": 60, "thickness": 6},
        "holes": [{"id": "H1", "type": "through", "diameter": 6.6, "position": [10, 10]}],
    }
    spec.update(overrides)
    return spec


def test_valid_spec_passes():
    """Valid specifications pass and return normalized results."""
    result = validate_design_spec(minimal_spec())

    assert result["status"] == "ok"
    assert result["errors"] == []
    normalized = result["normalized"]
    assert normalized["part_name"] == "bracket"
    assert normalized["base"]["width_mm"] == 100.0
    assert normalized["holes"][0]["diameter_mm"] == 6.6


def test_units_are_normalized_to_mm():
    """Convert inch specifications to millimeters to avoid 25.4x errors."""
    spec = minimal_spec(
        units="in",
        base={"type": "rect_plate", "width": 2.0, "height": 1.0, "thickness": 0.25},
    )
    result = validate_design_spec(spec)

    assert result["status"] == "ok"
    base = result["normalized"]["base"]
    assert base["width_mm"] == pytest.approx(50.8)
    assert base["height_mm"] == pytest.approx(25.4)
    assert base["thickness_mm"] == pytest.approx(6.35)


def test_unsupported_unit_is_rejected():
    """Reject unknown units rather than silently treating them as millimeters."""
    result = validate_design_spec(minimal_spec(units="furlong"))

    assert result["status"] == "error"
    assert any(item["code"] == "SPEC_UNIT_UNSUPPORTED" for item in result["errors"])


def test_all_errors_reported_at_once():
    """Return all issues together instead of forcing repeated trial and error."""
    spec = minimal_spec(
        base={"type": "rect_plate", "width": -1, "height": 0, "thickness": 6},
        holes=[{"id": "H1", "type": "wrong_type", "diameter": 6.6, "position": [10, 10]}],
    )
    result = validate_design_spec(spec)

    assert result["status"] == "error"
    assert len(result["errors"]) >= 3


def test_duplicate_hole_id_is_rejected():
    """Duplicate hole IDs prevent traceability and must fail validation."""
    spec = minimal_spec(holes=[
        {"id": "H1", "type": "through", "diameter": 6.6, "position": [10, 10]},
        {"id": "H1", "type": "through", "diameter": 6.6, "position": [20, 10]},
    ])
    result = validate_design_spec(spec)

    assert any(item["code"] == "SPEC_HOLE_ID_DUPLICATE" for item in result["errors"])


def test_hole_without_id_gets_generated_id_and_warning():
    """Fill missing IDs automatically while recommending explicit user naming."""
    spec = minimal_spec(holes=[{"type": "through", "diameter": 6.6, "position": [10, 10]}])
    result = validate_design_spec(spec)

    assert result["status"] == "ok"
    assert result["normalized"]["holes"][0]["id"] == "H1"
    assert any("id verilmedi" in warning for warning in result["warnings"])


def test_blind_hole_requires_depth():
    """Blind holes require depth."""
    spec = minimal_spec(holes=[{"id": "H1", "type": "blind", "diameter": 5.0, "position": [10, 10]}])
    result = validate_design_spec(spec)

    assert any(item["code"] == "SPEC_FIELD_MISSING" for item in result["errors"])


def test_counterbore_requires_extra_fields():
    """Counterbores require bore diameter and depth."""
    spec = minimal_spec(holes=[{"id": "H1", "type": "counterbore", "diameter": 6.6, "position": [10, 10]}])
    result = validate_design_spec(spec)

    codes = {item["code"] for item in result["errors"]}
    assert "SPEC_FIELD_MISSING" in codes
    assert len(result["errors"]) >= 2


def test_oversized_fillet_radius_warns():
    """Fillet radii exceeding half the plate thickness produce a DFM warning."""
    spec = minimal_spec(fillets=[{"radius": 10, "axis": "z"}])
    result = validate_design_spec(spec)

    assert result["status"] == "ok"
    assert any('levha kalınlığının' in warning for warning in result["warnings"])


def test_conflicting_fillet_flags_rejected():
    """Reject simultaneous convex_only and concave_only flags."""
    spec = minimal_spec(fillets=[{"radius": 2, "convex_only": True, "concave_only": True}])
    result = validate_design_spec(spec)

    assert any(item["code"] == "SPEC_FILLET_FLAGS" for item in result["errors"])


def test_schema_version_mismatch_warns_but_proceeds():
    """Version mismatches warn without blocking."""
    result = validate_design_spec(minimal_spec(schema_version="0.9"))

    assert result["status"] == "ok"
    assert any("schema_version" in warning for warning in result["warnings"])


def test_too_many_holes_rejected():
    """Reject hole counts above the limit to prevent excessive geometry."""
    spec = minimal_spec(holes=[
        {"id": f"H{index}", "type": "through", "diameter": 3.0, "position": [index, 0]}
        for index in range(250)
    ])
    result = validate_design_spec(spec)

    assert any(item["code"] == "SPEC_HOLES_TOO_MANY" for item in result["errors"])


def test_non_dict_spec_rejected():
    """Non-object inputs fail with an explicit error."""
    result = validate_design_spec(["not", "a", "spec"])

    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "SPEC_NOT_OBJECT"


def test_empty_spec_rejected():
    """Reject specifications without geometry rather than create empty documents."""
    result = validate_design_spec({"schema_version": "1.0", "units": "mm"})

    assert any(item["code"] == "SPEC_EMPTY" for item in result["errors"])


def test_base_type_none_is_allowed():
    """Explicit base.type=none creates only subsequent features such as holes."""
    result = validate_design_spec(minimal_spec(base={"type": "none"}))

    assert result["status"] == "ok"


def test_load_spec_missing_file():
    """Missing files return clear errors rather than uncaught exceptions."""
    result = load_design_spec("definitely/not/here.json")

    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "SPEC_FILE_MISSING"


def test_load_spec_invalid_json(tmp_path):
    """Catch and report JSON syntax errors."""
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    result = load_design_spec(path)

    assert result["errors"][0]["code"] == "SPEC_JSON_INVALID"


def test_load_spec_round_trip(tmp_path):
    """Read a valid specification from disk."""
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(minimal_spec()), encoding="utf-8")

    result = load_design_spec(path)

    assert result["status"] == "ok"
    assert result["source_path"].endswith("spec.json")


def test_unit_scale_and_to_mm():
    """Test the unit-conversion function directly."""
    assert unit_scale("mm") == 1.0
    assert unit_scale("IN") == 25.4
    assert to_mm(2, "in") == pytest.approx(50.8)
    with pytest.raises(DesignSpecError):
        unit_scale("stone")


# Verification comparisons

def test_compare_verification_passes_on_match():
    """Matching actual and expected measurements pass."""
    result = compare_verification(
        {"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 4, "mass_g": 500.0},
        {"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 4, "tolerance_mm": 0.1},
    )

    assert result["status"] == "pass"
    assert result["failed"] == []


def test_compare_verification_flags_dimension_mismatch():
    """Out-of-tolerance dimensions warn and require manual review."""
    result = compare_verification(
        {"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 4},
        {"envelope_mm": [120.0, 60.0, 6.0], "hole_count": 4, "tolerance_mm": 0.1},
    )

    assert result["status"] == "warn"
    assert "envelope_mm" in result["failed"]
    assert result["manual_review_required"] is True


def test_compare_verification_tolerance_is_honoured():
    """Deviations within tolerance pass."""
    result = compare_verification(
        {"envelope_mm": [100.05, 60.0, 6.0], "hole_count": 4},
        {"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 4, "tolerance_mm": 0.1},
    )

    assert result["status"] == "pass"


def test_compare_verification_skipped_without_expectations():
    """Missing verify sections are explicitly skipped rather than reported as passing."""
    result = compare_verification({"envelope_mm": [1, 2, 3]}, {})

    assert result["status"] == "skipped"


def test_compare_verification_reports_unreadable_geometry():
    """Unreadable geometry fails the check rather than passing by default."""
    result = compare_verification(
        {"envelope_mm": None, "hole_count": 2},
        {"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 2},
    )

    assert result["status"] == "warn"
    assert "envelope_mm" in result["failed"]


def test_compare_verification_mass_bounds():
    """Validate mass lower and upper bounds independently."""
    result = compare_verification(
        {"mass_g": 400.0},
        {"min_mass_g": 300.0, "max_mass_g": 500.0},
    )
    assert result["status"] == "pass"

    too_heavy = compare_verification({"mass_g": 900.0}, {"max_mass_g": 500.0})
    assert too_heavy["status"] == "warn"
