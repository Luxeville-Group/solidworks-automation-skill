'Semantic edge-selection regressions. Native testing found edge.Select4(True, None, False) raises type mismatch (0x80020005): the second argument requires a Dispatch VARIANT. Import the real scripts.sw_edge_select rather than polluting sys.modules with stubs that affect later collection.'
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.sw_edge_select as sw_edge_select  # noqa: E402


class FakeCurve:
    'Curve stub.'

    def __init__(self, is_circle=False):
        self._circle = is_circle

    def IsLine(self):
        return not self._circle

    def IsCircle(self):
        return self._circle


class FakeVertex:
    'Vertex stub.'

    def __init__(self, point_m):
        self._point = point_m

    def GetPoint(self):
        return list(self._point)


class FakeEdge:
    'Edge stub recording every selection call.'

    def __init__(self, start_m, end_m, length_m=None, is_circle=False,
                 diameter_m=None, selectable=True, select4_raises=None):
        self._start = start_m
        self._end = end_m
        self._length = length_m
        self._is_circle = is_circle
        self._diameter = diameter_m
        self._selectable = selectable
        self._select4_raises = select4_raises
        self.select_calls = []
        self.selected = False

    def GetLength(self):
        if self._length is None:
            span = [self._end[axis] - self._start[axis] for axis in range(3)]
            return sum(value * value for value in span) ** 0.5
        return self._length

    def GetCurve(self):
        return FakeCurve(self._is_circle)

    def GetStartVertex(self):
        return FakeVertex(self._start)

    def GetEndVertex(self):
        return FakeVertex(self._end)

    def GetCurveParams2(self):
        if self._is_circle:
            # Circle: [center(3), axis(3), radius]; radius, not diameter.
            return [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, (self._diameter or 0.01) / 2.0]
        span = [self._end[axis] - self._start[axis] for axis in range(3)]
        return [*self._start, *self._end, *span]

    def Select2(self, append, mark):
        self.select_calls.append(("Select2", append, mark))
        self.selected = self._selectable
        return self._selectable

    def Select4(self, append, callout):
        self.select_calls.append(("Select4", append, callout))
        if self._select4_raises is not None:
            raise self._select4_raises
        self.selected = self._selectable
        return self._selectable


class FakeBody:
    'Body stub.'

    def __init__(self, edges):
        self._edges = edges

    def GetEdges(self):
        return list(self._edges)


class FakeModel:
    'Document stub.'

    def __init__(self, edges):
        self._bodies = [FakeBody(edges)] if edges else []
        self.cleared = 0

    def GetBodies2(self, _type, _visible_only):
        return list(self._bodies)

    def ClearSelection2(self, _all):
        self.cleared += 1
        return True


# Twelve edges of a 100x60x6 plate, in meters.
def plate_edges():
    'Construct the edge set of a rectangular plate.'
    x, y, z = 0.1, 0.06, 0.006
    edges = []
    # Four vertical edges along Z.
    for corner in [(0, 0), (x, 0), (x, y), (0, y)]:
        edges.append(FakeEdge((corner[0], corner[1], 0.0), (corner[0], corner[1], z)))
    # Four edges along X.
    for base_z in (0.0, z):
        for y_pos in (0.0, y):
            edges.append(FakeEdge((0.0, y_pos, base_z), (x, y_pos, base_z)))
    # Four edges along Y.
    for base_z in (0.0, z):
        for x_pos in (0.0, x):
            edges.append(FakeEdge((x_pos, 0.0, base_z), (x_pos, y, base_z)))
    return edges


# Description

def test_edge_length_and_midpoint_in_mm():
    'Convert edge length and midpoint to millimeters.'
    edge = FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.01))

    descriptor = sw_edge_select.describe_edge(edge)

    assert descriptor["length_mm"] == pytest.approx(10.0)
    assert descriptor["mid_point_mm"] == pytest.approx([0.0, 0.0, 5.0])
    assert descriptor["is_circle"] is False


