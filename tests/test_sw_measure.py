'Measurement regressions for units observed in native testing. GetPartBox(True) returns meters, as do IFeatureManager inputs; bounding-box values are meaningful only after correct conversion.'
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

sys.modules.setdefault(
    "sw_preflight",
    types.SimpleNamespace(
        import_com_dependencies=lambda: (
            types.SimpleNamespace(VT_DISPATCH=9, VT_BYREF=16384, VT_I4=3),
            types.SimpleNamespace(),
            lambda *args: None,
        )
    ),
)


def fake_get_com_member(obj, attr_name, *args):
    'Test COM reader supporting both properties and methods.'
    member = getattr(obj, attr_name)
    if args:
        return member(*args)
    if callable(member):
        try:
            return member()
        except TypeError:
            return member
    return member


sys.modules.setdefault(
    "sw_connect",
    types.SimpleNamespace(
        get_com_member=fake_get_com_member,
        create_empty_dispatch_variant=lambda: None,
        mm=lambda value: value / 1000.0,
        deg=lambda value: value * 3.141592653589793 / 180.0,
    ),
)

import sw_measure  # noqa: E402


class FakeMassProperty:
    'Mass-property stub; SW2024 SP5 was observed without a Status member.'

    def __init__(self, mass_kg=0.036, volume_m3=3.6e-05, area_m2=0.0139,
                 center_m=(0.05, 0.03, -0.003), has_status=False):
        self._mass = mass_kg
        self._volume = volume_m3
        self._area = area_m2
        self._center = center_m
        if has_status:
            self.Status = 1
        self.override_calls = []

    def Mass(self):
        return self._mass

    def Volume(self):
        return self._volume

    def SurfaceArea(self):
        return self._area

    def CenterOfMass(self):
        return list(self._center)

    def GetMomentOfInertia(self, _frame):
        return [1e-05] * 9

    def SetOverrideMass(self, enabled):
        self.override_calls.append(enabled)


class FakeModel:
    'Document stub.'

    def __init__(self, box_m=None, material=None, mass_property=None, box_raises=False,
                 density_kg_m3=1000.0):
        self._box_m = box_m
        self.MaterialIdName = material
        self._mass_property = mass_property or FakeMassProperty()
        self._box_raises = box_raises
        self._density = density_kg_m3
        self.preference_writes = []
        self.Extension = types.SimpleNamespace(CreateMassProperty=lambda: self._mass_property)

    def GetPartBox(self, use_system_units=True):
        if self._box_raises:
            raise RuntimeError("no geometry")
        return list(self._box_m or [])

    def GetUserPreferenceDoubleValue(self, preference):
        'Read the double preference swMaterialPropertyDensity=7.'
        assert preference == 7, f"Only the density preference is supported; received {preference}"
        return self._density

    def SetUserPreferenceDoubleValue(self, preference, value):
        'Write a double preference.'
        self.preference_writes.append((preference, float(value)))
        self._density = float(value)
        return True


# Bounding-box units

def test_bounding_box_meters_are_converted_to_mm():
    'GetPartBox(True) returns meters and must convert to mm. A native 100x60x6 mm plate returned [0,0,-0.006,0.1,0.06,0]; omitted conversion would yield 0.1/0.06/0.006.'
    model = FakeModel(box_m=[0.0, 0.0, -0.006, 0.1, 0.06, 0.0])

    result = sw_measure.collect_bounding_box(model)

    assert result["size_mm"] == pytest.approx([100.0, 60.0, 6.0])
    assert result["min_corner_mm"] == pytest.approx([0.0, 0.0, -6.0])
    assert result["max_corner_mm"] == pytest.approx([100.0, 60.0, 0.0])
    assert result["errors"] == []


def test_bounding_box_diagonal_uses_mm():
    'Compute the diagonal in millimeters.'
    model = FakeModel(box_m=[0.0, 0.0, 0.0, 0.003, 0.004, 0.0])

    result = sw_measure.collect_bounding_box(model)

    assert result["diagonal_mm"] == pytest.approx(5.0)


def test_bounding_box_missing_geometry_reports_error():
    'Report missing geometry rather than zero coordinates.'
    result = sw_measure.collect_bounding_box(FakeModel(box_raises=True))

    assert result["size_mm"] is None
    assert result["errors"]


