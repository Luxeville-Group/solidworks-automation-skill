# -*- coding: utf-8 -*-
"""@file acad_preview.py
@brief Export the active AutoCAD drawing as a visual preview for screenshot-based review.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from acad_session import AutoCADSession


def convert_bmp_to_png(bmp_path: Path, png_path: Path) -> Dict[str, Any]:
    """@brief Attempt to convert an AutoCAD BMP preview to PNG.

    @param bmp_path Input BMP.
    @param png_path Output PNG.
    @return Conversion result.
    """
    try:
        from PIL import Image
    except Exception as exc:
        ps_script = f"""
Add-Type -AssemblyName System.Drawing
$src = [System.IO.Path]::GetFullPath('{str(bmp_path).replace("'", "''")}')
$dst = [System.IO.Path]::GetFullPath('{str(png_path).replace("'", "''")}')
$img = [System.Drawing.Image]::FromFile($src)
try {{
  $img.Save($dst, [System.Drawing.Imaging.ImageFormat]::Png)
}} finally {{
  $img.Dispose()
}}
"""
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as ps_exc:
            return {
                "status": "skipped",
                "reason": "Pillow and PowerShell System.Drawing conversion failed",
                "pillow_error": repr(exc),
                "powershell_error": repr(ps_exc),
            }
        if not png_path.exists():
            return {
                "status": "skipped",
                "reason": "PowerShell conversion completed but PNG was not created",
                "pillow_error": repr(exc),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        return {
            "status": "ok",
            "path": str(png_path),
            "size": png_path.stat().st_size,
            "converter": "powershell-system-drawing",
        }

    with Image.open(bmp_path) as image:
        image.save(png_path)
        size = list(image.size)
    return {
        "status": "ok",
        "path": str(png_path),
        "size": png_path.stat().st_size,
        "image_size": size,
    }


def main() -> int:
    """@brief CLI entry point."""
    parser = argparse.ArgumentParser(description="Export a preview of the active AutoCAD drawing")
    parser.add_argument("--output", required=True, help="Output PNG or BMP path")
    parser.add_argument("--source", help="Optionally open this DWG/DXF first")
    parser.add_argument("--launch", action="store_true", help="Allow starting AutoCAD")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    bmp_path = output if output.suffix.lower() == ".bmp" else output.with_suffix(".bmp")

    session = AutoCADSession(create_if_missing=args.launch, visible=True).connect()
    if args.source:
        session.open_document(args.source, read_only=True)

    bmp_path = session.export_bmp_preview(bmp_path)
    report: Dict[str, Any] = {
        "status": "ok",
        "bmp": {
            "path": str(bmp_path),
            "exists": bmp_path.exists(),
            "size": bmp_path.stat().st_size if bmp_path.exists() else None,
        },
    }

    if output.suffix.lower() == ".png":
        png_result = convert_bmp_to_png(bmp_path, output)
        report["png"] = png_result
        if png_result["status"] != "ok":
            report["status"] = "partial"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
