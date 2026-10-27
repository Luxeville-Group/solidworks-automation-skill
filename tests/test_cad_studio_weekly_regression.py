import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "tests" / "cad_studio_weekly_regression.py"
_SPEC = importlib.util.spec_from_file_location("cad_studio_weekly_regression", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MODULE)


def test_weekly_regression_decodes_python_and_autocad_output():
    assert _MODULE._decode_output("Test passed".encode("utf-8")) == "Test passed"
    assert _MODULE._decode_output("Türkçe çıktı".encode("gb18030")) == "Türkçe çıktı"
    assert _MODULE._decode_output("Unknown command".encode("utf-16")) == "Unknown command"
