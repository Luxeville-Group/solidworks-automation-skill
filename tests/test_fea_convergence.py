"""CalculiX multi-mesh convergence sequence regressions."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.fea_convergence import run_convergence_study, validate_convergence_request


def _analysis(case_index: int) -> dict:
    """@brief Return controlled meshes with increasing topology counts and identical physics."""
    nodes = [
        {"id": 1, "x": 0, "y": 0, "z": 0},
        {"id": 2, "x": 10, "y": 0, "z": 0},
        {"id": 3, "x": 0, "y": 10, "z": 0},
        {"id": 4, "x": 0, "y": 0, "z": 10},
    ]
    for offset in range(case_index):
        nodes.append({"id": 5 + offset, "x": 20 + offset, "y": 0, "z": 0})
    elements = [
        {"id": element_id, "type": "C3D4", "nodeIds": [1, 2, 3, 4]}
        for element_id in range(1, case_index + 2)
    ]
    return {
        "schemaVersion": "1.0",
        "analysisId": f"mesh_{case_index}",
        "analysisType": "static_linear",
        "solver": "calculix",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "temperature": "C"},
        "material": {"name": "Steel", "elasticModulusMPa": 210000, "poissonRatio": 0.3, "densityKgM3": 7850},
        "mesh": {
            "nodes": nodes,
            "elements": elements,
            "nodeSets": {"FixedNodes": [1, 2, 3]},
            "elementSets": {"AllElements": [item["id"] for item in elements]},
        },
        "constraints": [{"id": "fixed", "type": "fixed", "nodeSet": "FixedNodes"}],
        "loads": [{"id": "gravity", "type": "gravity", "magnitude": 9810, "direction": [0, 0, -1]}],
    }


def _study() -> dict:
    """@brief Return a three-level convergence protocol fixture."""
    return {
        "schemaVersion": "1.0",
        "studyId": "cantilever_convergence",
        "tolerancePercent": 5.0,
        "cases": [
            {"id": "coarse", "characteristicSizeMm": 10, "analysis": _analysis(0)},
            {"id": "medium", "characteristicSizeMm": 5, "analysis": _analysis(1)},
            {"id": "fine", "characteristicSizeMm": 2.5, "analysis": _analysis(2)},
        ],
    }


def test_validate_convergence_requires_strict_mesh_refinement() -> None:
    """@brief Mesh sizes, node counts, and element counts must change strictly from coarse to fine."""
    request = _study()
    assert validate_convergence_request(request)["studyId"] == "cantilever_convergence"
    request["cases"][2]["characteristicSizeMm"] = 5
    with pytest.raises(ValueError, match="kesin azalmalıdır"):
        validate_convergence_request(request)


def test_validate_convergence_accepts_nonlinear_and_fingerprints_contact_controls() -> None:
    """@brief Nonlinear convergence requires identical contact and increment settings across meshes."""
    request = _study()
    for case in request["cases"]:
        analysis = case["analysis"]
        analysis.update({
            "schemaVersion": "1.1",
            "analysisType": "static_nonlinear",
            "nonlinearControls": {
                "initialIncrement": 0.1, "timePeriod": 1.0,
                "minimumIncrement": 1e-6, "maximumIncrement": 0.2,
                "maximumIncrements": 100,
            },
        })
    assert validate_convergence_request(request)["cases"][0]["analysis"]["analysisType"] == "static_nonlinear"
    request["cases"][1]["analysis"]["nonlinearControls"]["maximumIncrement"] = 0.25
    with pytest.raises(ValueError, match="aynı olmalıdır"):
        validate_convergence_request(request)


def test_validate_convergence_rejects_changed_physics() -> None:
    """@brief Never silently change materials, loads, or constraints between meshes."""
    request = _study()
    request["cases"][2]["analysis"]["material"]["elasticModulusMPa"] = 70000
    with pytest.raises(ValueError, match="malzeme, yük ve constraint"):
        validate_convergence_request(request)


def test_run_convergence_compares_last_two_real_result_summaries(tmp_path: Path, monkeypatch) -> None:
    """@brief Use every solve result and return auditable relative changes."""
    values = {
        "coarse": (1.0, 100.0),
        "medium": (1.04, 104.0),
        "fine": (1.05, 105.0),
    }

    def fake_run(analysis, output_dir, timeout_seconds):
        case_id = analysis["analysisId"].rsplit("_", 1)[-1]
        displacement, stress = values[case_id]
        artifact = Path(output_dir) / f"{case_id}.frd"
        artifact.write_text("result", encoding="ascii")
        return {
            "status": "review_required",
            "error_code": None,
            "artifacts": [{"path": str(artifact), "producedThisRun": True}],
            "resultEvidence": {"summary": {
                "maximumDisplacementMm": displacement,
                "maximumVonMisesStressMPa": stress,
                "solverVersion": "2.23",
            }},
        }

    monkeypatch.setattr("scripts.fea_convergence.run_analysis", fake_run)
    report = run_convergence_study(_study(), tmp_path)

    assert report["status"] == "review_required"
    assert report["converged"] is True
    assert report["error_code"] is None
    assert len(report["cases"]) == 3
    assert report["changes"][-1]["displacementChangePercent"] == pytest.approx(0.9523809524)
    assert report["changes"][-1]["stressChangePercent"] == pytest.approx(0.9523809524)
    assert Path(report["reportPath"]).is_file()


def test_run_convergence_retains_nonconverged_review_gate(tmp_path: Path, monkeypatch) -> None:
    """@brief Excessive final-two-mesh changes must not be reported as convergence."""
    call = 0

    def fake_run(_analysis, _output_dir, timeout_seconds):
        nonlocal call
        call += 1
        return {
            "status": "review_required",
            "error_code": None,
            "artifacts": [],
            "resultEvidence": {"summary": {
                "maximumDisplacementMm": float(call),
                "maximumVonMisesStressMPa": float(call * 100),
                "solverVersion": "2.23",
            }},
        }

    monkeypatch.setattr("scripts.fea_convergence.run_analysis", fake_run)
    report = run_convergence_study(_study(), tmp_path)
    assert report["converged"] is False
    assert report["error_code"] == "fea_mesh_convergence_not_reached"
    assert report["retryable"] is True