def test_edge_direction_is_normalised():
    'Normalize straight-edge direction for axis filtering.'
    edge = FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.02))

    descriptor = sw_edge_select.describe_edge(edge)

    assert descriptor["direction"] == pytest.approx((0.0, 0.0, 1.0))


def test_circular_edge_diameter_in_mm():
    'Convert circular-edge diameter to millimeters.'
    edge = FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), length_m=0.0207, is_circle=True, diameter_m=0.0066)

    descriptor = sw_edge_select.describe_edge(edge)

    assert descriptor["is_circle"] is True
    assert descriptor["diameter_mm"] == pytest.approx(6.6)


def test_absurd_diameter_is_rejected():
    'Reject inconsistent diameter/length magnitudes to avoid corrupt measurements.'
    edge = FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), length_m=0.001, is_circle=True, diameter_m=0.5)

    descriptor = sw_edge_select.describe_edge(edge)

    assert descriptor["diameter_mm"] is None


def test_edge_descriptor_reports_errors_without_raising():
    'Record member-read errors rather than raising exceptions.'

    class BrokenEdge:
        def GetCurve(self):
            raise RuntimeError("boom")

    descriptor = sw_edge_select.describe_edge(BrokenEdge())

    assert descriptor["errors"]


# Filtering

def test_filter_by_z_axis_finds_vertical_edges():
    'Z-axis filtering must select exactly four vertical edges.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))

    selected, rejected = sw_edge_select.filter_edges(descriptors, axis="z")

    assert len(selected) == 4
    assert all(item["direction"][2] == pytest.approx(1.0) for item in selected)


def test_filter_axis_all_keeps_everything():
    'axis=all applies no direction filter.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))

    selected, _ = sw_edge_select.filter_edges(descriptors, axis="all")

    assert len(selected) == len(descriptors) == 12


def test_filter_vertical_alias_matches_z():
    'vertical is equivalent to the Z axis.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))

    by_z, _ = sw_edge_select.filter_edges(descriptors, axis="z")
    by_vertical, _ = sw_edge_select.filter_edges(descriptors, axis="vertical")

    assert len(by_z) == len(by_vertical)


def test_filter_by_length_range():
    'Filter by length range.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))

    long_edges, _ = sw_edge_select.filter_edges(descriptors, axis="all", min_length_mm=50.0)

    assert all(item["length_mm"] >= 50.0 for item in long_edges)
    assert len(long_edges) == 8  # Four X edges (100 mm) plus four Y edges (60 mm).


def test_filter_circular_only():
    'Keep circular edges only.'
    edges = plate_edges() + [
        FakeEdge((0.01, 0.01, 0.0), (0.01, 0.01, 0.0), length_m=0.0207, is_circle=True, diameter_m=0.0066)
    ]
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(edges))

    selected, _ = sw_edge_select.filter_edges(descriptors, circular=True)

    assert len(selected) == 1
    assert selected[0]["diameter_mm"] == pytest.approx(6.6)


def test_filter_by_diameter_tolerance():
    'Filter by diameter with tolerance.'
    edges = [
        FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), length_m=0.02, is_circle=True, diameter_m=0.0066),
        FakeEdge((0.05, 0.0, 0.0), (0.05, 0.0, 0.0), length_m=0.03, is_circle=True, diameter_m=0.008),
    ]
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(edges))

    selected, _ = sw_edge_select.filter_edges(
        descriptors, circular=True, diameter_mm=6.6, diameter_tolerance_mm=0.05
    )

    assert len(selected) == 1


def test_filter_by_position():
    'Filter by midpoint coordinates in millimeters.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))
    # The fixture considers vertical edges from z=0 to z=6;
    # check midpoint coordinates against the actual plate corners.
    selected, _ = sw_edge_select.filter_edges(
        descriptors, axis="z", position_mm=[0.0, 0.0, 3.0], position_tolerance_mm=0.5
    )

    assert len(selected) == 1
    assert selected[0]["mid_point_mm"] == pytest.approx([0.0, 0.0, 3.0])


