"""@brief Load and verify the C# Add-in host in a real SolidWorks session."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import win32com.client


ADDIN_GUID = "8EE76E8D-9B47-4DE0-AFA2-B2E36621A134"


def _com_value(owner, name: str, *args):
    """@brief Handle pywin32 exposing no-argument COM methods as properties or callable objects."""
    member = getattr(owner, name)
    # CDispatch means pywin32 already performed the no-argument COM call during property access;
    # although it implements __call__, calling again attempts to access a nonexistent default member.
    if not args and hasattr(member, "_oleobj_"):
        return member
    return member(*args) if callable(member) else member


def _diagnostic_path() -> Path:
    """@brief Return the current-user diagnostic path shared by the Add-in and tests."""
    return Path(os.environ["LOCALAPPDATA"]) / "CAD Studio" / "SolidWorksAddin" / "host-status.json"


def _wait_for_connected(path: Path, timeout_seconds: float = 20.0, *, require_property_page: bool = True) -> dict:
    """@brief Wait for Add-in evidence of connection and UI subsystem readiness."""
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict = {}
    while time.monotonic() < deadline:
        if path.exists():
            try:
                last_payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                time.sleep(0.2)
                continue
            if (
                last_payload.get("status") == "connected"
                and str(last_payload.get("hostProcessName", "")).casefold() == "sldworks"
                and last_payload.get("callbackRegistered") is True
                and last_payload.get("commandGroupReady") is True
                and last_payload.get("taskPaneReady") is True
                and (last_payload.get("propertyManagerPageReady") is True or not require_property_page)
            ):
                return last_payload
        time.sleep(0.2)
    raise RuntimeError(f"Add-in was not ready within {timeout_seconds:.0f}s: {last_payload}")


def run_regression(assembly: Path, *, keep_loaded: bool = True, start_solidworks: bool = False) -> dict:
    """@brief Load the host, trigger application events, and verify machine-readable diagnostics."""
    assembly = assembly.expanduser().resolve()
    if not assembly.is_file():
        raise FileNotFoundError(assembly)
    diagnostics = _diagnostic_path()
    if diagnostics.exists():
        diagnostics.unlink()

    started_solidworks = False
    try:
        sw_app = win32com.client.GetActiveObject("SldWorks.Application")
    except Exception:
        if not start_solidworks:
            raise RuntimeError("SolidWorks is not running; pass --start to launch the local default version.")
        sw_app = win32com.client.Dispatch("SldWorks.Application")
        sw_app.Visible = True
        started_solidworks = True
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                _com_value(sw_app, "RevisionNumber")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("SolidWorks was not ready within 45s of startup.")
    load_status = int(sw_app.LoadAddIn(str(assembly)))
    if load_status not in {0, 2}:
        raise RuntimeError(f"LoadAddIn failed, swLoadAddinError_e={load_status}")
    initial = _wait_for_connected(diagnostics, require_property_page=False)
    revision = str(_com_value(sw_app, "RevisionNumber"))
    if initial.get("solidWorksRevision") != revision:
        raise AssertionError((initial.get("solidWorksRevision"), revision))

    created = _com_value(sw_app, "NewPart")
    if created is None:
        raise RuntimeError("NewPart returned no document; cannot verify FileNewNotify2.")
    title = str(_com_value(created, "GetTitle"))
    sw_app.CloseDoc(title)
    event_payload = _wait_for_event(diagnostics, "file_new")
    event_payload = _wait_for_event(diagnostics, "active_model_doc_change")
    documents_after_close = int(_com_value(sw_app, "GetDocumentCount"))
    if documents_after_close != 0:
        raise RuntimeError(f"{documents_after_close} documents remain open after CloseDoc.")

    unload_status = None
    if not keep_loaded:
        unload_status = int(sw_app.UnloadAddIn(str(assembly)))
        if unload_status != 0:
            raise RuntimeError(f"UnloadAddIn failed, status={unload_status}")

    return {
        "status": "pass",
        "addin_guid": ADDIN_GUID,
        "assembly": str(assembly),
        "assembly_bytes": assembly.stat().st_size,
        "load_status": load_status,
        "unload_status": unload_status,
        "solidworks_revision": revision,
        "solidworks_started_by_probe": started_solidworks,
        "diagnostics": str(diagnostics),
        "command_group_ready": event_payload["commandGroupReady"],
        "task_pane_ready": event_payload["taskPaneReady"],
        "property_manager_page_ready": event_payload["propertyManagerPageReady"],
        "event_counts": event_payload["eventCounts"],
        "documents_after_close": documents_after_close,
        "errors": event_payload["errors"],
    }


def _wait_for_event(path: Path, name: str, timeout_seconds: float = 10.0) -> dict:
    """@brief Wait for the specified event to occur at least once."""
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict = {}
    while time.monotonic() < deadline:
        try:
            last_payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            time.sleep(0.2)
            continue
        if int(last_payload.get("eventCounts", {}).get(name, 0)) >= 1:
            return last_payload
        time.sleep(0.2)
    raise RuntimeError(f"Event {name} was not observed: {last_payload}")


def main() -> int:
    '@brief Command-line entry point.'
    parser = argparse.ArgumentParser()
    parser.add_argument("--assembly", required=True, type=Path)
    parser.add_argument("--unload", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_regression(
        args.assembly,
        keep_loaded=not args.unload,
        start_solidworks=args.start,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
