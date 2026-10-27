# -*- coding: utf-8 -*-
"""@file acad_preflight.py
@brief AutoCAD automation entry-point preflight.

This script checks only Python COM dependencies and AutoCAD COM availability; it does not modify drawings.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from cad_installation import discover_installation  # noqa: E402


def _result(status: str, **kwargs: Any) -> Dict[str, Any]:
    """@brief Construct a consistent JSON result."""
    data: Dict[str, Any] = {"status": status}
    data.update(kwargs)
    return data


def check_pywin32() -> Dict[str, Any]:
    """@brief Check whether pywin32 can be imported."""
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment-dependent
        return _result(
            "missing",
            package="pywin32",
            error=repr(exc),
            install="python -m pip install pywin32",
        )
    return _result("ok", package="pywin32")


def check_autocad(launch: bool) -> Dict[str, Any]:
    """@brief Check whether AutoCAD COM can be connected or started.

    @param launch Allow starting AutoCAD when True.
    @return AutoCAD connection status.
    """
    installation = discover_installation("autocad")
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:  # pragma: no cover
        return _result("missing_pywin32", error=repr(exc))

    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
        mode = "active"
    except Exception as active_exc:
        if not launch:
            return _result(
                "not_running",
                prog_id="AutoCAD.Application",
                installed=installation["installed"],
                executable=installation["executable"],
                installation_source=installation["source"],
                error=repr(active_exc),
                hint="AutoCAD is installed but not running; add --launch to start it automatically." if installation["installed"] else "AutoCAD installation not found; check shortcuts or the installation directory.",
            )
        try:
            app = win32com.client.Dispatch("AutoCAD.Application")
            mode = "launched"
        except Exception as launch_exc:
            return _result(
                "unavailable",
                prog_id="AutoCAD.Application",
                installed=installation["installed"],
                executable=installation["executable"],
                installation_source=installation["source"],
                error=repr(launch_exc),
                hint="Confirm Windows desktop AutoCAD is installed, and start it manually once to complete COM registration.",
            )

    try:
        app.Visible = True
    except Exception:
        pass

    doc_name = None
    try:
        doc_name = app.ActiveDocument.Name
    except Exception:
        doc_name = None

    return _result(
        "ok",
        prog_id="AutoCAD.Application",
        installed=installation["installed"],
        executable=installation["executable"],
        installation_source=installation["source"],
        mode=mode,
        version=str(getattr(app, "Version", "")),
        caption=str(getattr(app, "Caption", "")),
        active_document=doc_name,
    )


def main() -> int:
    """@brief CLI entry point."""
    parser = argparse.ArgumentParser(description="AutoCAD automation preflight")
    parser.add_argument("--launch", action="store_true", help="Allow the script to start AutoCAD")
    args = parser.parse_args()

    report = {
        "python": sys.executable,
        "platform": platform.platform(),
        "pywin32": check_pywin32(),
    }
    if report["pywin32"]["status"] == "ok":
        report["autocad"] = check_autocad(args.launch)
    else:
        report["autocad"] = _result("skipped", reason="pywin32_missing")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["pywin32"]["status"] != "ok":
        return 2
    if report["autocad"]["status"] != "ok":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
