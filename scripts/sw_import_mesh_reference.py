"""
@file sw_import_mesh_reference.py
@brief Import an OBJ/STL mesh reference into SOLIDWORKS and save review results.

For high-fidelity appearance references such as public car, consumer-electronics, or sculpture meshes. Preserve the visual reference without presenting triangle meshes as parametrically editable Class-A surfaces.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .sw_connect import (
        connect_solidworks,
        create_empty_dispatch_variant,
        get_com_member,
        save_document,
    )
    from .sw_preflight import import_com_dependencies
    from .sw_review import run_review
except ImportError:
    from sw_connect import (
        connect_solidworks,
        create_empty_dispatch_variant,
        get_com_member,
        save_document,
    )
    from sw_preflight import import_com_dependencies
    from sw_review import run_review


pythoncom, _win32com_client, VARIANT = import_com_dependencies()


# Values checked against the local SOLIDWORKS 2024 swconst.dll. Integer constants avoid depending on
# the .NET loading path of SolidWorks.Interop.swconst.dll.
SW_IMPORT_STL_VRML_MODEL_TYPE = 208
SW_IMPORT_STL_VRML_UNITS = 210
SW_IMPORT_UNIT_PREFERENCE = 205
SW_IMPORT_STL_VRML_TEXTURE_INFORMATION = 303
SW_VRML_STL_IMPORT_AS_PS_MESH = 679
SW_VRML_STL_IMPORT_SEGMENTED = 682

SW_IMPORT_GRAPHICS_BODY = 0
SW_IMPORT_SURFACE_BODY = 1
SW_IMPORT_SOLID_BODY = 2

SW_LENGTH_UNITS = {
    "mm": 0,
    "cm": 1,
    "m": 2,
    "meter": 2,
    "meters": 2,
    "inch": 3,
    "in": 3,
    "ft": 4,
}

SW_MESH_MODEL_TYPES = {
    "graphics": SW_IMPORT_GRAPHICS_BODY,
    "surface": SW_IMPORT_SURFACE_BODY,
    "solid": SW_IMPORT_SOLID_BODY,
}


def configure_mesh_import_preferences(
    sw: Any,
    *,
    units: str = "m",
    model_type: str = "graphics",
    import_textures: bool = True,
    as_ps_mesh: bool = True,
    segmented: bool = False,
) -> dict[str, Any]:
    """
    @brief Set SOLIDWORKS OBJ/STL/VRML import preferences.

    @param sw SOLIDWORKS application COM object.
    @param units Mesh units, default m.
    @param model_type graphics/surface/solid; graphics is best for high-face-count visual references.
    @param import_textures Attempt texture import.
    @param as_ps_mesh Use the subdivision/graphics-mesh route.
    @param segmented Import segmented mesh.
    @return Preference audit information.
    """
    unit_key = units.strip().lower()
    type_key = model_type.strip().lower()
    if unit_key not in SW_LENGTH_UNITS:
        raise ValueError(f"Desteklenmeyen birim: {units}")
    if type_key not in SW_MESH_MODEL_TYPES:
        raise ValueError(f"Desteklenmeyen içe aktarma türü: {model_type}")

    report: dict[str, Any] = {
        "units": unit_key,
        "model_type": type_key,
        "operations": [],
    }

    int_preferences = [
        (SW_IMPORT_STL_VRML_MODEL_TYPE, SW_MESH_MODEL_TYPES[type_key]),
        (SW_IMPORT_STL_VRML_UNITS, SW_LENGTH_UNITS[unit_key]),
        (SW_IMPORT_UNIT_PREFERENCE, 0),
    ]
    for preference, value in int_preferences:
        ok = sw.SetUserPreferenceIntegerValue(preference, value)
        report["operations"].append(
            {"kind": "integer", "preference": preference, "value": value, "ok": bool(ok)}
        )

    toggle_preferences = [
        (SW_IMPORT_STL_VRML_TEXTURE_INFORMATION, bool(import_textures)),
        (SW_VRML_STL_IMPORT_AS_PS_MESH, bool(as_ps_mesh)),
        (SW_VRML_STL_IMPORT_SEGMENTED, bool(segmented)),
    ]
    for preference, value in toggle_preferences:
        # SetUserPreferenceToggle returns void in some versions; continue if COM raises no exception and validate import/preview afterward.
        returned = sw.SetUserPreferenceToggle(preference, value)
        report["operations"].append(
            {
                "kind": "toggle",
                "preference": preference,
                "value": value,
                "returned": returned,
            }
        )

    return report


def import_mesh_reference(
    mesh_path: str | os.PathLike[str],
    output_sldprt: str | os.PathLike[str],
    *,
    review_dir: str | os.PathLike[str] | None = None,
    units: str = "m",
    model_type: str = "graphics",
    visible: bool = True,
) -> dict[str, Any]:
    """
    @brief Import an OBJ/STL mesh reference and save SLDPRT.

    @param mesh_path Input OBJ/STL path.
    @param output_sldprt Output SLDPRT path.
    @param review_dir Optional review directory for four-view BMPs and a JSON report.
    @param units Input mesh units.
    @param model_type graphics/surface/solid; high-face-count references default to graphics.
    @param visible Show SOLIDWORKS when True.
    @return Import, save, and review results.
    """
    mesh = Path(mesh_path).expanduser().resolve()
    output = Path(output_sldprt).expanduser().resolve()
    if mesh.suffix.lower() not in {".obj", ".stl"}:
        raise ValueError("Bu script yalnızca OBJ/STL işler. GLB/FBX/BLEND dosyalarını önce Blender/trimesh ile dönüştürün.")
    if not mesh.exists():
        raise FileNotFoundError(str(mesh))

    output.parent.mkdir(parents=True, exist_ok=True)
    sw, _active = connect_solidworks(visible=visible)

    result: dict[str, Any] = {
        "source": str(mesh),
        "source_size_bytes": mesh.stat().st_size,
        "output_sldprt": str(output),
        "solidworks_revision": get_com_member(sw, "RevisionNumber"),
    }
    result["import_preferences"] = configure_mesh_import_preferences(
        sw,
        units=units,
        model_type=model_type,
        import_textures=True,
        as_ps_mesh=True,
        segmented=False,
    )

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

    # OBJ/STL pitfall: do not pass None to LoadFile4 or call GetImportFileData() first.
    # None causes type mismatch; OpenDoc6 may return 2097152 in some SW2024 environments.
    model = sw.LoadFile4(str(mesh), "r", create_empty_dispatch_variant(), errors)
    result["loadfile4_errors"] = int(errors.value)
    result["opened"] = model is not None
    if model is None:
        raise RuntimeError(f"OBJ/STL içe aktarma başarısız; LoadFile4 errors={errors.value}")

    result["title"] = get_com_member(model, "GetTitle")
    result["doc_type"] = get_com_member(model, "GetType")

    model.ClearSelection2(True)
    model.ForceRebuild3(False)
    model.ViewZoomtofit2()
    model.GraphicsRedraw2()

    saved = save_document(model, str(output))
    result["saved"] = bool(saved)
    result["output_size_bytes"] = output.stat().st_size if output.exists() else 0
    if not saved:
        raise RuntimeError(f"Kaydetme başarısız: {output}")

    if review_dir:
        review_base = Path(review_dir).expanduser().resolve()
        review_base.mkdir(parents=True, exist_ok=True)
        report, report_path = run_review(
            model,
            str(review_base),
            basename=output.stem,
            expected_outputs=[str(output), str(mesh)],
        )
        result["review_report"] = report_path
        result["review_evaluation"] = report.get("evaluation")
        result["review_previews"] = report.get("previews")

    return result


def _build_parser() -> argparse.ArgumentParser:
    """@brief Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="OBJ/STL mesh referansını SOLIDWORKS içine aktar ve SLDPRT olarak kaydet."
    )
    parser.add_argument("mesh_path", help="Giriş OBJ/STL yolu")
    parser.add_argument("output_sldprt", help="Çıktı SLDPRT yolu")
    parser.add_argument("--review-dir", help="İnceleme çıktı dizini")
    parser.add_argument("--units", default="m", choices=sorted(SW_LENGTH_UNITS.keys()))
    parser.add_argument(
        "--model-type",
        default="graphics",
        choices=sorted(SW_MESH_MODEL_TYPES.keys()),
        help="graphics/surface/solid olarak içe aktar. Yüksek yüz sayılı görünüş referansları için graphics önerilir.",
    )
    parser.add_argument("--hidden", action="store_true", help="SOLIDWORKS penceresini gizle")
    return parser


def main(argv: list[str] | None = None) -> int:
    """@brief Command-line entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = import_mesh_reference(
        args.mesh_path,
        args.output_sldprt,
        review_dir=args.review_dir,
        units=args.units,
        model_type=args.model_type,
        visible=not args.hidden,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
