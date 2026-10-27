'Advanced SolidWorks capability-probe gates.'
from pathlib import Path

from scripts import sw_capability_probe


class _PythonCom:
    'Placeholder COM module for tests.'


def test_advanced_interfaces_do_not_inherit_unrelated_verified_levels(monkeypatch):
    'Type-library presence cannot promote surfaces, molds or Routing to verified.'
    type_names = [
        "ISurface",
        "IKnitSurfaceFeatureData",
        "IMold",
        "ICavityFeatureData",
        "IRouteManager",
        "IRouteProperty",
        "IAutoRoute",
    ]
    monkeypatch.setattr(sw_capability_probe, "missing_com_dependencies", lambda: [])
    monkeypatch.setattr(sw_capability_probe, "solidworks_installed", lambda: True)
    monkeypatch.setattr(sw_capability_probe, "import_com_dependencies", lambda allow_install=False: (_PythonCom(), None, None))
    monkeypatch.setattr(sw_capability_probe, "_find_typelib", lambda patterns: Path("installed.tlb"))
    monkeypatch.setattr(sw_capability_probe, "_type_names", lambda pythoncom, path: type_names)

    report = sw_capability_probe.probe_capabilities()

    assert report["capabilities"]["surface_modeling"]["manifest_capability_id"] == "surface_modeling"
    assert report["capabilities"]["surface_modeling"]["implementation_status"] == "pilot"
    assert report["capabilities"]["mold_tools"]["manifest_capability_id"] == "mold_tools"
    assert report["capabilities"]["mold_tools"]["implementation_status"] == "pilot"
    assert report["capabilities"]["routing"]["interfaces_found"] == ["IRouteManager", "IRouteProperty", "IAutoRoute"]
    assert report["capabilities"]["routing"]["implementation_status"] == "pilot"
    assert all(
        report["capabilities"][capability]["implementation_status"] != "verified"
        for capability in ("surface_modeling", "mold_tools", "routing")
    )
    assert all(
        report["capabilities"][capability]["ready_for_unattended_use"] is False
        for capability in ("surface_modeling", "mold_tools", "routing")
    )
