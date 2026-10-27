"""@brief Scheme B real regression: patterns, editable sketches, reopen/edit parameters; owned instances only."""
import argparse
import json
import math
from pathlib import Path
import sys

import pythoncom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.sw_connect import connect_solidworks, get_com_member, get_sw_version, new_document, save_document, open_document
from scripts.sw_part import sketch, sketch_circle, sketch_rectangle, extrude_boss, extrude_cut, linear_pattern, circular_pattern
from scripts.sw_assembly import iter_feature_tree
from scripts.sw_sketch_quality import fully_define_sketch, inspect_model_sketches
from scripts.sw_measure import collect_mass_properties
from scripts.sw_review import collect_geometry_measurements
from scripts.sw_session import SolidWorksSession
from scripts.sw_process import solidworks_processes


def hole_layout(model):
    """@brief Read hole-axis positions in the perpendicular plane, excluding depth-induced axial origin changes."""
    result = []
    for hole in collect_geometry_measurements(model)["holes"]:
        axis = hole["axis"]
        origin = hole["position_mm"]
        dot = sum(a * b for a, b in zip(axis, origin))
        perpendicular = tuple(round(origin[i] - dot * axis[i], 5) for i in range(3))
        result.append((hole["diameter_mm"], perpendicular))
    return sorted(result)


