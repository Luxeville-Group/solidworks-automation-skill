"""Open FEA schema, gate, and CalculiX input generation regressions."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.fea_analysis import build_calculix_input, discover_solver, parse_calculix_results, run_analysis, validate_analysis


def _request() -> dict:
    """@brief Return a single-tetrahedron static golden request."""
    return {
        "schemaVersion": "1.0",
        "analysisId": "bracket_static",
        "analysisType": "static_linear",
        "solver": "calculix",
        "units": {"length": "mm", "force": "N", "stress": "MPa", "temperature": "C"},
        "material": {"name": "Al6061", "elasticModulusMPa": 68900, "poissonRatio": 0.33, "densityKgM3": 2700},
        "mesh": {
            "nodes": [
                {"id": 1, "x": 0, "y": 0, "z": 0}, {"id": 2, "x": 10, "y": 0, "z": 0},
                {"id": 3, "x": 0, "y": 10, "z": 0}, {"id": 4, "x": 0, "y": 0, "z": 10},
            ],
            "elements": [{"id": 1, "type": "C3D4", "nodeIds": [1, 2, 3, 4]}],
            "nodeSets": {"FixedNodes": [1, 2, 3], "LoadNode": [4]},
            "elementSets": {"AllElements": [1]},
        },
        "constraints": [{"id": "fixed_base", "type": "fixed", "nodeSet": "FixedNodes"}],
        "loads": [{"id": "tip_force", "type": "force", "nodeSet": "LoadNode", "dof": 3, "value": -100}],
    }


def _nonlinear_request() -> dict:
    """@brief Return an FEA 1.1 request with plasticity and surface contact."""
    request = _request()
    request.update({
        "schemaVersion": "1.1",
        "analysisId": "contact_nonlinear",
        "analysisType": "static_nonlinear",
        "nonlinearControls": {
            "initialIncrement": 0.05,
            "timePeriod": 1.0,
            "minimumIncrement": 1e-5,
            "maximumIncrement": 0.1,
            "maximumIncrements": 200,
        },
        "surfaces": {
            "MasterFace": {"elementSet": "MasterElements", "face": "S1"},
            "SlaveFace": {"elementSet": "SlaveElements", "face": "S2"},
        },
        "contacts": [{
            "id": "interface", "masterSurface": "MasterFace", "slaveSurface": "SlaveFace",
            "frictionCoefficient": 0.2, "normalStiffnessMPaPerMm": 21000,
            "tangentialStickSlopeMPaPerMm": 10500,
        }],
    })
    request["mesh"]["elements"].append({"id": 2, "type": "C3D4", "nodeIds": [1, 2, 3, 4]})
    request["mesh"]["elementSets"].update({"MasterElements": [1], "SlaveElements": [2]})
    request["material"]["plasticCurve"] = [
        {"yieldStressMPa": 250, "plasticStrain": 0.0},
        {"yieldStressMPa": 300, "plasticStrain": 0.05},
    ]
    return request


def test_validate_analysis_accepts_consistent_mesh_and_references() -> None:
    """@brief Valid material, mesh, loads, and constraints must pass."""
    validated = validate_analysis(_request())
    assert validated["analysisId"] == "bracket_static"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda payload: payload.update({"analysisId": "bad\n*INCLUDE"}), "analysisId"),
        (lambda payload: payload["mesh"]["elements"][0].update({"nodeIds": [1, 2, 3, 99]}), "eksik"),
        (lambda payload: payload["material"].update({"poissonRatio": 0.5}), "poissonRatio"),
        (lambda payload: payload["loads"][0].update({"nodeSet": "Missing"}), "nodeSet"),
    ],
)
def test_validate_analysis_rejects_injection_and_invalid_engineering_references(mutator, message: str) -> None:
    """@brief Block injection, dangling topology references, and invalid materials."""
    payload = _request()
    mutator(payload)
    with pytest.raises(ValueError, match=message):
        validate_analysis(payload)


def test_calculix_input_is_whitelisted_and_never_overwrites(tmp_path: Path) -> None:
    """@brief Input decks contain fixed templates only; repeated generation uses versioned files."""
    output = tmp_path / "job.inp"
    first = build_calculix_input(_request(), output)
    second = build_calculix_input(_request(), output)
    first_path = Path(first["artifacts"][0]["path"])
    second_path = Path(second["artifacts"][0]["path"])
    content = first_path.read_text(encoding="ascii")
    assert first["status"] == "pass"
    assert first_path.name == "job.inp"
    assert second_path.name == "job_v2.inp"
    assert "*NODE" in content and "*ELEMENT,TYPE=C3D4" in content
    assert "*BOUNDARY" in content and "*CLOAD" in content
    assert first["artifacts"][0]["sha256"]


def test_calculix_sets_wrap_after_sixteen_ids(tmp_path: Path) -> None:
    """@brief NSET/ELSET lines must respect the CalculiX 16-item limit."""
    request = _request()
    request["mesh"]["nodes"].extend(
        {"id": node_id, "x": node_id, "y": 0, "z": 0}
        for node_id in range(5, 21)
    )
    request["mesh"]["nodeSets"]["ManyNodes"] = list(range(1, 21))
    result = build_calculix_input(request, tmp_path / "wrapped.inp")
    content = Path(result["artifacts"][0]["path"]).read_text(encoding="ascii").splitlines()
    start = content.index("*NSET,NSET=ManyNodes")
    member_lines = content[start + 1:start + 3]
    assert [len(line.split(",")) for line in member_lines] == [16, 4]


def test_nonlinear_contact_input_uses_only_whitelisted_keywords(tmp_path: Path) -> None:
    """@brief Geometric nonlinearity, plasticity, and contact generate fixed CalculiX keywords."""
    request = _nonlinear_request()
    assert validate_analysis(request)["analysisType"] == "static_nonlinear"
    report = build_calculix_input(request, tmp_path / "nonlinear.inp")
    content = Path(report["artifacts"][0]["path"]).read_text(encoding="ascii")
    assert "*STEP,NLGEOM,INC=200" in content
    assert "*PLASTIC\n250,0\n300,0.05" in content
    assert "*EL FILE\nS,E,PEEQ" in content
    assert "*SURFACE,NAME=MasterFace,TYPE=ELEMENT\nMasterElements,S1" in content
    assert "*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=LINEAR\n21000" in content
    assert "*FRICTION\n0.2,10500" in content
    assert "*CONTACT PAIR,INTERACTION=CADSTUDIO_CONTACT_interface,TYPE=SURFACE TO SURFACE" in content
    assert "*CONTACT FILE,FREQUENCY=999999,CONTACT ELEMENTS" in content
    assert "CDIS,CSTR" in content
    assert content.index("*CONTACT PAIR") < content.index("*STEP,NLGEOM")
    assert report["requestEvidence"] == {
        "geometricNonlinearity": True,
        "plasticCurvePointCount": 2,
        "contactPairCount": 1,
    }


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda payload: payload["nonlinearControls"].update({"initialIncrement": 2}), "minimum <= initial"),
        (lambda payload: payload["surfaces"]["MasterFace"].update({"face": "S5"}), "uygun değil"),
        (lambda payload: payload["contacts"][0].update({"masterSurface": "Missing"}), "tanımlanmış iki farklı surface"),
        (lambda payload: payload["material"]["plasticCurve"][1].update({"plasticStrain": 0}), "kesin artmalı"),
    ],
)
def test_nonlinear_extensions_reject_invalid_increment_surface_contact_and_curve(mutator, message: str) -> None:
    """@brief Reject invalid increments, faces, contacts, and plastic curves before writing files."""
    request = _nonlinear_request()
    mutator(request)
    with pytest.raises(ValueError, match=message):
        validate_analysis(request)


def test_pressure_requires_explicit_element_face_and_gravity_uses_defined_all_set(tmp_path: Path) -> None:
    """@brief Solid pressure requires a face; gravity references the generator-defined complete set."""
    pressure = _request()
    pressure["loads"] = [{"id": "pressure_load", "type": "pressure", "elementSet": "AllElements", "magnitude": 2.5}]
    with pytest.raises(ValueError, match="P1-P6"):
        validate_analysis(pressure)
    pressure["loads"][0]["face"] = "P1"
    assert validate_analysis(pressure)

    gravity = _request()
    gravity["loads"] = [{"id": "gravity_load", "type": "gravity", "magnitude": 9810, "direction": [0, 0, -1]}]
    result = build_calculix_input(gravity, tmp_path / "gravity.inp")
    content = Path(result["artifacts"][0]["path"]).read_text(encoding="ascii")
    assert "*ELSET,ELSET=CADSTUDIO_ALL_ELEMENTS" in content
    assert "CADSTUDIO_ALL_ELEMENTS,GRAV,9810" in content


def test_tetrahedral_pressure_rejects_nonexistent_face() -> None:
    """@brief C3D4 tetrahedra have P1–P4 only; never generate invalid P5/P6 pressure loads."""
    request = _request()
    request["loads"] = [{"id": "Pressure1", "type": "pressure", "elementSet": "AllElements", "face": "P5", "magnitude": 2.5}]
    with pytest.raises(ValueError, match="uygun değil"):
        validate_analysis(request)


def test_missing_solver_is_blocked_without_fake_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief A missing solver must not create a solve directory or results."""
    monkeypatch.delenv("CADSTUDIO_CALCULIX_EXE", raising=False)
    monkeypatch.delenv("CADSTUDIO_ELMER_EXE", raising=False)
    monkeypatch.setattr("scripts.fea_analysis.shutil.which", lambda _name: None)
    monkeypatch.setattr("scripts.fea_analysis._windows_user_environment", lambda _name: None)
    monkeypatch.setattr("scripts.fea_analysis._standard_solver_candidates", lambda _name: [])
    preflight = discover_solver("calculix")
    output = tmp_path / "results"
    result = run_analysis(_request(), output)
    assert preflight["status"] == "blocked"
    assert preflight["error_code"] == "fea_solver_missing"
    assert result["status"] == "blocked"
    assert result["stage"] == "preflight"
    assert result["artifacts"] == []
    assert not output.exists()


