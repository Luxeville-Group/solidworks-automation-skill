'Native advanced fillet/chamfer regression on an open-source gusset bracket. Import MIT-licensed CadQuery l_gusset STEP, create a four-point variable-radius fillet and distance-distance chamfer on one complex body, then save, export STEP, reopen, read FeatureData and review four views.'

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from sw_appearance import set_document_appearance  # noqa: E402
from sw_connect import create_empty_dispatch_variant, get_com_member, mm  # noqa: E402
from sw_export import export_to_step  # noqa: E402
from sw_review import run_review  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402
from verify_advanced_fillets import (  # noqa: E402
    SW_CHAMFER_DISTANCE_DISTANCE,
    SW_FEATURE_VARIABLE,
    SW_FILLET_PROPAGATE,
    SW_FILLET_UNIFORM_RADIUS,
    SW_FILLET_VARIABLE_TYPE,
    SW_OVERFLOW_DEFAULT,
    SW_PROFILE_CIRCULAR,
    _assert_feature,
    _double_array,
    _edge_points,
    _feature_data_evidence,
    _find_edge,
    _hide_review_helpers,
    _near,
)


SOURCE_REPOSITORY = "https://github.com/archimedes-market/parametric-bracket-library"
SOURCE_LICENSE = "MIT"
SOURCE_COMMIT = "5b285130bff480cda282499e83604b295dd0aa4d"
SOURCE_CADQUERY_VERSION = "2.8.0"
SOURCE_SHA256 = "cc2d38a467f8a78ab80d939b655930e3f1d3bda204fbfc42cd3722e56328c1f9"
VARIABLE_FEATURE = "OSS_Gusset_Variable_4Point"
CHAMFER_FEATURE = "OSS_Gusset_Width_Width_C0p8_C1p4"


def _advanced_evidence_passes(evidence: dict[str, Any]) -> bool:
    'Strictly validate four control-point readbacks and unequal chamfer distances.'
    variable = evidence["variable"]
    chamfer = evidence["width_width_chamfer"]
    controls = variable.get("control_points") or []
    return (
        str(variable.get("type_name")) == "VarFillet"
        and int(variable.get("GetControlPointsCount") or 0) == 4
        and [item.get("location_percent") for item in controls]
        == [20.0, 40.0, 60.0, 80.0]
        and [item.get("radius_mm") for item in controls]
        == [1.2, 1.8, 0.9, 1.5]
        and int(chamfer.get("Type") or -1) == SW_CHAMFER_DISTANCE_DISTANCE
        and sorted(float(value) for value in chamfer.get("edge_distances_mm") or [])
        == [0.8, 1.4]
    )


def _sha256(path: Path) -> str:
    'Compute the input STEP SHA-256 for traceable test provenance.'
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _body_stats(model: Any) -> dict[str, Any]:
    'Read single-body complexity; reject empty imports or ambiguous multiple bodies.'
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"Açık kaynak braket tek katı olmalı; gerçek / Open-source bracket must be one body; actual: {len(bodies)}")
    faces = tuple(get_com_member(bodies[0], "GetFaces") or ())
    edges = tuple(get_com_member(bodies[0], "GetEdges") or ())
    analytic_faces = {"plane": 0, "cylinder": 0, "other": 0}
    for face in faces:
        surface = get_com_member(face, "GetSurface")
        if bool(get_com_member(surface, "IsPlane")):
            analytic_faces["plane"] += 1
        elif bool(get_com_member(surface, "IsCylinder")):
            analytic_faces["cylinder"] += 1
        else:
            analytic_faces["other"] += 1
    return {
        "body_count": len(bodies),
        "face_count": len(faces),
        "edge_count": len(edges),
        "analytic_faces": analytic_faces,
    }