def test_rejected_entries_carry_reasons():
    'Explain exclusions so users can adjust filters.'
    descriptors, _ = sw_edge_select.iter_model_edges(FakeModel(plate_edges()))

    _, rejected = sw_edge_select.filter_edges(descriptors, axis="z")

    assert len(rejected) == 8
    assert all(item["reasons"] for item in rejected)


# Selection

def test_select_edges_uses_select2():
    'Prefer Select2 to avoid Callout argument issues.'
    model = FakeModel(plate_edges())

    result = sw_edge_select.select_edges(model, {"axis": "z"})

    assert result["status"] == "ok"
    assert result["selected_count"] == 4


def test_select_edge_passes_dispatch_variant_not_none(monkeypatch):
    'Select4 Callout must be a Dispatch VARIANT, not None. Native type mismatch (0x80020005) motivates this test: disable Select2 and verify create_empty_dispatch_variant() is passed to Select4.'
    sentinel = object()
    monkeypatch.setattr(sw_edge_select, "create_empty_dispatch_variant", lambda: sentinel)

    edge = FakeEdge((0.0, 0.0, 0.0), (0.0, 0.0, 0.01))
    edge.Select2 = None  # Simulate an environment with Select4 only.
    model = FakeModel([edge])

    sw_edge_select.select_edges(model, {"axis": "z"})

    assert edge.select_calls == [("Select4", True, sentinel)]
    assert edge.select_calls[0][2] is not None


def test_select_falls_back_to_select4_when_select2_fails(monkeypatch):
    'Fall back to Select4 on Select2 errors, with a non-None Callout.'
    sentinel = object()
    monkeypatch.setattr(sw_edge_select, "create_empty_dispatch_variant", lambda: sentinel)

    class Select2Broken(FakeEdge):
        def Select2(self, append, mark):
            self.select_calls.append(("Select2", append, mark))
            raise RuntimeError("\u7c7b\u578b\u4e0d\u5339\u914d")

    edge = Select2Broken((0.0, 0.0, 0.0), (0.0, 0.0, 0.01))
    model = FakeModel([edge])

    sw_edge_select.select_edges(model, {"axis": "z"})

    assert edge.select_calls[0][0] == "Select2"
    assert edge.select_calls[1][0] == "Select4"
    assert edge.select_calls[1][2] is sentinel


def test_select_edges_clears_selection_first():
    'Clear selection before choosing edges to avoid stale state.'
    model = FakeModel(plate_edges())

    sw_edge_select.select_edges(model, {"axis": "z"})

    assert model.cleared >= 1


def test_select_edges_errors_when_nothing_matches():
    'No matching edges must return error; silently continuing could fillet the current contour and create the wrong feature.'
    model = FakeModel(plate_edges())

    result = sw_edge_select.select_edges(model, {"axis": "z", "min_length_mm": 1000.0})

    assert result["status"] == "error"
    assert result["selected_count"] == 0
    assert result["errors"]
    assert result["rejected_sample"]


def test_select_edges_errors_on_empty_model():
    'Report an explicit error when the model has no edges.'
    result = sw_edge_select.select_edges(FakeModel([]), {"axis": "z"})

    assert result["status"] == "error"
    assert any('Modelde kenar bulunamadı' in item for item in result["errors"])


def test_select_edges_reports_partial_failures():
    'Report partial selection failures while returning successful selections.'
    edges = plate_edges()
    edges[0]._selectable = False
    model = FakeModel(edges)

    result = sw_edge_select.select_edges(model, {"axis": "z"})

    assert result["status"] == "ok"
    assert result["selected_count"] == 3
    assert result["errors"]


def test_describe_convexity_tolerates_missing_faces():
    'Return None on failed convexity classification so callers do not incorrectly exclude edges.'

    class NoFaces(FakeEdge):
        def GetTwoAdjacentFaces2(self):
            return []

    assert sw_edge_select.describe_convexity(NoFaces((0, 0, 0), (0, 0, 1))) is None
