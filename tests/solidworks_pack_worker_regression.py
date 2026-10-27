"""@brief SW2026 real acceptance: forced comtypes fallback, reference reopening, and user-document protection."""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pythoncom
from scripts import sw_delivery
from scripts.sw_connect import connect_solidworks, get_com_member, new_document, save_document, open_document
from scripts.sw_part import sketch, sketch_rectangle, extrude_boss
from scripts.sw_sketch_quality import fully_define_sketch
from scripts.sw_assembly import add_component, get_components
from scripts.sw_process import solidworks_processes


def close_test_files(sw, root):
    """@brief Refresh inventory each time to avoid reusing part proxies unloaded with the assembly."""
    for _ in range(12):
        candidates = []
        for doc in get_com_member(sw, "GetDocuments") or []:
            path = str(get_com_member(doc, "GetPathName") or "")
            if path and Path(path).resolve().is_relative_to(root):
                candidates.append(doc)
        if not candidates:
            return
        candidates.sort(key=lambda item: int(get_com_member(item, "GetType")) != 2)
        sw.CloseDoc(str(get_com_member(candidates[0], "GetTitle")))
    raise RuntimeError("Test documents were not fully cleaned up")


def main(output, source=None):
    """@brief Verify the real parent/child process chain using a private test instance and new output directory."""
    if solidworks_processes() != {}:
        raise RuntimeError("This real-machine test requires no CAD instance currently in use")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed"}
    sw = None
    user_title = None
    pythoncom.CoInitialize()
    try:
        sw, _, meta = connect_solidworks(version=2026, wait_seconds=60, visible=False, return_metadata=True)
        if not meta["started_by_cad_studio"]:
            raise RuntimeError("Test-instance ownership not confirmed")
        pid = int(get_com_member(sw, "GetProcessID"))
        if source is None:
            paths = []
            for index in range(2):
                part = new_document(sw, "part")
                with sketch(part, "Front Plane") as ref:
                    sketch_rectangle(part, 0, 0, .024 + index * .002, .014)
                    fully_define_sketch(part)
                if extrude_boss(part, ref, .008) is None:
                    raise RuntimeError("Test-part creation failed")
                path = output / f"Part{index}.sldprt"
                if not save_document(part, str(path)):
                    raise RuntimeError("Test-part save failed")
                paths.append(path)
                sw.CloseDoc(str(get_com_member(part, "GetTitle")))
            asm = new_document(sw, "assembly")
            for index, path in enumerate(paths):
                if add_component(asm, str(path), x=index * .04, sw=sw) is None:
                    raise RuntimeError("Test-component insertion failed")
            source = output / "TestAssembly.sldasm"
            if not save_document(asm, str(source)):
                raise RuntimeError("Test-assembly save failed")
        else:
            source = source.resolve()
            asm = open_document(sw, str(source), read_only=True, silent=True, raise_on_error=True)
        user = new_document(sw, "part")
        user_title = str(get_com_member(user, "GetTitle"))
        before = {str(get_com_member(item, "GetTitle")) for item in get_com_member(sw, "GetDocuments") or []}
        with patch.object(sw_delivery, "_pywin32_pack_and_go", side_effect=RuntimeError("Test-forced marshaling fallback")):
            packed = sw_delivery.pack_and_go(asm, output / "package", include_drawings=False,
                include_simulation_results=False, include_toolbox_components=False, flatten=True, fallback_policy="blocked")
        report["pack"] = packed
        if not packed["success"] or packed["backend"] != "comtypes":
            raise RuntimeError(f"Actual fallback did not complete native packaging: {packed['status']}; {packed.get('fallback_errors')}")
        after = {str(get_com_member(item, "GetTitle")) for item in get_com_member(sw, "GetDocuments") or []}
        if before != after or int(get_com_member(sw, "GetProcessID")) != pid or str(get_com_member(user, "GetTitle")) != user_title:
            raise RuntimeError("Fallback changed the parent instance or user-document inventory")
        close_test_files(sw, output)
        if source.parent != output:
            close_test_files(sw, source.parent)
        reopened = open_document(sw, str(output / "package" / source.name), read_only=True, silent=True, raise_on_error=True)
        components = get_components(reopened)
        component_paths = [str(item["path"]) for item in components]
        if len(component_paths) != 2 or not all(Path(path).resolve().is_relative_to(output / "package") for path in component_paths):
            raise RuntimeError(f"Packaged references still point to the source directory: {component_paths}")
        report.update(status="pass", year=meta["actual_version"], revision=meta["actual_revision"],
            parent_proxy_alive=True, user_unsaved_document_preserved=True, document_list_unchanged=True,
            reopened_component_paths=component_paths)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if sw is not None:
            try:
                close_test_files(sw, output)
                if source is not None and source.parent != output:
                    close_test_files(sw, source.parent)
                if user_title:
                    sw.CloseDoc(user_title)
                remaining = list(get_com_member(sw, "GetDocuments") or [])
                report["remaining_documents"] = len(remaining)
                if not remaining:
                    sw.ExitApp()
            except Exception as error:
                report.update(status="failed", cleanup_error=str(error))
        pythoncom.CoUninitialize()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key!='pack'}, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.output.resolve(), args.source))