def test_run_contact_requires_copen_and_cpress_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief Contact tasks without COPEN/CPRESS cannot reach review_required."""
    executable = tmp_path / "ccx.exe"
    executable.write_bytes(b"test solver")
    monkeypatch.setattr(
        "scripts.fea_analysis.discover_solver",
        lambda _solver: {
            "status": "pass", "solver": "calculix", "executable": str(executable),
            "source": "test",
        },
    )
    monkeypatch.setattr(
        "scripts.fea_analysis.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        "scripts.fea_analysis.parse_calculix_results",
        lambda *_args: {
            "status": "pass", "error_code": None, "checks": [],
            "summary": {
                "maximumContactElementCount": 28,
                "contactNodeCount": 16,
                "contactComponents": ["CSLIP1", "CSLIP2"],
            },
            "files": [],
        },
    )

    report = run_analysis(_nonlinear_request(), tmp_path / "results")

    assert report["status"] == "failed"
    assert report["error_code"] == "fea_contact_fields_missing"
    assert report["retryable"] is True


def test_discover_solver_reads_windows_user_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief Read Windows user-level solver environment variables even before process refresh."""
    executable = tmp_path / "ccx.exe"
    executable.write_bytes(b"ccx")
    monkeypatch.delenv("CADSTUDIO_CALCULIX_EXE", raising=False)
    monkeypatch.setattr("scripts.fea_analysis.shutil.which", lambda _name: None)
    monkeypatch.setattr("scripts.fea_analysis._windows_user_environment", lambda _name: str(executable))
    monkeypatch.setattr("scripts.fea_analysis._standard_solver_candidates", lambda _name: [])
    report = discover_solver("calculix")
    assert report["status"] == "pass"
    assert report["executable"] == str(executable.resolve())
    assert report["source"].startswith("HKCU")


