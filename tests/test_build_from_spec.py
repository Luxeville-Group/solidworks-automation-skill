"""Specification-executor regression tests. Two defects found in native runs are covered: (1) specifications use millimeters while sw_hole_features center/diameter/depth and sw_part.fillet require meters; passing millimeters directly creates a 1000x sketch and silent cut rejection (a 100 mm plate reached 13300 mm in testing). (2) A loop variable named fillet shadowed the function, making fillet(model, radius) call a dict. Tests patch dependencies locally with unittest.mock to avoid contaminating other modules."""
from pathlib import Path
import sys
import types
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.build_from_spec as build_from_spec  # noqa: E402


class FakeModel:
    """Document test double."""

    def __init__(self):
        self.rebuilds = 0
        self.cleared = 0

    def ForceRebuild3(self, _silent):
        self.rebuilds += 1
        return True

    def ClearSelection2(self, _all):
        self.cleared += 1
        return True


@pytest.fixture
def harness(monkeypatch):
    """Replace build_from_spec external dependencies and return a call-recording container. Patch only that module's bindings without affecting other test files."""
    record = {"holes": [], "part": []}

    def make_creator(kind):
        def creator(model, hole):
            record["holes"].append({"kind": kind, "hole": hole})
            return {"feature_kind": kind, "feature_names": (hole.get("id"),)}
        return creator

    def through(model, center=None, diameter=None, name='Delik', **kwargs):
        record["holes"].append({"kind": "through", "center": center, "diameter": diameter, "name": name})

        return {"feature_kind": "through", "feature_names": (name,), "center_m": center, "diameter_m": diameter}

    def blind(model, center=None, diameter=None, depth=None, name='Delik', **kwargs):
        record["holes"].append({"kind": "blind", "center": center, "diameter": diameter, "depth": depth, "name": name})
        return {"feature_kind": "blind", "feature_names": (name,)}

    def counterbore(model, center=None, hole_diameter=None, counterbore_diameter=None,
                    counterbore_depth=None, name='Delik', **kwargs):
        record["holes"].append({
            "kind": "counterbore", "center": center, "diameter": hole_diameter,
            "counterbore_diameter": counterbore_diameter,
            "counterbore_depth": counterbore_depth, "name": name,
        })
        return {"feature_kind": "counterbore", "feature_names": (name,)}

    def countersink(model, center=None, hole_diameter=None, countersink_diameter=None,
                    included_angle_deg=None, name='Delik', **kwargs):
        record["holes"].append({
            "kind": "countersink", "center": center, "diameter": hole_diameter,
            "countersink_diameter": countersink_diameter,
            "included_angle_deg": included_angle_deg, "name": name,
        })
        return {"feature_kind": "countersink", "feature_names": (name,)}

    monkeypatch.setattr(build_from_spec, "create_through_hole", through)
    monkeypatch.setattr(build_from_spec, "create_blind_hole", blind)
    monkeypatch.setattr(build_from_spec, "create_counterbore_hole", counterbore)
    monkeypatch.setattr(build_from_spec, "create_countersink_hole", countersink)

    def corner_rectangle(model, x1, y1, x2, y2):
        record["part"].append(("corner_rectangle", x1, y1, x2, y2))

    def circle(model, cx, cy, radius):
        record["part"].append(("circle", cx, cy, radius))

    def extrude_boss(model, sketch_name, depth, **kwargs):
        record["part"].append(("extrude_boss", sketch_name, depth))
        return types.SimpleNamespace(Name="Boss-Extrude1")

    def fillet(model, radius, edges=None):
        record["part"].append(("fillet", radius))
        return types.SimpleNamespace(Name="Fillet1")

    class FakeSketchManager:
        """Sketch context-manager test double."""

        def __init__(self, outer):
            self._outer = outer

        def __enter__(self):
            return "Sketch1"

        def __exit__(self, *_):
            return False

    def sketch(model, plane_name="Front Plane"):
        record["part"].append(("sketch", plane_name))
        return FakeSketchManager(record)

    monkeypatch.setattr(build_from_spec, "sketch_corner_rectangle", corner_rectangle)
    monkeypatch.setattr(build_from_spec, "sketch_circle", circle)
    monkeypatch.setattr(build_from_spec, "extrude_boss", extrude_boss)
    monkeypatch.setattr(build_from_spec, "fillet", fillet)
    monkeypatch.setattr(build_from_spec, "sketch", sketch)

    monkeypatch.setattr(
        build_from_spec, "select_edges",
        lambda model, spec: {"status": "ok", "selected_count": 4, "selected": []},
    )
    monkeypatch.setattr(
        build_from_spec.sw_measure, "collect_bounding_box",
        lambda model: {"size_mm": [100.0, 60.0, 6.0], "errors": []},
    )
    monkeypatch.setattr(
        build_from_spec.sw_measure, "collect_mass_properties",
        lambda model: {"mass_g": 500.0, "errors": []},
    )
    return record