def _add_variable_fillet(model: Any):
    "Create a four-point variable-radius fillet on the upright plate's 80 mm outer edge."
    edge = _find_edge(
        model,
        lambda a, b: _near(a[0], 0.0) and _near(b[0], 0.0)
        and _near(a[1], mm(20.0)) and _near(b[1], mm(20.0))
        and _near(abs(a[2] - b[2]), mm(80.0)),
    )
    controls = ((0.20, 1.2), (0.40, 1.8), (0.60, 0.9), (0.80, 1.5))
    model.ClearSelection2(True)
    if not edge.Select2(False, 1):
        raise RuntimeError('Açık kaynak braketin değişken radyüs kenarı seçilemedi / Open-source bracket variable-radius edge selection failed')
    start, end = _edge_points(edge)
    for location, _radius in controls:
        xyz = tuple(
            start[index] + location * (end[index] - start[index])
            for index in range(3)
        )
        if not model.Extension.SelectByID2(
            "", "POINTREF", *xyz, True, 256, create_empty_dispatch_variant(), 0
        ):
            raise RuntimeError(f"Açık kaynak braket kontrol noktası seçilemedi / Open-source bracket control-point selection failed: {location:.2f}")
    feature = model.FeatureManager.FeatureFillet3(
        SW_FILLET_PROPAGATE + SW_FILLET_UNIFORM_RADIUS + SW_FILLET_VARIABLE_TYPE,
        0.0, 0.0, 0.0, SW_FEATURE_VARIABLE,
        SW_OVERFLOW_DEFAULT, SW_PROFILE_CIRCULAR,
        _double_array((mm(1.0), mm(1.6))),
        0, 0, 0,
        _double_array([mm(radius) for _location, radius in controls]),
        0, 0,
    )
    return _assert_feature(model, feature, VARIABLE_FEATURE)


def _add_width_width_chamfer(model: Any):
    "Create a 0.8/1.4 mm distance-distance chamfer on the horizontal plate's 40 mm outer edge."
    edge = _find_edge(
        model,
        lambda a, b: _near(a[0], mm(80.0)) and _near(b[0], mm(80.0))
        and _near(a[2], 0.0) and _near(b[2], 0.0)
        and _near(abs(a[1] - b[1]), mm(40.0)),
    )
    model.ClearSelection2(True)
    if not edge.Select2(False, 0):
        raise RuntimeError('Açık kaynak braketin mesafe-mesafe pah kenarı seçilemedi / Open-source bracket distance-distance chamfer edge selection failed')
    feature = model.FeatureManager.InsertFeatureChamfer(
        0,
        SW_CHAMFER_DISTANCE_DISTANCE,
        mm(0.8),
        0.0,
        mm(1.4),
        0.0,
        0.0,
        0.0,
    )
    return _assert_feature(model, feature, CHAMFER_FEATURE)