def test_parse_calculix_results_reports_displacement_stress_and_convergence(tmp_path: Path) -> None:
    """@brief FRD/STA parsing returns finite displacement, equivalent stress, and converged increments."""
    stem = "job"
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n"
        " -1         1 0.0 0.0 -2.0E-04\n -3\n"
        " -4  STRESS      6    1\n"
        " -1         1 -2.0 -2.0 -6.0 0.0 0.0 0.0\n -3\n"
        " -4  PE          1    1\n"
        " -1         1 1.25E-03\n -3\n"
        " 9999\n",
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text("     1          1     1     1  1.0  1.0  1.0\n", encoding="ascii")
    (tmp_path / f"{stem}.cvg").write_text(
        "     1     1     1     1       28  0.0  0.0  0.0  0.0\n",
        encoding="ascii",
    )
    report = parse_calculix_results(tmp_path, stem)
    assert report["status"] == "pass"
    assert report["summary"]["solverVersion"] == "2.23"
    assert report["summary"]["maximumDisplacementMm"] == pytest.approx(2.0e-4)
    assert report["summary"]["maximumVonMisesStressMPa"] == pytest.approx(4.0)
    assert report["summary"]["convergedIncrementCount"] == 1
    assert report["summary"]["maximumContactElementCount"] == 28
    assert report["summary"]["maximumEquivalentPlasticStrain"] == pytest.approx(1.25e-3)


