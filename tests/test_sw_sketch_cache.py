"Sketch-selection cache lifecycle regressions. Global dictionaries can retain COM references across documents, and id(model)/id(_oleobj_) keys can be reused after GC, incorrectly selecting an old document's sketch. Tests cover both retention and identity reuse."
import gc
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Inject COM stubs before importing sw_part to avoid native dependencies.
sys.modules.setdefault(
    "sw_preflight",
    types.SimpleNamespace(
        import_com_dependencies=lambda: (
            types.SimpleNamespace(VT_DISPATCH=9),
            types.SimpleNamespace(),
            lambda *args: None,
        )
    ),
)
sys.modules.setdefault(
    "sw_connect",
    types.SimpleNamespace(
        get_com_member=lambda obj, attr, *args: getattr(obj, attr)(*args)
        if args or callable(getattr(obj, attr))
        else getattr(obj, attr),
        # sw_part imports this factory for Select4 Callout arguments.
        create_empty_dispatch_variant=lambda: None,
        mm=lambda value: value / 1000.0,
        deg=lambda value: value * 3.141592653589793 / 180.0,
    ),
)

import sw_part  # noqa: E402


class FakeModel:
    'Minimal document with title/path fingerprints.'

    def __init__(self, title, path=""):
        self._title = title
        self._path = path
        self._oleobj_ = object()

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path


@pytest.fixture(autouse=True)
def _clean_cache():
    'Clear caches before and after each case to prevent cross-test interference.'
    sw_part.clear_sketch_selection_cache()
    yield
    sw_part.clear_sketch_selection_cache()


def _ref(name="Sketch1", source="test"):
    return sw_part.SketchSelectionRef(name=name, source=source)


def test_cache_hit_within_same_document():
    'Hit the cache within one document rather than falling back to SelectByID2(SKETCH).'
    model = FakeModel("Part1")
    ref = _ref()

    sw_part._cache_sketch_ref(model, ref)

    assert sw_part._find_cached_sketch_ref(model, "Sketch1") is ref


def test_cache_does_not_leak_across_documents():
    'Do not share cache hits between documents.'
    first = FakeModel("Part1")
    second = FakeModel("Assembly1")

    sw_part._cache_sketch_ref(first, _ref())

    assert sw_part._find_cached_sketch_ref(second, "Sketch1") is None


def test_cache_rejects_reused_ole_object_id():
    "Reused COM addresses must not hit an old document's sketch."
    original = FakeModel("Part1")
    sw_part._cache_sketch_ref(original, _ref())

    # Simulate CPython address reuse by sharing an underlying OLE-object identity.
    reused = FakeModel("DifferentPart")
    reused._oleobj_ = original._oleobj_

    assert sw_part._find_cached_sketch_ref(reused, "Sketch1") is None


def test_cache_rejects_reused_id_after_gc():
    'Invalidate cache entries after their source document is collected.'
    model = FakeModel("Part1")
    sw_part._cache_sketch_ref(model, _ref())

    del model
    gc.collect()
    sw_part._prune_sketch_cache()

    assert len(sw_part._SKETCH_SELECTION_CACHE) == 0


def test_cache_invalidated_when_active_document_switches():
    'Invalidate when a title changes at the same COM address.'
    model = FakeModel("Part1")
    sw_part._cache_sketch_ref(model, _ref())

    model._title = "Part2"  # Same address, different document.

    assert sw_part._find_cached_sketch_ref(model, "Sketch1") is None


def test_cache_entries_are_bounded():
    'Bound cache size for long-running processes.'
    for index in range(sw_part._SKETCH_CACHE_LIMIT + 10):
        model = FakeModel(f"Part{index}")
        sw_part._cache_sketch_ref(model, _ref(f"Sketch{index}"))

    assert len(sw_part._SKETCH_SELECTION_CACHE) <= sw_part._SKETCH_CACHE_LIMIT


def test_clear_cache_for_single_document():
    'Targeted document cleanup leaves other documents intact.'
    first = FakeModel("Part1")
    second = FakeModel("Part2")
    first_ref = _ref()
    second_ref = _ref()

    sw_part._cache_sketch_ref(first, first_ref)
    sw_part._cache_sketch_ref(second, second_ref)

    sw_part.clear_sketch_selection_cache(first)

    assert sw_part._find_cached_sketch_ref(first, "Sketch1") is None
    assert sw_part._find_cached_sketch_ref(second, "Sketch1") is second_ref


def test_clear_cache_all():
    'Full cleanup empties the cache.'
    sw_part._cache_sketch_ref(FakeModel("Part1"), _ref())
    sw_part._cache_sketch_ref(FakeModel("Part2"), _ref())

    sw_part.clear_sketch_selection_cache()

    assert len(sw_part._SKETCH_SELECTION_CACHE) == 0


def test_explicit_sketch_ref_bypasses_cache():
    'Direct SketchSelectionRef inputs bypass cache lookup.'
    ref = _ref()
    assert sw_part._find_cached_sketch_ref(FakeModel("Part1"), ref) is ref