def main(output):
    """@brief Compare analytical volume and verify editable real dimensions without bulk Fix constraints."""
    prior = solidworks_processes()
    if prior is None or prior:
        raise RuntimeError("Real-machine regression requires an idle, separate SolidWorks instance")
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "cases": [], "cleanup": {}}
    sw = None
    owned_titles = set()
    pythoncom.CoInitialize()
    try:
        sw, _, meta = connect_solidworks(version=2026, wait_seconds=60, visible=True, return_metadata=True)
        report["version"] = get_sw_version(sw)
        pid = int(get_com_member(sw, "GetProcessID"))
        if pid in prior or not meta["started_by_cad_studio"]:
            raise RuntimeError("CAD-instance ownership cannot be confirmed")
        for circular in (False, True):
            label = "circular" if circular else "linear"
            model = new_document(sw, "part")
            owned_titles.add(str(get_com_member(model, "GetTitle")))
            with sketch(model, "Front Plane") as ref:
                if circular:
                    sketch_circle(model, 0, 0, .030)
                else:
                    sketch_rectangle(model, 0, 0, .080, .040)
                base_quality = fully_define_sketch(model)
            boss = extrude_boss(model, ref, .008, direction=False)
            if boss is None:
                raise RuntimeError("Base extrusion failed")
            boss_name = str(get_com_member(boss, "Name"))
            with sketch(model, "Front Plane") as ref:
                sketch_circle(model, .015 if circular else -.020, 0, .003)
                hole_quality = fully_define_sketch(model)
            cut = extrude_cut(model, ref, 0, direction=True)
            if cut is None:
                raise RuntimeError("Seed-hole creation failed")
            cut_name = str(get_com_member(cut, "Name"))
            if circular:
                bodies = get_com_member(model, "GetBodies2", 0, False)
                cylinder = None
                for face in get_com_member(bodies[0], "GetFaces"):
                    surface = get_com_member(face, "GetSurface")
                    if get_com_member(surface, "IsCylinder") and abs(get_com_member(surface, "CylinderParams")[6] - .030) < 1e-6:
                        cylinder = face
                        break
                data = get_com_member(model.SelectionManager, "CreateSelectData")
                data.Mark = 0
                model.ClearSelection2(True)
                if cylinder is None or not get_com_member(cylinder, "Select4", False, data) or not model.InsertAxis2(True):
                    raise RuntimeError("Reference-axis creation failed")
                axes = [feature for feature, _ in iter_feature_tree(model) if get_com_member(feature, "GetTypeName2") == "RefAxis"]
                if len(axes) != 1:
                    raise RuntimeError("Reference axis is not unique")
                axis_name = str(get_com_member(axes[0], "Name"))
                created = circular_pattern(model, cut_name, axis_name, 2 * math.pi, 4)
                section = math.pi * 30**2 - 4 * math.pi * 3**2
            else:
                created = linear_pattern(model, cut_name, 1, 0, 0, .020, 3)
                section = 80 * 40 - 3 * math.pi * 3**2
            if created is None or not model.ForceRebuild3(False):
                raise RuntimeError("Pattern creation or rebuild failed")
            actual = collect_mass_properties(model)["volume_mm3"]
            original_holes = hole_layout(model)
            if len(original_holes) != (4 if circular else 3):
                raise RuntimeError(f"Pattern hole count mismatch: {original_holes}")
            if actual is None or abs(actual - section * 8) > .1:
                raise RuntimeError(f"{label} pattern volume mismatch: {actual}, expected={section * 8}")
            path = output / (label + ".sldprt")
            if not save_document(model, str(path)):
                raise RuntimeError('Kaydetme başarısız')
            sw.CloseDoc(str(get_com_member(model, "GetTitle")))
            reopened = open_document(sw, str(path), silent=True)
            quality = inspect_model_sketches(reopened)
            if quality["status"] != "pass":
                raise RuntimeError(f"Saved sketch quality mismatch: {quality}")
            dimension = get_com_member(reopened, "Parameter", "D1@" + boss_name)
            dimension.SystemValue = .010
            if not reopened.ForceRebuild3(False):
                raise RuntimeError("Rebuild failed after thickness change")
            changed = collect_mass_properties(reopened)["volume_mm3"]
            changed_holes = hole_layout(reopened)
            if original_holes != changed_holes:
                raise RuntimeError("Hole diameter or centers changed after parameter update")
            if changed is None or abs(changed - section * 10) > .1:
                raise RuntimeError(f"Geometry mismatch after parameter update: {changed}, expected={section * 10}")
            if not save_document(reopened, str(output / (label + "_thickness10.sldprt"))):
                raise RuntimeError("Updated model save failed")
            report["cases"].append({"name": label, "status": "pass", "volume8": actual, "volume10": changed,
                "base_quality": base_quality, "hole_quality": hole_quality, "reopened_quality": quality})
            report["cases"][-1].update(holes_before=original_holes, holes_after=changed_holes)
            print(f"PASS {label}: volume8={actual}, volume10={changed}", flush=True)
            sw.CloseDoc(str(get_com_member(reopened, "GetTitle")))
        user_document = new_document(sw, "part")
        user_title = str(get_com_member(user_document, "GetTitle"))
        owned_titles.add(user_title)
        with SolidWorksSession(max_documents=2) as session:
            if int(get_com_member(session.sw, "GetProcessID")) != pid:
                raise RuntimeError("Session incorrectly connected to another CAD process")
            session.new_part()
            try:
                session.new_part()
            except Exception as error:
                if getattr(error, "code", None) != "SW_DOCUMENT_BUDGET":
                    raise
            else:
                raise RuntimeError("Document budget failed to prevent creation")
        if str(get_com_member(user_document, "GetTitle")) != user_title or len(get_com_member(sw, "GetDocuments") or []) != 1:
            raise RuntimeError("Cleanup touched the simulated user document or left current-run documents")
        report["cases"].append({"name": "session_ownership_budget", "status": "pass", "protected_user_document": True})
        print("PASS session_ownership_budget", flush=True)
        sw.CloseDoc(user_title)
        report["status"] = "pass"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], flush=True)
    finally:
        if sw is not None:
            remaining = list(get_com_member(sw, "GetDocuments") or [])
            # This run owns the isolated test instance's documents; exit only when no other documents remain.
            for doc in remaining:
                path = str(get_com_member(doc, "GetPathName") or "")
                title = str(get_com_member(doc, "GetTitle"))
                if (not path and title in owned_titles) or (path and Path(path).resolve().is_relative_to(output)):
                    sw.CloseDoc(str(get_com_member(doc, "GetTitle")))
            report["cleanup"]["remaining_documents"] = len(get_com_member(sw, "GetDocuments") or [])
            if report["cleanup"]["remaining_documents"] == 0:
                sw.ExitApp()
        pythoncom.CoUninitialize()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(main(parser.parse_args().output.resolve()))