def test_parse_calculix_results_reports_contact_penetration_pressure_and_slip(tmp_path: Path) -> None:
    """@brief Extract penetration, pressure, and tangential-slip evidence from the final CONTACT block."""
    stem = "contact_job"
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n -1         1 0.0 0.0 -2.0E-04\n -3\n"
        " -4  STRESS      6    1\n -1         1 -2.0 -2.0 -6.0 0.0 0.0 0.0\n -3\n"
        " -4  CONTACT     6    1\n"
        " -5  COPEN       1    2    1    0\n"
        " -5  CSLIP1      1    2    2    0\n"
        " -5  CSLIP2      1    2    3    0\n"
        " -5  CPRESS      1    2    4    0\n"
        " -5  CSHEAR1     1    2    5    0\n"
        " -5  CSHEAR2     1    2    6    0\n"
        " -1         1 -2.0E-03 3.0E-03 4.0E-03 12.5 1.0 2.0\n -3\n"
        " 9999\n",
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text("     1          1     1     1  1.0  1.0  1.0\n", encoding="ascii")
    report = parse_calculix_results(tmp_path, stem)
    assert report["status"] == "pass"
    assert report["summary"]["contactNodeCount"] == 1
    assert report["summary"]["maximumPenetrationMm"] == pytest.approx(0.002)
    assert report["summary"]["maximumContactPressureMPa"] == pytest.approx(12.5)
    assert report["summary"]["maximumContactSlipMm"] == pytest.approx(0.005)


def test_parse_calculix_results_rejects_nonfinite_contact_field(tmp_path: Path) -> None:
    """@brief Nonfinite contact COPEN/CPRESS values cannot enter valid results."""
    stem = "nonfinite_contact"
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n -1         1 0.0 0.0 0.2\n -3\n"
        " -4  STRESS      6    1\n -1         1 2.0 2.0 6.0 0.0 0.0 0.0\n -3\n"
        " -4  CONTACT     2    1\n"
        " -5  COPEN       1    2    1    0\n"
        " -5  CPRESS      1    2    2    0\n"
        " -1         1 NaN 12.5\n -3\n"
        " 9999\n",
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text(
        "     1          1     1     1  1.0  1.0  1.0\n",
        encoding="ascii",
    )

    report = parse_calculix_results(tmp_path, stem)

    assert report["status"] == "failed"
    assert report["error_code"] == "fea_result_incomplete_or_nonfinite"
    assert report["summary"]["finiteValues"] is False


