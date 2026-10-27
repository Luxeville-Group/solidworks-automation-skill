"""SOLIDWORKS drawing compatibility entry point.

Drawing implementation lives in subskills/solidworks-engineering-drawing. This bridge preserves the historical scripts.sw_drawing import path for existing skills, tests, and third-party callers.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


_IMPLEMENTATION = (
    Path(__file__).resolve().parents[1]
    / "subskills"
    / "solidworks-engineering-drawing"
    / "scripts"
    / "drawing_workflow.py"
)
_SPEC = importlib.util.spec_from_file_location("solidworks_drawing_workflow", _IMPLEMENTATION)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Teknik çizim subskill uygulaması yüklenemedi: {_IMPLEMENTATION}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

__all__ = list(getattr(_MODULE, "__all__", ()))
if not __all__:
    __all__ = [name for name in vars(_MODULE) if not name.startswith("_")]
for _name in __all__:
    globals()[_name] = getattr(_MODULE, _name)
