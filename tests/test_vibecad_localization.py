"""Verify Turkish/English planning with explicit non-default dimensions."""

import importlib.util
from pathlib import Path

import pytest


def _planner():
    path = Path(__file__).resolve().parents[1] / "subskills/solidworks-vibecad/scripts/plan_from_brief.py"
    spec = importlib.util.spec_from_file_location("localized_vibecad_planner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("brief", [
    "100x70x9mm taban, M6 montaj, 27mm merkez deliği, R4, C2",
    "100x70x9mm base, M6 mounting, center hole: 27mm, R4, C2",
    "100x70x9mm TABAN, M6 MONTAJ, MERKEZ DELİĞİ: 27mm, R4, C2",
])
def test_bilingual_plan_preserves_explicit_dimensions(brief):
    plan = _planner().build_plan(brief)
    parameters = plan["parameters"]
    assert parameters["center_hole_diameter"] == 27
    features = {feature["name"]: feature for feature in plan["features"]}
    assert features["BasePlate"]["params"] == {"length": 100, "width": 70, "thickness": 9}
    assert features["OuterCornerFillet"]["params"]["radius"] == 4
    assert features["TopEdgeChamfer"]["params"]["distance"] == 2
    assert features["CornerMountingHoles"]["params"]["fastener"] == "M6"
    assert plan["review_plan"]