def test_parse_calculix_results_uses_latest_complete_result_blocks(tmp_path: Path) -> None:
    """@brief Summarize only the final complete FRD increment; exclude older displacement and stress."""
    stem = "multi_step"
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n -1         1 0.0 0.0 9.0\n -3\n"
        " -4  STRESS      6    1\n -1         1 90.0 0.0 0.0 0.0 0.0 0.0\n -3\n"
        " -4  DISP        4    1\n -1         1 0.0 0.0 0.2\n -3\n"
        " -4  STRESS      6    1\n -1         1 2.0 2.0 6.0 0.0 0.0 0.0\n -3\n"
        " 9999\n",
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text("     1          1     1     1  1.0  1.0  1.0\n", encoding="ascii")
    report = parse_calculix_results(tmp_path, stem)
    assert report["status"] == "pass"
    assert report["summary"]["displacementNodeCount"] == 1
    assert report["summary"]["maximumDisplacementMm"] == pytest.approx(0.2)
    assert report["summary"]["maximumVonMisesStressMPa"] == pytest.approx(4.0)


@pytest.mark.parametrize(("token", "token_detected"), [("1.0E309", False), ("NaN", True)])
def test_parse_calculix_results_rejects_nonfinite_plastic_strain(
    tmp_path: Path,
    token: str,
    token_detected: bool,
) -> None:
    """@brief Nonfinite PEEQ must fail nonlinear results even when displacement/stress are finite."""
    stem = f"nonfinite_peeq_{token_detected}"
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n -1         1 0.0 0.0 0.2\n -3\n"
        " -4  STRESS      6    1\n -1         1 2.0 2.0 6.0 0.0 0.0 0.0\n -3\n"
        f" -4  PE          1    1\n -1         1 {token}\n -3\n"
        " 9999\n",
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text(
        "     1          1     1     1  1.0  1.0  1.0\n",
        encoding="ascii",
    )

    report = parse_calculix_results(tmp_path, stem)

    assert report["status"] == "failed"
    assert report["error_code"] == "fea_result_incomplete_or_nonfinite"
    assert report["summary"]["finiteValues"] is False
    assert report["summary"]["nonfiniteResultToken"] is token_detected


@pytest.mark.parametrize("defect", ["truncated", "mismatched_nodes", "duplicate_node", "failed_marker"])
def test_parse_calculix_results_rejects_incomplete_or_inconsistent_evidence(tmp_path: Path, defect: str) -> None:
    """@brief Truncation, mismatched/duplicate nodes, and failure keywords must not appear converged."""
    stem = "bad_job"
    displacement_rows = " -1         1 0.0 0.0 -2.0E-04\n"
    stress_rows = " -1         1 -2.0 -2.0 -6.0 0.0 0.0 0.0\n"
    terminator = " 9999\n"
    if defect == "mismatched_nodes":
        stress_rows = " -1         2 -2.0 -2.0 -6.0 0.0 0.0 0.0\n"
    elif defect == "duplicate_node":
        displacement_rows += displacement_rows
    elif defect == "truncated":
        terminator = ""
    (tmp_path / f"{stem}.frd").write_text(
        "    1UVERSION           Version 2.23\n"
        " -4  DISP        4    1\n" + displacement_rows + " -3\n"
        " -4  STRESS      6    1\n" + stress_rows + " -3\n" + terminator,
        encoding="ascii",
    )
    (tmp_path / f"{stem}.sta").write_text("     1          1     1     1  1.0  1.0  1.0\n" + ("ERROR: solver failed\n" if defect == "failed_marker" else ""), encoding="ascii")
    report = parse_calculix_results(tmp_path, stem)
    assert report["status"] == "failed"
    assert report["error_code"] == "fea_result_incomplete_or_nonfinite"


def test_run_non_static_analysis_blocks_before_creating_output(tmp_path: Path) -> None:
    """@brief Unimplemented analysis types must not leave task directories."""
    request = _request()
    request["analysisType"] = "modal"
    result = run_analysis(request, tmp_path / "results")
    assert result["status"] == "blocked"
    assert result["error_code"] == "fea_calculix_analysis_unsupported"
    assert not (tmp_path / "results").exists()


def test_fea_json_schema_is_valid_and_accepts_golden_request() -> None:
    """@brief Public schema and golden 1.0/1.1 requests must pass Draft 2020-12."""
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = Path(__file__).parents[1] / "apps" / "desktop" / "cad_workbench" / "schemas" / "fea_analysis.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_request(), schema)
    jsonschema.validate(_nonlinear_request(), schema)
