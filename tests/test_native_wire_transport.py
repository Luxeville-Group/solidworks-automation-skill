'Check complete stdin requests, target rejection and transfer-size limits.'
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import cad_installation, sw_native_wire as native


@pytest.fixture
def native_host(monkeypatch, tmp_path):
    'Stub installation and COM metadata without starting CAD or loading mock DLLs.'
    install = tmp_path / 'Kurulum yolu' / "SOLIDWORKS"
    redist = install / "api" / "redist"
    redist.mkdir(parents=True)
    (redist / "SolidWorks.Interop.sldworks.dll").touch()
    target = str(tmp_path / 'Türkçe_parça.sldprt')
    model = SimpleNamespace()
    sw = SimpleNamespace()
    metadata = {(id(sw), "ActiveDoc"): model, (id(sw), "GetProcessID"): 123, (id(model), "GetPathName"): target}
    # Stub connection metadata so offline transfer tests do not require Windows COM modules.
    monkeypatch.setitem(sys.modules, "scripts.sw_connect", SimpleNamespace(get_com_member=lambda obj, name: metadata[(id(obj), name)]))
    monkeypatch.setattr(cad_installation, "discover_installation", lambda product: {"executable": str(install / "SLDWORKS.exe")})
    return sw, target


def test_maximum_high_precision_spec_uses_short_command_and_utf8_stdin(native_host, monkeypatch):
    'Valid specs exceeding 32K command-line size arrive intact, including maximum counts and long names.'
    sw, target = native_host
    points = [[float(f"{i}.{axis}1234567890123") for axis in range(3)] for i in range(6)]
    spec = native.BuildSpec(
        sweeps=[{"name": "Wire" + str(i) + "x" * 90, "control_points_mm": points, "diameter_mm": .9} for i in range(64)],
        boxes=[{"name": "Box" + str(i), "bounds_mm": [0, 0, 0, 10, 10, 5]} for i in range(64)],
    )
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert len(subprocess.list2cmdline(command)) < 2048
        assert len(kwargs["input"].encode("utf-8")) > 32767
        assert kwargs["encoding"] == "utf-8"
        payload = json.loads(kwargs["input"])
        assert payload["source"] == target
        assert payload["process_id"] == 123
        assert payload["spec"] == json.loads(spec.model_dump_json())
        return SimpleNamespace(returncode=0, stdout='{"status":"ready","save_requested":false}', stderr="")

    monkeypatch.setattr(native.subprocess, "run", run)
    result = native.invoke_native(sw, target, "build", dry_run=True, spec=spec.model_dump())
    assert result["status"] == "ready"
    assert len(calls) == 1


def test_oversize_request_is_rejected_before_child_launch(native_host, monkeypatch):
    'Reject before launching subprocesses when UTF-8 byte limits are exceeded.'
    sw, target = native_host
    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: pytest.fail("Child must not start"))
    with pytest.raises(ValueError, match="exceeds 1 MiB"):
        native.invoke_native(sw, target, "exclude", body_names=['gövde' * (native.MAX_NATIVE_REQUEST_BYTES // 2)])


def test_target_mismatch_is_rejected_before_child_launch(native_host, monkeypatch):
    'Stdin transport preserves the existing active-document protection.'
    sw, target = native_host
    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: pytest.fail("Child must not start"))
    with pytest.raises(ValueError, match="target mismatch"):
        native.invoke_native(sw, target + ".other", "inspect")


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows PowerShell pipe contract")
def test_real_powershell_receives_large_utf8_request(tmp_path):
    'Use real PowerShell pipes to independently verify non-ASCII JSON beyond command-line limits.'
    script = tmp_path / 'Boru_doğrulama.ps1'
    script.write_text(
        "[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)\n"
        "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)\n"
        "$request=[Console]::In.ReadToEnd()\n"
        "[Console]::Out.Write($request)\n", encoding="utf-8-sig",
    )
    request = json.dumps({'Yol': str(tmp_path / 'Türkçe_parça.sldprt'), "data": 'değer' * 20000}, ensure_ascii=False)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        input=request, capture_output=True, encoding="utf-8", timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == json.loads(request)