def test_bounding_box_short_array_reports_error():
    'Report fewer than six coordinates.'
    result = sw_measure.collect_bounding_box(FakeModel(box_m=[0.0, 0.0, 0.0]))

    assert result["size_mm"] is None
    assert any('6 koordinat' in item for item in result["errors"])


# Mass properties

def test_mass_properties_converted_to_engineering_units():
    'Convert mass to g, volume to mm3, area to mm2 and centroid to mm.'
    model = FakeModel(mass_property=FakeMassProperty(), material="Alloy Steel")

    result = sw_measure.collect_mass_properties(model)

    assert result["mass_g"] == pytest.approx(36.0)
    assert result["volume_mm3"] == pytest.approx(36000.0)
    assert result["surface_area_mm2"] == pytest.approx(13900.0)
    assert result["center_of_mass_mm"] == pytest.approx([50.0, 30.0, -3.0])
    assert result["material"] == "Alloy Steel"
    assert result["material_assigned"] is True
    assert result["errors"] == []


def test_mass_properties_warns_when_material_missing():
    'Unassigned material produces a warning, not an execution error.'
    model = FakeModel(material=None)

    result = sw_measure.collect_mass_properties(model)

    assert result["material_assigned"] is False
    assert result["errors"] == []
    assert any('malzeme atanmamış' in item for item in result["warnings"])


def test_missing_status_member_is_not_an_error():
    'Missing IMassProperty.Status on SW2024 SP5 is not an error; generic reads previously added a meaningless warning to each measurement.'
    model = FakeModel(mass_property=FakeMassProperty(has_status=False))

    result = sw_measure.collect_mass_properties(model)

    assert not any("Status" in item for item in result["errors"])
    assert result["status"] is None


def test_status_reported_when_present():
    'Read Status normally when available.'
    model = FakeModel(mass_property=FakeMassProperty(has_status=True))

    result = sw_measure.collect_mass_properties(model)

    assert result["status"] == "calculated"


def test_density_derived_from_mass_over_volume():
    'Without requested density, derive mass/volume to check material selection.'
    model = FakeModel(mass_property=FakeMassProperty(mass_kg=7.85, volume_m3=0.001))

    result = sw_measure.collect_mass_properties(model)

    assert result["density_kg_m3"] == pytest.approx(7850.0)
    assert result["implied_density_kg_m3"] == pytest.approx(7850.0)


def test_density_set_through_user_preference():
    'Set density through swMaterialPropertyDensity(7); IMassProperty.Density is read-only and SetOverrideMass does not exist in the tested native environment.'
    model = FakeModel(mass_property=FakeMassProperty(mass_kg=0.2826, volume_m3=3.6e-05))

    result = sw_measure.collect_mass_properties(model, density_kg_m3=7850.0)

    assert result["density_overridden"] is True
    assert model.preference_writes == [(7, 7850.0)]
    assert result["density_kg_m3"] == pytest.approx(7850.0)
    assert result["previous_density_kg_m3"] == pytest.approx(1000.0)
    # Derived density matches the request; no error expected.
    assert result["errors"] == []


def test_density_mismatch_is_flagged():
    'If derived density differs, report that the density setting failed rather than silently returning wrong mass.'
    # Request 7850 but keep the model at 1000.
    model = FakeModel(mass_property=FakeMassProperty(mass_kg=0.036, volume_m3=3.6e-05))

    result = sw_measure.collect_mass_properties(model, density_kg_m3=7850.0)

    assert any('Yoğunluk ayarı uygulanmamış olabilir' in item for item in result["errors"])


def test_mass_property_creation_failure_is_reported():
    'Report CreateMassProperty failure structurally rather than raising a bare exception.'

    class BrokenModel:
        MaterialIdName = None

        class Extension:
            @staticmethod
            def CreateMassProperty():
                raise RuntimeError("no body")

    result = sw_measure.collect_mass_properties(BrokenModel())

    assert result["mass_g"] is None
    assert any('Mass Property nesnesi oluşturulamadı' in item for item in result["errors"])


# Interference checks

