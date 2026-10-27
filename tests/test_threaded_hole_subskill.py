'Offline engineering-logic regressions for solidworks-threaded-holes.'

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "subskills"
    / "solidworks-threaded-holes"
    / "scripts"
    / "create_threaded_hole_template.py"
)
# Some older tests leave simplified objects in sys.modules during collection;
# remove that pollution before loading the subskill to avoid suite-order dependence.
for module_name in ("sw_connect", "sw_preflight"):
    if module_name in sys.modules and not getattr(sys.modules[module_name], "__file__", None):
        del sys.modules[module_name]
SPEC = importlib.util.spec_from_file_location("solidworks_threaded_hole_template", SCRIPT_PATH)
threaded = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = threaded
SPEC.loader.exec_module(threaded)


def make_args(**overrides) -> argparse.Namespace:
    'Generate overridable default CLI arguments.'
    values = {
        "thread": "M6",
        "block_length": 40.0,
        "block_width": 30.0,
        "block_thickness": 16.0,
        "hole_x": 0.0,
        "hole_y": 0.0,
        "tap_drill": None,
        "pilot_depth": None,
        "thread_depth": None,
        "mouth_chamfer": 0.6,
        "through": False,
        "hole_face": "top",
        "thread_class": "6H",
        "handedness": "right",
        "visible_thread": "fallback",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class FakeFeature:
    'Simulate a renameable SolidWorks feature.'

    Name = ""


class FakeFeatureManager:
    'Record FeatureCut4 end conditions.'

    def __init__(self):
        self.cut_calls = []

    def FeatureCut4(self, *args):
        self.cut_calls.append(args)
        return FakeFeature()


class FakeCutModel:
    'Minimal model API for the cut function.'

    def __init__(self):
        self.FeatureManager = FakeFeatureManager()


class FakeThreadEdge:
    'Record the circular-edge selection mark used by ThreadFeatureData.'

    def __init__(self):
        self.select_calls = []

    def Select2(self, append, mark):
        self.select_calls.append((append, mark))
        return True


class FakeThreadData:
    'Simulate assignable IThreadFeatureData.'

    def InitializeThreadData(self):
        return None


class FakeThreadFeatureManager:
    'Simulate the ThreadFeatureData creation chain.'

    def __init__(self):
        self.data = FakeThreadData()

    def CreateDefinition(self, feature_id):
        assert feature_id == threaded.SW_FM_SWEEP_THREAD
        return self.data

    def CreateFeature(self, data):
        assert data is self.data
        return FakeFeature()


class FakeThreadModel:
    'Minimal model API for real Thread creation.'

    def __init__(self):
        self.FeatureManager = FakeThreadFeatureManager()

    def ClearSelection2(self, _clear_all):
        return True


class FakeTreeFeature:
    'Simulate top-level and child feature chains.'

    def __init__(self, name, feature_type, next_feature=None, next_subfeature=None, first_subfeature=None):
        self.Name = name
        self._feature_type = feature_type
        self._next_feature = next_feature
        self._next_subfeature = next_subfeature
        self._first_subfeature = first_subfeature

    def GetTypeName2(self):
        return self._feature_type

    def GetNextFeature(self):
        return self._next_feature

    def GetNextSubFeature(self):
        return self._next_subfeature

    def GetFirstSubFeature(self):
        return self._first_subfeature


class FakeTreeModel:
    'Feature-tree model exposing FirstFeature.'

    def __init__(self, first_feature):
        self._first_feature = first_feature

    def FirstFeature(self):
        return self._first_feature


def test_through_hole_uses_through_all_end_condition(monkeypatch) -> None:
    '--through must create true Through All, not an excessively deep blind cut.'
    model = FakeCutModel()
    monkeypatch.setattr(threaded, "select_sketch", lambda *_args: None)

    threaded.cut_hole_from_sketch(model, "Sketch1", 16.0, 'Tam geçişli kılavuz ön deliği', through=True)

    assert model.FeatureManager.cut_calls[0][3] == threaded.SW_END_COND_THROUGH_ALL


def test_real_thread_uses_official_edge_mark_without_start_entity(monkeypatch) -> None:
    'Planar circular edges require mark 1 without fabricated StartEntity.'
    model = FakeThreadModel()
    edge = FakeThreadEdge()
    params = threaded.build_params(make_args())
    monkeypatch.setattr(threaded, "locate_hole_mouth_edge", lambda *_args, **_kwargs: (edge, (0.0, 0.0, 0.0)))

    threaded.add_real_thread_feature(model, params)

    assert edge.select_calls == [(False, 1)]
    assert model.FeatureManager.data.Edge is edge
    assert model.FeatureManager.data.Type == "Metric Tap"
    assert not hasattr(model.FeatureManager.data, "StartEntity")
    assert model.FeatureManager.data.DiameterOverride is False


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"thread_depth": 12.0, "pilot_depth": 5.0}, 'Thread depth'),
        ({"hole_x": 100.0}, 'Hole X'),
        ({"tap_drill": 8.0}, 'Tap-drill diameter'),
        ({"mouth_chamfer": -1.0}, "mouth_chamfer"),
        ({"block_length": -40.0}, "block_length"),
        ({"hole_x": float("nan")}, "hole_x"),
    ],
)
def test_invalid_engineering_parameters_fail_before_com(overrides, message) -> None:
    'Invalid geometry/process parameters fail before COM.'
    with pytest.raises(ValueError, match=message):
        threaded.build_params(make_args(**overrides))