def base_spec(**overrides):
    """Build a normalized specification."""
    spec = {
        "schema_version": "1.0",
        "part_name": "bracket",
        "source_units": "mm",
        "base": {"type": "rect_plate", "width_mm": 100.0, "height_mm": 60.0, "thickness_mm": 6.0},
        "holes": [],
        "fillets": [],
        "verify": {},
    }
    spec.update(overrides)
    return spec


def run(spec, harness, **kwargs):
    """Execute a build and return its result and recorded calls."""
    kwargs.setdefault("apply_fillets", False)
    kwargs.setdefault("verify_geometry", False)
    return build_from_spec.build_from_spec(FakeModel(), spec, **kwargs), harness


# Unit conversion

def test_hole_arguments_converted_to_metres(harness):
    """Hole center and diameter must convert from millimeters to meters. Without conversion, x=10 mm is treated as 10 m; a 100x60 mm plate reached 13300 mm in native testing."""
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0]}
    ])

    result, record = run(spec, harness)

    assert len(record["holes"]) == 1
    hole = record["holes"][0]
    assert hole["kind"] == "through"
    # Arguments passed into sw_hole_features must be meters.
    assert hole["center"] == pytest.approx((0.010, 0.010))
    assert hole["diameter"] == pytest.approx(0.0066)
    assert result["hole_count_created"] == 1


def test_hole_center_helper_converts_mm_to_m():
    """_hole_center_m is the single millimeter-to-meter conversion point and must be correct."""
    center = build_from_spec._hole_center_m({"position_mm": [10.0, 20.0, 0.0]})

    assert center == pytest.approx((0.010, 0.020))


def test_blind_hole_depth_converted_to_metres(harness):
    """Convert blind-hole depth to meters."""
    spec = base_spec(holes=[
        {"id": "H1", "type": "blind", "diameter_mm": 5.0, "depth_mm": 6.0, "position_mm": [10.0, 10.0, 0.0]}
    ])

    result, record = run(spec, harness)

    assert record["holes"][0]["depth"] == pytest.approx(0.006)
    assert result["hole_count_created"] == 1


def test_counterbore_dimensions_converted_to_metres(harness):
    """Convert all three counterbore dimension groups."""
    spec = base_spec(holes=[{
        "id": "H1", "type": "counterbore", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0],
        "counterbore_diameter_mm": 11.0, "counterbore_depth_mm": 6.0,
    }])

    result, record = run(spec, harness)

    hole = record["holes"][0]
    assert hole["kind"] == "counterbore"
    assert hole["diameter"] == pytest.approx(0.0066)
    assert hole["counterbore_diameter"] == pytest.approx(0.011)
    assert hole["counterbore_depth"] == pytest.approx(0.006)
    assert result["hole_count_created"] == 1