def run_regression(args: argparse.Namespace) -> dict[str, Any]:
    'Run the complete native workflow and return machine-readable evidence.'
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Açık kaynak braket STEP bulunamadı / Open-source bracket STEP missing: {source}")
    source_sha256 = _sha256(source)
    if args.source_commit != SOURCE_COMMIT:
        raise RuntimeError(
            f"Kaynak commit uyuşmuyor / Source commit mismatch: expected={SOURCE_COMMIT}, actual={args.source_commit}"
        )
    if source_sha256 != SOURCE_SHA256:
        raise RuntimeError(
            f"Girdi STEP özeti uyuşmuyor / Input STEP hash mismatch: expected={SOURCE_SHA256}, actual={source_sha256}"
        )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    part_path = output_dir / "l_gusset_advanced.SLDPRT"
    step_path = output_dir / "l_gusset_advanced.step"
    session = SolidWorksSession(version=args.version, visible=True)
    model = None
    reopened = None
    try:
        model = session.open(str(source), read_only=False, silent=True)
        baseline = _body_stats(model)
        if baseline["face_count"] < 12 or baseline["edge_count"] < 30:
            raise RuntimeError(f"Braket topoloji karmaşıklığı yetersiz / Bracket topology complexity insufficient: {baseline}")
        if not session.save(model, str(part_path)):
            raise RuntimeError('Açık kaynak braket SLDPRT olarak kaydedilemedi / Could not save open-source bracket as SLDPRT')
        variable = _add_variable_fillet(model)
        chamfer = _add_width_width_chamfer(model)
        set_document_appearance(model, "silver")
        _hide_review_helpers(model)
        model.ViewZoomtofit2()
        if not session.save(model):
            raise RuntimeError('İşlenen braket kaydedilemedi / Enhanced bracket save failed')
        if not export_to_step(model, str(step_path)):
            raise RuntimeError('İşlenen braket STEP olarak aktarılamadı / Enhanced bracket STEP export failed')
        review, review_path = run_review(
            model,
            output_dir,
            basename="l_gusset_advanced",
            expected_outputs=[str(part_path), str(step_path)],
        )
        before = {
            "variable": _feature_data_evidence(variable, "variable", model),
            "width_width_chamfer": _feature_data_evidence(
                chamfer, "width_width_chamfer", model
            ),
            "topology": _body_stats(model),
        }
        session.close(model=model)
        model = None
        reopened = session.open(str(part_path), read_only=True, silent=True)
        reopened_ok = bool(reopened.ForceRebuild3(False))
        reopened_variable = reopened.FeatureByName(VARIABLE_FEATURE)
        reopened_chamfer = reopened.FeatureByName(CHAMFER_FEATURE)
        after = {
            "variable": _feature_data_evidence(
                reopened_variable, "variable", reopened
            ) if reopened_variable else {"definition_available": False},
            "width_width_chamfer": _feature_data_evidence(
                reopened_chamfer, "width_width_chamfer", reopened
            ) if reopened_chamfer else {"definition_available": False},
            "topology": _body_stats(reopened),
        }
        passed = (
            reopened_ok
            and _advanced_evidence_passes(before)
            and _advanced_evidence_passes(after)
            and part_path.is_file()
            and step_path.is_file()
            and review["evaluation"]["status"] in {"pass", "warn"}
        )
        return {
            "status": "verified" if passed else "failed",
            "source": {
                "repository": SOURCE_REPOSITORY,
                "commit": args.source_commit,
                "license": SOURCE_LICENSE,
                "cadquery_version": SOURCE_CADQUERY_VERSION,
                "path": str(source),
                "sha256": source_sha256,
            },
            "solidworks_revision": str(get_com_member(session.sw, "RevisionNumber")),
            "baseline": baseline,
            "before_close": before,
            "after_reopen": after,
            "rebuild_after_reopen": reopened_ok,
            "review": review["evaluation"],
            "review_path": str(review_path),
            "outputs": {"part": str(part_path), "step": str(step_path)},
        }
    finally:
        for document in (reopened, model):
            if document is not None:
                try:
                    session.close(model=document)
                except Exception:
                    pass
        session.quit_owned_instance()


def parse_args() -> argparse.Namespace:
    'Parse CLI arguments.'
    parser = argparse.ArgumentParser(description='Açık kaynak karmaşık güçlendirme braketinde gelişmiş radyüs/pah doğrulaması / Verify advanced fillets/chamfers on a complex open-source gusset bracket.')
    parser.add_argument("--source", type=Path, required=True, help='CadQuery ile oluşturulan l_gusset STEP / CadQuery-generated l_gusset STEP.')
    parser.add_argument("--source-commit", default=SOURCE_COMMIT, help='Kaynak depo commit özeti / Source repository commit hash.')
    parser.add_argument("--version", type=int, default=2026, help='SolidWorks yılı / SolidWorks year.')
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "open_source_bracket_regression",
        help='Regresyon çıktılarının dizini / Regression artifact directory.',
    )
    return parser.parse_args()


def main() -> int:
    'Command-line entry point.'
    args = parse_args()
    report = run_regression(args)
    report_path = args.output_dir.resolve() / "open_source_bracket_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), **report}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