class FakeInterference:
    'Interference object stub.'

    def __init__(self, count=0, fail_on=None):
        self.count = count
        self.fail_on = fail_on
        self.TreatSubAssembliesAsComponents = None
        self.TreatCoincidenceAsInterference = None
        self.done_called = False

    def Done(self):
        self.done_called = True
        if self.fail_on == "done":
            raise RuntimeError("assembly busy")

    def GetInterferenceCount(self):
        if self.fail_on == "count":
            raise RuntimeError("count unavailable")
        return self.count

    def GetInterferences(self):
        assert not self.done_called
        if self.fail_on == "calculate":
            raise RuntimeError("calculation failed")
        return [types.SimpleNamespace(Volume=1e-07, Components=[])
                for _ in range(self.count)]


class FakeAssembly:
    'Assembly stub.'

    def __init__(self, count=0, fail_on=None):
        self.InterferenceDetectionManager = FakeInterference(count, fail_on)

    def ClearSelection2(self, all_selections):
        assert all_selections


def test_interference_clean_assembly():
    'Zero interference passes but still requires human review.'
    result = sw_measure.inspect_interference(FakeAssembly(count=0))

    assert result["status"] == "pass"
    assert result["interference_count"] == 0
    assert result["severity"] == "none"
    assert result["manual_review_required"] is True


def test_interference_reports_volumes_in_mm3():
    'Convert interference volume to mm3 and classify by volume.'
    result = sw_measure.inspect_interference(FakeAssembly(count=2))

    assert result["status"] == "warn"
    assert result["interference_count"] == 2
    assert result["items"][0]["volume_mm3"] == pytest.approx(100.0)
    assert result["severity"] == "major"


def test_interference_options_are_forwarded():
    'Options must reach SolidWorks.'
    assembly = FakeAssembly(count=0)

    sw_measure.inspect_interference(
        assembly,
        treat_subassemblies_as_components=True,
        treat_coincidence_as_interference=True,
    )

    assert assembly.InterferenceDetectionManager.TreatSubAssembliesAsComponents is True
    assert assembly.InterferenceDetectionManager.TreatCoincidenceAsInterference is True
    assert assembly.InterferenceDetectionManager.IgnoreHiddenBodies is False
    assert assembly.InterferenceDetectionManager.done_called


@pytest.mark.parametrize("failure", ["count", "calculate", "done"])
def test_interference_api_failures_never_report_zero(failure):
    'Calculation, count or cleanup failure must never fabricate zero interference.'
    assembly = FakeAssembly(count=2, fail_on=failure)
    result = sw_measure.inspect_interference(assembly)
    assert result["status"] == "blocked"
    assert result["interference_count"] is None
    assert assembly.InterferenceDetectionManager.done_called


def test_interference_array_count_mismatch_is_blocked():
    'Reject an empty array inconsistent with a nonzero count.'
    assembly = FakeAssembly(count=2)
    assembly.InterferenceDetectionManager.GetInterferences = lambda: []
    assert sw_measure.inspect_interference(assembly)["status"] == "blocked"


def test_interference_failure_is_structured():
    'Interference-check errors return blocked rather than crash.'
    result = sw_measure.inspect_interference(FakeAssembly(fail_on="done"))

    assert result["status"] == "blocked"
    assert result["manual_review_required"] is True
    assert result["errors"]


# Fit checks

def test_clearance_fit_detected():
    'A larger hole than shaft is a clearance fit.'
    result = sw_measure.check_tolerance_fit(shaft_mm=9.98, hole_mm=10.02, fit="clearance")

    assert result["fit_satisfied"] is True
    assert result["clearance_mm"] == pytest.approx(0.04)


def test_interference_fit_detected():
    'A smaller hole than shaft is an interference fit.'
    result = sw_measure.check_tolerance_fit(shaft_mm=10.05, hole_mm=10.0, fit="interference")

    assert result["fit_satisfied"] is True
    assert result["clearance_mm"] == pytest.approx(-0.05)


def test_fit_check_warns_about_nominal_sizes():
    'Include the limitation that nominal dimensions exclude tolerances.'
    result = sw_measure.check_tolerance_fit(shaft_mm=9.98, hole_mm=10.02)

    assert "GB/T 1800" in result["caveat"] or "ISO 286" in result["caveat"]


def test_fit_requested_but_not_satisfied():
    'Fail explicitly when clearance was requested but interference results.'
    result = sw_measure.check_tolerance_fit(shaft_mm=10.05, hole_mm=10.0, fit="clearance")

    assert result["fit_satisfied"] is False