def test_countersink_angle_passed_through_unconverted(harness):
    """Countersink angles remain in degrees without unit conversion."""
    spec = base_spec(holes=[{
        "id": "H1", "type": "countersink", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0],
        "countersink_diameter_mm": 12.0, "angle_deg": 82.0,
    }])

    result, record = run(spec, harness)

    hole = record["holes"][0]
    assert hole["kind"] == "countersink"
    assert hole["countersink_diameter"] == pytest.approx(0.012)
    assert hole["included_angle_deg"] == 82.0
    assert result["hole_count_created"] == 1


def test_base_plate_origin_at_lower_left_corner(harness):
    """The plate origin is its lower-left corner so hole locations follow drawing coordinates. Previously centering the plate (-50..50) placed a 90 mm hole outside the plate."""
    result, record = run(base_spec(), harness)

    rectangle = next(call for call in record["part"] if call[0] == "corner_rectangle")
    assert rectangle[1:3] == pytest.approx((0.0, 0.0))
    assert rectangle[3:5] == pytest.approx((0.1, 0.06))


def test_base_plate_thickness_converted(harness):
    """Convert thickness to meters."""
    result, record = run(base_spec(), harness)

    extrude = next(call for call in record["part"] if call[0] == "extrude_boss")
    assert extrude[2] == pytest.approx(0.006)


def test_cylinder_base_diameter_converted(harness):
    """Convert cylinder diameter to meters; radius is half the diameter."""
    spec = base_spec(base={"type": "cylinder", "diameter_mm": 50.0, "height_mm": 80.0})

    result, record = run(spec, harness)

    circle = next(call for call in record["part"] if call[0] == "circle")
    assert circle[3] == pytest.approx(0.025)


# Bounds validation

def test_hole_outside_plate_is_rejected_before_building(harness):
    """Reject out-of-bounds hole positions before creation rather than report misleading feature-creation failures."""
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [200.0, 10.0, 0.0]}
    ])

    result, record = run(spec, harness)

    assert result["status"] == "error"
    assert any("levha sınırlarını aşıyor" in item for item in result["errors"])
    assert record["holes"] == []


def test_hole_touching_edge_is_rejected(harness):
    """A hole wall beyond the boundary counts as out of bounds even if its center is inside."""
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 20.0, "position_mm": [3.0, 30.0, 0.0]}
    ])

    result, _ = run(spec, harness)

    assert result["status"] == "error"
    assert any("levha sınırlarını aşıyor" in item for item in result["errors"])


def test_valid_corner_holes_pass_bounds_check(harness):
    """Four corner holes within the plate pass validation and are all created."""
    spec = base_spec(holes=[
        {"id": f"H{index}", "type": "through", "diameter_mm": 6.6, "position_mm": position + [0.0]}
        for index, position in enumerate([[10.0, 10.0], [90.0, 10.0], [10.0, 50.0], [90.0, 50.0]], start=1)
    ])

    result, _ = run(spec, harness)

    assert result["hole_count_created"] == 4
    assert result["errors"] == []


def test_cylinder_hole_outside_radius_rejected(harness):
    """Reject a hole outside the cylindrical base radius."""
    spec = base_spec(
        base={"type": "cylinder", "diameter_mm": 50.0, "height_mm": 10.0},
        holes=[{"id": "H1", "type": "through", "diameter_mm": 5.0, "position_mm": [40.0, 0.0, 0.0]}],
    )

    result, _ = run(spec, harness)

    assert any("silindir yarıçapını aşıyor" in item for item in result["errors"])


# Result classification

def test_hole_feature_names_key_is_read_correctly(harness):
    """HoleFeatureEvidence uses feature_names, not status/feature_name. The old implementation read a nonexistent status key and classified successful holes as failures."""
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0]}
    ])

    result, _ = run(spec, harness)

    assert result["hole_count_created"] == 1
    assert not any("oluşturulamadı" in item for item in result["errors"])
    step = next(item for item in result["steps"] if item["step"] == "hole")
    assert step["ok"] is True
    assert step["feature"] == "H1"