def test_through_hole_keeps_physical_depth_and_allows_partial_thread() -> None:
    'Through tap-drill evidence equals plate thickness while partial thread depth is allowed.'
    params = threaded.build_params(make_args(through=True, thread_depth=10.0))

    assert params.pilot_depth_mm == 16.0
    assert params.thread_depth_mm == 10.0
    assert params.through_hole is True


def test_custom_metric_pitch_requires_explicit_tap_drill() -> None:
    'Out-of-table pitches require explicit user tap-drill diameters.'
    with pytest.raises(ValueError):
        threaded.build_params(make_args(thread="M8x1.0"))

    params = threaded.build_params(make_args(thread="M8x1.0", tap_drill=7.0))
    assert params.thread_label == "M8x1"
    assert params.pitch_mm == 1.0
    assert params.tap_drill_diameter_mm == 7.0


def test_visible_helix_preserves_pitch_and_stays_inside_hole() -> None:
    'Helix turn counts may be fractional; axial depth divided by turns equals the requested pitch.'
    params = threaded.build_params(
        make_args(thread="M8", block_thickness=20.0, thread_depth=16.0, pilot_depth=18.0)
    )
    plan = threaded.visible_helix_plan(params)

    assert plan["axial_depth_mm"] / plan["turns"] == pytest.approx(params.pitch_mm)
    assert plan["start_offset_mm"] + plan["axial_depth_mm"] <= params.pilot_depth_mm
    assert plan["segment_count"] == math.ceil(plan["turns"] * 32.0)


def test_metadata_only_representation_is_not_verified() -> None:
    'Properties alone cannot establish verified thread representation.'
    with pytest.raises(RuntimeError, match='custom properties alone'):
        threaded.require_thread_representation({"representation": "metadata-only"})

    assert threaded.require_thread_representation({"representation": "real-thread"}) == "real-thread-verified"


def test_cosmetic_thread_is_detected_as_cut_subfeature() -> None:
    'CosmeticThread belongs under the hole/cut; top-level traversal is insufficient.'
    params = threaded.build_params(make_args())
    cosmetic = FakeTreeFeature("CosmeticThread_M6x1.0_Internal_Blind_RH", "CosmeticThread")
    chamfer = FakeTreeFeature("Chamfer_Thread_Mouth", "Chamfer")
    cut = FakeTreeFeature(
        "Cut_M6x1.0_Tap_Drill",
        "ICE",
        next_feature=chamfer,
        first_subfeature=cosmetic,
    )

    evidence = threaded.collect_thread_feature_evidence(FakeTreeModel(cut), params, visible_segments=0)

    assert evidence["representation"] == "cosmetic-thread"
    assert evidence["has_cosmetic_thread"] is True
    cosmetic_item = next(item for item in evidence["features"] if item["type"] == "CosmeticThread")
    assert cosmetic_item["parent"] == "Cut_M6x1.0_Tap_Drill"


@pytest.mark.parametrize("basename", ["../escape", "folder/name", "bad:name", ".."])
def test_basename_cannot_escape_output_directory(basename) -> None:
    'Output basenames cannot contain paths or invalid Windows characters.'
    with pytest.raises(ValueError):
        threaded.validate_basename(basename)
