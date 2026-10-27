"""Offline engineering-logic regression tests for solidworks-fillet-chamfer-cnc."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "subskills" / "solidworks-fillet-chamfer-cnc" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import cnc_strategy as strategy  # noqa: E402
import advanced_fillet_strategy as advanced  # noqa: E402
import hold_line_bridge as hold_bridge  # noqa: E402


def test_default_parameters_pass_and_keep_dowels_clear_of_center_slot() -> None:
    """Default locating holes must no longer intersect the center slot."""
    params, report = strategy.build_parameters()

    assert report["errors"] == []
    assert report["status"] == "pass_with_warnings"
    assert strategy.parameter_positions(params)["dowel"] == [(-0.0, -24.0), (0.0, 24.0)]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"dowel_hole_x": 32.0, "dowel_hole_y": 0.0}, "center slot"),
        ({"counterbore_diameter": 6.0}, "counterbore_diameter"),
        ({"counterbore_depth": 16.0}, "minimum_bottom_wall"),
        ({"pocket_center_x": 55.0}, "Pocket exceeds"),
        ({"chamfer_angle_deg": 90.0}, "chamfer_angle_deg"),
        ({"base_corner_radius": float("nan")}, "finite"),
    ],
)
def test_invalid_engineering_parameters_block_before_com(overrides, message) -> None:
    """Block hole/slot collisions and unmanufacturable dimensions before COM calls."""
    with pytest.raises(ValueError, match=message):
        strategy.build_parameters(overrides)


def test_rectangle_pocket_is_allowed_but_requires_dfm_warning() -> None:
    """A sharp rectangular pocket must not be reported as CNC friendly."""
    _params, report = strategy.build_parameters({"pocket_shape": "rectangle"})

    assert any("sharp internal corner" in warning for warning in report["warnings"])


def test_operation_plan_has_exact_edge_counts_and_bounded_fallbacks() -> None:
    """Operation plans declare edge counts and limit fallback attempts and minimum values."""
    params, _report = strategy.build_parameters()
    progressive = strategy.build_operation_plan(params, "progressive")
    strict = strategy.build_operation_plan(params, "strict")

    by_name = {item["name"]: item for item in progressive}
    assert by_name["Fillet_Base_Corners"]["expected_edge_count"] == 4
    assert by_name["Chamfer_Top_Outer"]["expected_edge_count"] == 8
    assert by_name["Chamfer_Hole_Mouths"]["expected_edge_count"] == 6
    assert by_name["Fillet_Base_Corners"]["attempt_values_mm"] == [8.0, 6.0, 4.0]
    assert all(len(item["attempt_values_mm"]) == 1 for item in strict)


def test_zero_treatment_disables_operation_and_updates_expected_topology() -> None:
    """Disabling vertical-corner fillets restores the top-edge loop from eight edges to four."""
    params, _report = strategy.build_parameters(
        {"base_corner_radius": 0.0, "boss_corner_radius": 0.0}
    )
    plan = strategy.build_operation_plan(params)
    by_name = {item["name"]: item for item in plan}

    assert "Fillet_Base_Corners" not in by_name
    assert "Fillet_Boss_Corners" not in by_name
    assert by_name["Chamfer_Top_Outer"]["expected_edge_count"] == 4
    assert by_name["Chamfer_Boss_Top"]["expected_edge_count"] == 4


def test_set_parser_rejects_unknown_or_malformed_values() -> None:
    """Generic parameter overrides must not silently accept typos."""
    assert strategy.parse_set_values(["base_corner_radius=6"]) == {
        "base_corner_radius": 6.0
    }
    with pytest.raises(ValueError, match="Unknown parameter"):
        strategy.parse_set_values(["base_corner_raduis=6"])
    with pytest.raises(ValueError, match="name=value"):
        strategy.parse_set_values(["base_corner_radius"])


@pytest.mark.parametrize("basename", ["../escape", "folder/name", "bad:name", ".."])
def test_basename_cannot_escape_output_directory(basename) -> None:
    """Output basenames must not include paths or illegal Windows characters."""
    with pytest.raises(ValueError):
        strategy.validate_basename(basename)


def test_json_parameter_file_supports_wrapped_payload(tmp_path: Path) -> None:
    """VibeCAD and the desktop can reuse the parameters wrapper format."""
    path = tmp_path / "params.json"
    path.write_text(
        json.dumps({"schema_version": 2, "parameters": {"top_chamfer": 1.25}}),
        encoding="utf-8",
    )

    assert strategy.load_parameter_file(path) == {"top_chamfer": 1.25}


def test_dry_run_cli_writes_plan_without_solidworks(tmp_path: Path) -> None:
    """--dry-run generates a complete plan without COM modeling side effects."""
    script = SCRIPT_DIR / "create_cnc_mount_template.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--dry-run",
            "--failure-policy",
            "strict",
            "--set",
            "top_chamfer=1.25",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads((tmp_path / "CNC_Mount_Template_plan.json").read_text(encoding="utf-8"))

    assert "planned" in completed.stdout
    assert payload["schema_version"] == 2
    assert payload["failure_policy"] == "strict"
    assert payload["parameters"]["top_chamfer"] == pytest.approx(1.25)


def test_exact_edge_selection_refuses_ambiguous_topology(monkeypatch) -> None:
    """Unexpected match counts must prevent further fillet or chamfer creation."""
    spec = importlib.util.spec_from_file_location(
        "cnc_mount_template_for_test",
        SCRIPT_DIR / "create_cnc_mount_template.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class FakeModel:
        """Provide the minimal model interface required for exact edge selection."""

        def ClearSelection2(self, _clear_all):
            return True

    fake_edges = [object(), object()]
    monkeypatch.setattr(module, "matching_edges", lambda *_args: fake_edges)
    monkeypatch.setattr(module, "edge_signature", lambda _edge: {"curve": "line"})

    with pytest.raises(RuntimeError, match="expected=4, actual=2"):
        module.select_exact_edges(FakeModel(), lambda _edge: True, "base vertical", 4)


def test_reference_planes_are_hidden_before_review(monkeypatch) -> None:
    """Hide visible construction planes so they do not contaminate delivery previews."""
    spec = importlib.util.spec_from_file_location(
        "cnc_mount_template_hide_planes_test",
        SCRIPT_DIR / "create_cnc_mount_template.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    calls = []

    class FakeModel:
        """Provide the minimal model interface required to hide reference planes."""

        def ClearSelection2(self, clear_all):
            calls.append(("clear", clear_all))

    def fake_member(_model, name, *_args):
        calls.append(("member", name))
        return True

    monkeypatch.setattr(module, "get_com_member", fake_member)
    module.hide_reference_planes(FakeModel())

    assert ("member", "GetVisibilityOfConstructPlanes") in calls
    assert ("member", "ViewDispRefplanes") in calls


def test_progressive_treatment_records_actual_degraded_size(monkeypatch) -> None:
    """A None solver result may trigger planned fallback, but record actual dimensions."""
    spec = importlib.util.spec_from_file_location(
        "cnc_mount_template_fallback_test",
        SCRIPT_DIR / "create_cnc_mount_template.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class FakeFeature:
        """Simulate a feature created successfully on the second attempt."""

        Name = ""

    class FakeFeatureManager:
        """Return None first, then a feature."""

        def __init__(self):
            self.calls = 0
            self.feature = FakeFeature()

        def FeatureFillet(self, *_args):
            self.calls += 1
            return None if self.calls == 1 else self.feature

    class FakeModel:
        """Provide the minimal model interface required for fillet fallback."""

        def __init__(self):
            self.FeatureManager = FakeFeatureManager()

        def ClearSelection2(self, _clear_all):
            return True

        def ForceRebuild3(self, _top_only):
            return True

        def FeatureByName(self, name):
            return self.FeatureManager.feature if self.FeatureManager.feature.Name == name else None

    params, _report = strategy.build_parameters()
    operation = strategy.build_operation_plan(params, "progressive")[0]
    monkeypatch.setattr(module, "operation_predicate", lambda *_args: lambda _edge: True)
    monkeypatch.setattr(
        module,
        "select_exact_edges",
        lambda *_args: ([object()] * 4, [{"curve": "line"}] * 4),
    )

    evidence = module.apply_treatment(FakeModel(), operation, params)

    assert evidence["status"] == "degraded"
    assert evidence["requested_value_mm"] == 8.0
    assert evidence["actual_value_mm"] == 6.0
    assert [item["result"] for item in evidence["attempts"]] == [
        "feature_returned_none",
        "created_and_persisted",
    ]


def test_nonpersistent_feature_aborts_without_trying_smaller_size(monkeypatch) -> None:
    """A nonempty but unpersisted feature must not trigger another superimposed fillet attempt."""
    spec = importlib.util.spec_from_file_location(
        "cnc_mount_template_persistence_test",
        SCRIPT_DIR / "create_cnc_mount_template.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    class FakeFeature:
        """Simulate a nameable feature that cannot be read back from the tree."""

        Name = ""

    class FakeFeatureManager:
        """Record API call counts."""

        def __init__(self):
            self.calls = 0

        def FeatureFillet(self, *_args):
            self.calls += 1
            return FakeFeature()

    class FakeModel:
        """Simulate a feature disappearing after rebuild."""

        def __init__(self):
            self.FeatureManager = FakeFeatureManager()

        def ClearSelection2(self, _clear_all):
            return True

        def ForceRebuild3(self, _top_only):
            return True

        def FeatureByName(self, _name):
            return None

    params, _report = strategy.build_parameters()
    operation = strategy.build_operation_plan(params, "progressive")[0]
    model = FakeModel()
    monkeypatch.setattr(module, "operation_predicate", lambda *_args: lambda _edge: True)
    monkeypatch.setattr(
        module,
        "select_exact_edges",
        lambda *_args: ([object()] * 4, [{"curve": "line"}] * 4),
    )

    with pytest.raises(RuntimeError, match="further dimension attempts prohibited"):
        module.apply_treatment(model, operation, params)

    assert model.FeatureManager.calls == 1


def test_advanced_variable_contract_validates_order_and_geometry() -> None:
    """Variable-radius control points must be ordered and every radius must fit the target edge."""
    spec = advanced.VariableFilletSpec(
        start_radius=2.0,
        end_radius=5.0,
        control_points=((0.25, 3.0), (0.75, 4.0)),
    )

    report = advanced.validate_variable_spec(spec, edge_length_mm=60.0)

    assert report["endpoint_radii_mm"] == [2.0, 5.0]
    assert [item["location"] for item in report["control_points"]] == [0.25, 0.75]
    with pytest.raises(ValueError, match="strictly increase"):
        advanced.validate_variable_spec(
            advanced.VariableFilletSpec(control_points=((0.75, 3.0), (0.25, 4.0))),
            edge_length_mm=60.0,
        )
    with pytest.raises(ValueError, match="Maximum fillet diameter"):
        advanced.validate_variable_spec(
            advanced.VariableFilletSpec(start_radius=31.0, end_radius=2.0),
            edge_length_mm=60.0,
        )


def test_face_and_full_round_contracts_reject_invalid_envelopes() -> None:
    """Face-fillet clearance and all three full-round face groups must be complete."""
    assert advanced.validate_face_spec(
        advanced.FaceFilletSpec(radius=4.0), clearance_mm=16.0
    )["status"] == "pass"
    with pytest.raises(ValueError, match="both face clearances"):
        advanced.validate_face_spec(
            advanced.FaceFilletSpec(radius=16.0), clearance_mm=16.0
        )
    with pytest.raises(ValueError, match="requires nonempty side set"):
        advanced.validate_full_round_spec(
            advanced.FullRoundFilletSpec(), face_set_counts=(1, 0, 1)
        )


def test_hold_line_surface_combo_and_width_width_contracts() -> None:
    """Advanced paths reject mismatched counts, surface types, and envelopes."""
    hold = advanced.validate_hold_line_spec(
        advanced.HoldLineFilletSpec(radius=4.0, hold_line_count=1),
        clearance_mm=16.0,
        available_hold_lines=1,
    )
    assert hold["hold_line_count"] == 1
    with pytest.raises(ValueError, match='count must match'):
        advanced.validate_hold_line_spec(
            advanced.HoldLineFilletSpec(hold_line_count=2),
            clearance_mm=16.0,
            available_hold_lines=1,
        )

    surface = advanced.validate_surface_combination_spec(
        advanced.SurfaceCombinationSpec(radius=3.0),
        clearance_mm=15.0,
        surface_types=("plane", "cylinder"),
    )
    assert surface["curvature_continuous"] is True
    with pytest.raises(ValueError, match="different surface types"):
        advanced.validate_surface_combination_spec(
            advanced.SurfaceCombinationSpec(),
            clearance_mm=15.0,
            surface_types=("plane", "plane"),
        )

    chamfer = advanced.validate_width_width_chamfer_spec(
        advanced.WidthWidthChamferSpec(width1=2.0, width2=4.0),
        adjacent_clearances_mm=(15.0, 16.0),
    )
    assert chamfer["widths_mm"] == [2.0, 4.0]
    with pytest.raises(ValueError, match="must be below the corresponding side clearance"):
        advanced.validate_width_width_chamfer_spec(
            advanced.WidthWidthChamferSpec(width1=15.0, width2=4.0),
            adjacent_clearances_mm=(15.0, 16.0),
        )


def test_hold_line_multilanguage_probe_is_safe_by_default(monkeypatch) -> None:
    """Block known faulty builds by default while retaining cross-language and explicit retest evidence."""
    monkeypatch.delenv(hold_bridge.UNSAFE_HOLD_LINE_ENV, raising=False)

    with pytest.raises(hold_bridge.HoldLineBridgeError) as caught:
        hold_bridge.create_hold_line_via_native_addin(object(), "fixture.SLDPRT")

    evidence = caught.value.evidence
    assert evidence["status"] == "blocked"
    assert evidence["reason"] == "known_server_fault"
    assert evidence["failure_boundary"].endswith("ISetHoldLines")
    assert any("C#" in backend for backend in evidence["tested_backends"])
    assert any("native C++" in backend for backend in evidence["tested_backends"])
    assert evidence["unsafe_opt_in"].endswith("=1")
    hold_bridge._require_unsafe_probe(
        "native-cpp-swb", False, solidworks_revision="33.5.0"
    )


def test_native_hold_line_bridge_has_one_in_process_responsibility() -> None:
    """The native bridge retains only deferred UI writes; do not restore registry or Add-in experiment paths."""
    source = (
        SCRIPT_DIR / "native" / "NativeHoldLineAddin.cpp"
    ).read_text(encoding="utf-8")

    assert "ISetHoldLines" in source
    assert "SetTimer" in source
    assert "DllRegisterServer" not in source
    assert "RegCreateKey" not in source
    assert "CreateFeature(" not in source


def test_open_source_complex_regression_contract_is_reproducible() -> None:
    """Complex examples must pin the MIT source, four control points, and unequal-width chamfer read-back."""
    source = (SCRIPT_DIR / "verify_open_source_bracket.py").read_text(encoding="utf-8")

    assert "archimedes-market/parametric-bracket-library" in source
    assert 'SOURCE_LICENSE = "MIT"' in source
    assert "SOURCE_SHA256" in source
    assert "Input STEP hash mismatch" in source
    assert "GetControlPointsCount" in source
    assert "== 4" in source
    assert "_advanced_evidence_passes(before)" in source


def test_setback_contract_preserves_one_to_one_distance_mapping() -> None:
    """Setback distance arrays must correspond one-to-one with the three meeting edges."""
    report = advanced.validate_setback_spec(
        advanced.SetbackFilletSpec(radius=3.0, distances=(4.0, 5.0, 6.0)),
        incident_edge_lengths_mm=(60.0, 40.0, 18.0),
    )

    assert report["distances_mm"] == [4.0, 5.0, 6.0]
    with pytest.raises(ValueError, match="exactly three"):
        advanced.validate_setback_spec(
            advanced.SetbackFilletSpec(), incident_edge_lengths_mm=(60.0, 40.0)
        )
    with pytest.raises(ValueError, match="smaller than the corresponding edge length"):
        advanced.validate_setback_spec(
            advanced.SetbackFilletSpec(distances=(61.0, 5.0, 6.0)),
            incident_edge_lengths_mm=(60.0, 40.0, 18.0),
        )


def test_advanced_capability_report_never_equates_interface_with_verification() -> None:
    """Complete type-library members imply interface_ready, never native verified status."""
    interfaces = {
        interface: set(members)
        for requirements in advanced.REQUIRED_INTERFACES.values()
        for interface, members in requirements.items()
    }
    # Merge requirements on the same interface across capabilities.
    for requirements in advanced.REQUIRED_INTERFACES.values():
        for interface, members in requirements.items():
            interfaces.setdefault(interface, set()).update(members)

    report = advanced.build_capability_report(interfaces, source="mock.tlb")

    assert all(
        item["status"] == "interface_ready"
        for item in report["capabilities"].values()
    )
    assert "native" in report["note"]
    interfaces["ISimpleFilletFeatureData2"].remove("SetFaces")
    blocked = advanced.build_capability_report(interfaces, source="mock.tlb")
    assert blocked["capabilities"]["face"]["status"] == "blocked"
    assert blocked["capabilities"]["full_round"]["status"] == "blocked"


def test_setback_distance_array_is_explicit_double_safearray() -> None:
    """Setback must not fall back to an ordinary tuple silently rejected by SolidWorks."""
    spec = importlib.util.spec_from_file_location(
        "advanced_fillet_verifier_for_array_test",
        SCRIPT_DIR / "verify_advanced_fillets.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    value = module._double_array([0.001, 0.002, 0.003])

    assert value.varianttype == module.pythoncom.VT_ARRAY | module.pythoncom.VT_R8
    assert tuple(value.value) == pytest.approx((0.001, 0.002, 0.003))
