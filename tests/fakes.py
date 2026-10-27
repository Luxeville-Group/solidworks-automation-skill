"""
SolidWorks COM test-double factories.

Previously, each test file defined its own Fake classes, such as ``sys.modules["sw_connect"] = SimpleNamespace(...)``,
creating seven or eight incompatible implementations of the same object. This module supplies shared doubles;
new tests should reuse these classes instead of creating another set.

Design principles:
- Doubles implement only members **actually called** by the tested code and fail explicitly otherwise, preventing
  silently returned None values from making tests pass incorrectly.
- Record call sequences (``calls``) for regression assertions such as ensuring SelectByID2 was not called.
- Preserve units supplied by callers without conversion: unit conversion is itself under test.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


class FakeVariant:
    """VARIANT placeholder that records constructor arguments only."""

    def __init__(self, *args):
        self.args = args


class FakeEdge:
    """Edge double recording selection state and supporting Select2/Select4."""

    def __init__(self, index=0, length_m=0.01, start_m=(0.0, 0.0, 0.0), end_m=(0.0, 0.0, 0.01),
                 is_circle=False, diameter_m=None, selectable=True):
        self.index = index
        self.length_m = length_m
        self.start_m = start_m
        self.end_m = end_m
        self.is_circle = is_circle
        self.diameter_m = diameter_m
        self.selectable = selectable
        self.selected = False
        self.select_calls: List[Tuple[Any, ...]] = []

    def GetLength(self):
        return self.length_m

    def GetCurve(self):
        return FakeCurve(is_circle=self.is_circle, diameter_m=self.diameter_m)

    def GetStartVertex(self):
        return FakeVertex(self.start_m)

    def GetEndVertex(self):
        return FakeVertex(self.end_m)

    def GetCurveParams2(self):
        # Circle: [center(3), axis(3), radius]
        if self.is_circle:
            return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, self.diameter_m / 2.0 if self.diameter_m else 0.005]
        # Line: [start(3), end(3), direction(3)]
        direction = [self.end_m[axis] - self.start_m[axis] for axis in range(3)]
        return [*self.start_m, *self.end_m, *direction]

    def Select2(self, append, mark):
        self.select_calls.append(("Select2", append, mark))
        self.selected = self.selectable
        return self.selectable

    def Select4(self, append, callout):
        self.select_calls.append(("Select4", append, callout))
        self.selected = self.selectable
        return self.selectable


class FakeVertex:
    """Vertex double."""

    def __init__(self, point_m):
        self.point_m = point_m

    def GetPoint(self):
        return list(self.point_m)


class FakeCurve:
    """Curve double."""

    def __init__(self, is_circle=False, diameter_m=None):
        self.is_circle = is_circle
        self.diameter_m = diameter_m

    def IsLine(self):
        return not self.is_circle

    def IsCircle(self):
        return self.is_circle

    def CircleParams(self):
        return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, self.diameter_m / 2.0 if self.diameter_m else 0.005]


class FakeFace:
    """Face double."""

    def __init__(self, edges=(), is_cylinder=False, cylinder_radius_m=None):
        self.edges = list(edges)
        self.is_cylinder = is_cylinder
        self.cylinder_radius_m = cylinder_radius_m

    def GetEdges(self):
        return list(self.edges)

    def GetSurface(self):
        return FakeSurface(is_cylinder=self.is_cylinder, radius_m=self.cylinder_radius_m)


class FakeSurface:
    """Surface double."""

    def __init__(self, is_cylinder=False, radius_m=None):
        self.is_cylinder = is_cylinder
        self.radius_m = radius_m

    def IsCylinder(self):
        return self.is_cylinder

    def CylinderParams(self):
        return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, self.radius_m or 0.005]


class FakeBody:
    """Body double."""

    def __init__(self, edges=(), faces=()):
        self.edges = list(edges)
        self.faces = list(faces)

    def GetEdges(self):
        return list(self.edges)

    def GetFaces(self):
        return list(self.faces)


class FakeFeature:
    """Feature double."""

    def __init__(self, name="Feature1"):
        self.Name = name


class FakeMassProperty:
    """Mass-properties double.

    Space-style members such as Status simulate unavailable versions through ``has_status=False``.
    """

    def __init__(self, mass_kg=0.0, volume_m3=0.0, area_m2=0.0, center_m=(0.0, 0.0, 0.0),
                 inertia=None, has_status=False):
        self._mass = mass_kg
        self._volume = volume_m3
        self._area = area_m2
        self._center = list(center_m)
        self._inertia = inertia or [0.0] * 9
        if has_status:
            self.Status = 1
        self.override_calls: List[Any] = []

    def Mass(self):
        return self._mass

    def Volume(self):
        return self._volume

    def SurfaceArea(self):
        return self._area

    def CenterOfMass(self):
        return list(self._center)

    def GetMomentOfInertia(self, _frame):
        return list(self._inertia)

    def SetOverrideMass(self, enabled):
        self.override_calls.append(("SetOverrideMass", enabled))


class FakeModel:
    """
    Document double.

    Parameters:
        title / path: document identity.
        box_m: six GetPartBox(True) coordinates in meters; None means no geometry.
        material: assigned material name; None means unassigned.
    """

    def __init__(self, title="Part1", path="", box_m=None, material=None,
                 edges=(), expectation=None, mass_kg=0.0, volume_m3=0.0):
        self._title = title
        self._path = path
        self._oleobj_ = object()
        self._box_m = box_m
        self.MaterialIdName = material
        self._bodies = [FakeBody(edges=edges)] if edges else []
        self._mass = FakeMassProperty(mass_kg=mass_kg, volume_m3=volume_m3)
        self.calls: List[str] = []
        self.expectation = expectation
        self.selection_count = 0
        self.Extension = FakeExtension(self)
        self.SketchManager = FakeSketchManager()
        self.FeatureManager = FakeFeatureManager(self)

    # ---- Basic identity ----
    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path

    def GetType(self):
        return 1  # swDocPART

    # ---- Geometry ----
    def GetPartBox(self, use_system_units=True):
        self.calls.append(f"GetPartBox({use_system_units})")
        if self._box_m is None:
            raise RuntimeError("no geometry")
        # Critical: GetPartBox(True) returns meters; GetPartBox(False) returns millimeters.
        if use_system_units:
            return list(self._box_m)
        return [value * 1000.0 for value in self._box_m]

    def GetBodies2(self, _type, _visible_only):
        return list(self._bodies)

    def ForceRebuild3(self, _silent):
        self.calls.append("ForceRebuild3")
        return True

    def ClearSelection2(self, _all):
        self.selection_count = 0
        self.calls.append("ClearSelection2")
        return True

    def GetSelectionCount(self):
        return self.selection_count


class FakeExtension:
    """ModelDocExtension double."""

    def __init__(self, model: FakeModel):
        self._model = model
        self.select_by_id_calls: List[Tuple[Any, ...]] = []

    def SelectByID2(self, *args):
        self.select_by_id_calls.append(args)
        return False

    def CreateMassProperty(self):
        return self._model._mass

    def SaveAs(self, *args):
        self._model.calls.append("SaveAs")
        return True


class FakeSketchManager:
    """SketchManager double."""

    def __init__(self):
        self.ActiveSketch = None

    def InsertSketch(self, _update):
        return None


class FakeFeatureManager:
    """FeatureManager double recording each feature-creation argument list."""

    def __init__(self, model: FakeModel):
        self._model = model
        self.fillet_calls: List[Tuple[Any, ...]] = []
        self.chamfer_calls: List[Tuple[Any, ...]] = []
        self.extrude_calls: List[Tuple[Any, ...]] = []
        self.fillet_result = FakeFeature("Fillet1")
        self.chamfer_result = FakeFeature("Chamfer1")
        self.extrude_result = FakeFeature("Boss-Extrude1")

    def FeatureFillet(self, *args):
        self.fillet_calls.append(args)
        if self._model.selection_count <= 0:
            raise RuntimeError("Parameter not optional")
        return self.fillet_result

    def InsertFeatureChamfer(self, *args):
        self.chamfer_calls.append(args)
        if self._model.selection_count <= 0:
            raise RuntimeError("Parameter not optional")
        return self.chamfer_result

    def FeatureExtrusion3(self, *args):
        self.extrude_calls.append(args)
        return self.extrude_result

    def FeatureCut4(self, *args):
        self.extrude_calls.append(("cut", *args))
        return self.extrude_result


class FakeSolidWorks:
    """ISldWorks double managing document lists, creation, and closing."""

    def __init__(self, documents=(), template_ok=True):
        self.documents = list(documents)
        self.template_ok = template_ok
        self.new_document_return = None
        self.new_document_factory = None
        self.closed: List[str] = []
        self.preferences: Dict[int, Any] = {}

    def GetDocuments(self):
        return list(self.documents)

    def NewDocument(self, _template, *_args):
        if not self.template_ok:
            return None
        if self.new_document_factory is not None:
            document = self.new_document_factory()
            self.documents.append(document)
            return document
        return self.new_document_return

    def CloseDoc(self, title):
        self.closed.append(title)
        self.documents = [doc for doc in self.documents if doc.GetTitle() != title]
        return True

    def CloseAllDocuments(self, _save):
        self.closed.extend(doc.GetTitle() for doc in self.documents)
        self.documents = []
        return True

    def GetUserPreferenceIntegerValue(self, preference):
        return self.preferences.get(preference, 0)

    def SetUserPreferenceIntegerValue(self, preference, value):
        self.preferences[preference] = value
        return True

    def RevisionNumber(self):
        return "32.5.0"


def install_com_stubs(monkeypatch=None):
    """
    Inject COM doubles for the ``scripts`` package so tested modules can import offline.

    Return a namespace for test assertions.

    Usage::

        stubs = install_com_stubs()
        from scripts import sw_measure
    """
    import sys
    import types

    stub_modules = {
        "sw_preflight": types.SimpleNamespace(
            import_com_dependencies=lambda: (
                types.SimpleNamespace(VT_DISPATCH=9, VT_BYREF=16384, VT_I4=3),
                types.SimpleNamespace(),
                FakeVariant,
            ),
            missing_com_dependencies=lambda: [],
            solidworks_installed=lambda: True,
        ),
    }

    def fake_get_com_member(obj, attr_name, *args):
        member = getattr(obj, attr_name)
        if args:
            return member(*args)
        if callable(member):
            try:
                return member()
            except TypeError:
                return member
        return member

    stub_modules["sw_connect"] = types.SimpleNamespace(
        get_com_member=fake_get_com_member,
        create_empty_dispatch_variant=lambda: FakeVariant(),
        mm=lambda value: value / 1000.0,
        deg=lambda value: math.radians(value),
    )

    for name, module in stub_modules.items():
        sys.modules.setdefault(name, module)
    return stub_modules
