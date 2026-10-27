'Offline provenance and acceptance-gate tests for open-source complex CNC cases.'

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "subskills" / "solidworks-fillet-chamfer-cnc" / "scripts" / "verify_open_source_complex_case.py"
MANIFEST = ROOT / "subskills" / "solidworks-fillet-chamfer-cnc" / "examples" / "open_source_corner_bracket_case.json"
SPEC = importlib.util.spec_from_file_location("open_source_cnc_case", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_pinned_manifest_contains_commit_hash_and_attribution() -> None:
    'Network cases require pinned commit, hash, license and attribution.'
    case = MODULE.load_case(MANIFEST)

    assert case["commit"] in case["download_url"]
    assert len(case["sha256"]) == 64
    assert case["license"] == "CC BY 3.0"
    assert "FreeCAD" in case["attribution"]
    assert case["advanced_operation"]["kind"] == "width_width_chamfer"
    assert case["advanced_operation"]["widths_mm"] == [0.2, 0.4]


def test_cached_source_is_verified_without_network(tmp_path, monkeypatch) -> None:
    'Cached source files still require byte-for-byte SHA-256 verification.'
    content = b"ISO-10303-21; pinned fixture"
    destination = tmp_path / "fixture.step"
    destination.write_bytes(content)
    case = {
        "download_url": "https://raw.githubusercontent.com/owner/repo/" + "a" * 40 + "/fixture.step",
        "sha256": hashlib.sha256(content).hexdigest(),
        "commit": "a" * 40,
        "license": "CC BY 3.0",
        "attribution": "fixture",
    }

    def reject_network(*args, **kwargs):
        'Reading a cached file must not request the network, even for a valid manifest.'
        pytest.fail('Unexpected network request while reading a valid cache')

    monkeypatch.setattr(MODULE, "read_https_response", reject_network)
    evidence = MODULE.fetch_pinned_source(case, destination)

    assert evidence["source"] == "cache"
    assert evidence["bytes"] == len(content)


def test_complexity_gate_rejects_empty_or_simplified_models() -> None:
    'Single-body checks must not conceal incorrect imports with too few faces/edges.'
    assert MODULE.topology_is_complex({"solids": 1, "faces": 40, "edges": 98, "vertices": 64})
    assert not MODULE.topology_is_complex({"solids": 1, "faces": 6, "edges": 12, "vertices": 8})
    assert not MODULE.topology_is_complex({"solids": 2, "faces": 40, "edges": 98, "vertices": 64})


def test_expected_source_topology_rejects_drift() -> None:
    'Pinned cases must match exact declared topology, not just minimum counts.'
    case = {"expected_source_topology": {"solids": 1, "faces": 40, "edges": 98}}
    MODULE.assert_expected_source_topology(case, {"solids": 1, "faces": 40, "edges": 98})

    with pytest.raises(RuntimeError, match='topology drift'):
        MODULE.assert_expected_source_topology(case, {"solids": 1, "faces": 39, "edges": 98})
