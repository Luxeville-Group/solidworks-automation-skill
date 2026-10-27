'sw_part sketch-selection regressions. A localized SW2024 issue showed that with an empty selection and failed SelectByID2(SKETCH), feature creation must use the cached sketch object rather than stale selections.'
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def fake_get_com_member(obj, attr_name, *args):
    'Test COM member reader.'
    member = getattr(obj, attr_name)
    return member(*args) if args or callable(member) else member


class FakeVariant:
    'Test VARIANT placeholder.'

    def __init__(self, *_args):
        pass


sys.modules["sw_connect"] = types.SimpleNamespace(get_com_member=fake_get_com_member)
sys.modules["sw_preflight"] = types.SimpleNamespace(
    import_com_dependencies=lambda: (
        types.SimpleNamespace(VT_DISPATCH=9),
        types.SimpleNamespace(),
        FakeVariant,
    )
)

import sw_part  # noqa: E402


class FakeFeature:
    'Simulate a SolidWorks Feature.'

    def __init__(self, name):
        self.Name = name
        self.selected = False

    def Select2(self, append, mark):
        'Simulate successful object-level selection.'
        self.selected = True
        return True


class FakeSketch:
    'Simulate a SolidWorks Sketch.'

    def __init__(self, name):
        self.Name = name
        self.feature = FakeFeature(name)

    def GetFeature(self):
        "Return the sketch's feature."
        return self.feature


class FakeSketchManager:
    'Simulate SketchManager.'

    def __init__(self, sketch):
        self.ActiveSketch = None
        self.sketch = sketch

    def InsertSketch(self, _update_edit_rebuild):
        'Enter or exit sketch mode.'
        self.ActiveSketch = self.sketch if self.ActiveSketch is None else None


class FakeSelectionManager:
    'Simulate an empty selection set.'

    def GetSelectedObjectCount2(self, _mark):
        'Always return an empty selection set.'
        return 0


class FakeExtension:
    'Simulate SelectByID2 failing for SKETCH but succeeding for PLANE.'

    def __init__(self):
        self.calls = []

    def SelectByID2(self, name, entity_type, *_args):
        'Record selection calls and deliberately fail sketch-name selection.'
        self.calls.append((name, entity_type))
        return entity_type == "PLANE"


class FakeFeatureManager:
    'Simulate the extrusion feature manager.'

    def __init__(self, model):
        self.model = model

    def FeatureExtrusion3(self, *_args):
        'Create a feature only after object-level selection.'
        if self.model.sketch.feature.selected:
            return FakeFeature("Boss-Extrude1")
        return None


class FakeModel:
    'Simulate minimal IModelDoc2.'

    def __init__(self):
        self.sketch = FakeSketch("\u8349\u56fe1")
        self.Extension = FakeExtension()
        self.SketchManager = FakeSketchManager(self.sketch)
        self.SelectionManager = FakeSelectionManager()
        self.FeatureManager = FakeFeatureManager(self)
        self.clear_calls = 0

    def ClearSelection2(self, _clear_all):
        'Record selection clearing.'
        self.clear_calls += 1

    def FeatureByName(self, _name):
        'Simulate localized SolidWorks failing to find a sketch by name.'
        return None


class SketchSelectionTests(unittest.TestCase):
    'Sketch selection must not depend on stale selections or SelectByID2(SKETCH).'

    def test_extrude_uses_cached_sketch_object_when_select_by_id_fails(self):
        'Extrusion succeeds despite empty selection and failed sketch-name selection.'
        model = FakeModel()

        with sw_part.sketch(model, "Front Plane") as sketch_name:
            self.assertEqual(sketch_name, "\u8349\u56fe1")

        feature = sw_part.extrude_boss(model, sketch_name, 0.01)

        self.assertIsNotNone(feature)
        self.assertTrue(model.sketch.feature.selected)
        self.assertNotIn(("\u8349\u56fe1", "SKETCH"), model.Extension.calls)


if __name__ == "__main__":
    unittest.main()