def test_missing_feature_names_marks_hole_failed(harness, monkeypatch):
    """Empty feature names mean failure, never success."""
    monkeypatch.setattr(
        build_from_spec, "create_through_hole",
        lambda model, hole: {"feature_kind": "through", "feature_names": ()},
    )
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0]}
    ])

    result, _ = run(spec, harness)

    assert result["status"] == "error"
    assert result["hole_count_created"] == 0


def test_creator_exception_is_recorded_not_raised(harness, monkeypatch):
    """Record an individual hole-creation exception and continue the remaining build."""

    def raising(model, center=None, diameter=None, name="H", **kwargs):
        if name == "H2":
            raise RuntimeError("boom")
        return {"feature_kind": "through", "feature_names": (name,)}

    monkeypatch.setattr(build_from_spec, "create_through_hole", raising)
    spec = base_spec(holes=[
        {"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0]},
        {"id": "H2", "type": "through", "diameter_mm": 6.6, "position_mm": [90.0, 10.0, 0.0]},
    ])

    result, _ = run(spec, harness)

    assert any("H2" in item for item in result["errors"])
    assert result["hole_count_created"] == 1


# Hole pattern expansion

def test_circular_pattern_expands_evenly():
    """Expand circular patterns at equal angles and renumber holes."""
    holes = [{
        "id": "B", "type": "through", "diameter_mm": 5.0, "position_mm": [0.0, 0.0, 0.0],
        "pattern": {"type": "circular", "count": 6, "radius": 30.0, "start_angle": 0.0},
    }]

    expanded = build_from_spec.expand_hole_patterns(holes)

    assert len(expanded) == 6
    assert expanded[0]["id"] == "B_1"
    assert expanded[0]["position_mm"][:2] == pytest.approx([30.0, 0.0])
    assert expanded[3]["position_mm"][:2] == pytest.approx([-30.0, 0.0], abs=1e-6)


def test_linear_pattern_expands_along_direction():
    """Expand linear patterns along dx/dy."""
    holes = [{
        "id": "L", "type": "through", "diameter_mm": 5.0, "position_mm": [10.0, 10.0, 0.0],
        "pattern": {"type": "linear", "count": 4, "dx": 20.0, "dy": 0.0},
    }]

    expanded = build_from_spec.expand_hole_patterns(holes)

    assert len(expanded) == 4
    assert [hole["position_mm"][0] for hole in expanded] == pytest.approx([10.0, 30.0, 50.0, 70.0])


def test_hole_without_pattern_is_copied_not_aliased():
    """Preserve unpatterned holes by copying rather than sharing references."""
    holes = [{"id": "H1", "type": "through", "diameter_mm": 5.0, "position_mm": [1.0, 2.0, 0.0]}]

    expanded = build_from_spec.expand_hole_patterns(holes)

    assert expanded[0] is not holes[0]
    assert expanded[0]["position_mm"] == [1.0, 2.0, 0.0]


def test_pattern_count_is_clamped():
    """Clamp abnormal pattern counts to avoid generating excessive geometry."""
    holes = [{
        "id": "B", "type": "through", "diameter_mm": 5.0, "position_mm": [0.0, 0.0, 0.0],
        "pattern": {"type": "circular", "count": 10**6, "radius": 30.0},
    }]

    expanded = build_from_spec.expand_hole_patterns(holes)

    assert len(expanded) <= 200


def test_unknown_pattern_type_preserves_original_hole():
    """Preserve the original hole when the pattern type is unknown."""
    holes = [{
        "id": "B", "type": "through", "diameter_mm": 5.0, "position_mm": [1.0, 2.0, 0.0],
        "pattern": {"type": "spiral", "count": 4},
    }]

    expanded = build_from_spec.expand_hole_patterns(holes)

    assert len(expanded) == 1
    assert expanded[0]["position_mm"] == [1.0, 2.0, 0.0]


# Fillets

def test_fillet_radius_converted_to_metres(harness):
    """Convert fillet radius to meters."""
    spec = base_spec(fillets=[{"radius_mm": 4.0, "axis": "z"}])

    result, record = run(spec, harness, apply_fillets=True)

    fillet_call = next(call for call in record["part"] if call[0] == "fillet")
    assert fillet_call[1] == pytest.approx(0.004)


def test_fillet_loop_variable_does_not_shadow_function(harness):
    """A loop variable named fillet previously shadowed the function, causing dict-not-callable errors. A recorded fillet call proves the function is no longer shadowed."""
    spec = base_spec(fillets=[{"radius_mm": 2.0, "axis": "z"}, {"radius_mm": 3.0, "axis": "z"}])

    result, record = run(spec, harness, apply_fillets=True)

    fillet_calls = [call for call in record["part"] if call[0] == "fillet"]
    assert len(fillet_calls) == 2
    assert [call[1] for call in fillet_calls] == pytest.approx([0.002, 0.003])


def test_fillet_skipped_when_no_edges_match(harness, monkeypatch):
    """Skip fillets with a clear message when no edges match; do not act silently on the current selection."""
    monkeypatch.setattr(
        build_from_spec, "select_edges",
        lambda model, spec: {"status": "error", "selected_count": 0, "errors": ["none"]},
    )
    spec = base_spec(fillets=[{"radius_mm": 4.0, "axis": "z"}])

    result, record = run(spec, harness, apply_fillets=True)

    assert any("kenar seçilmedi" in item for item in result["warnings"])
    assert not any(call[0] == "fillet" for call in record["part"])


def test_fillet_failure_is_warning_not_error(harness, monkeypatch):
    """Record a fillet failure as a warning without rolling back the existing solid."""
    def failing_fillet(model, radius, edges=None):
        raise RuntimeError("Radius too large")

    monkeypatch.setattr(build_from_spec, "fillet", failing_fillet)
    spec = base_spec(fillets=[{"radius_mm": 50.0, "axis": "z"}])

    result, _ = run(spec, harness, apply_fillets=True)

    assert any("Fillet 0 başarısız" in item for item in result["warnings"])
    assert result["status"] in ("ok", "warn")


# Verification

def test_verification_runs_and_reports(harness):
    """Compare actual measurements with expected values when verification is enabled."""
    spec = base_spec(
        holes=[{"id": "H1", "type": "through", "diameter_mm": 6.6, "position_mm": [10.0, 10.0, 0.0]}],
        verify={"envelope_mm": [100.0, 60.0, 6.0], "hole_count": 1, "tolerance_mm": 0.1},
    )

    result, _ = run(spec, harness, verify_geometry=True)

    assert result["verification"]["status"] == "pass"
    assert result["measurements"]["bounding_box"]["size_mm"] == [100.0, 60.0, 6.0]


def test_verification_flags_dimension_mismatch(harness, monkeypatch):
    """Dimension mismatches produce a warning and require review."""
    monkeypatch.setattr(
        build_from_spec.sw_measure, "collect_bounding_box",
        lambda model: {"size_mm": [999.0, 60.0, 6.0], "errors": []},
    )
    spec = base_spec(verify={"envelope_mm": [100.0, 60.0, 6.0], "tolerance_mm": 0.1})

    result, _ = run(spec, harness, verify_geometry=True)

    assert result["verification"]["status"] == "warn"
    assert "envelope_mm" in result["verification"]["failed"]


def test_base_none_skips_solid_creation(harness):
    """base.type=none creates only subsequent features."""
    spec = base_spec(base={"type": "none"})

    result, record = run(spec, harness)

    assert not any(call[0] == "extrude_boss" for call in record["part"])
    assert result["steps"][0]["ok"] is True


def test_mass_properties_included_in_measurements(harness):
    """Measurements include both bounding box and mass properties."""
    result, _ = run(base_spec(), harness, verify_geometry=True)

    assert result["measurements"]["mass_properties"]["mass_g"] == 500.0
