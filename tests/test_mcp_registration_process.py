"""@brief Probe actual Node/Python arguments and interpreter provenance without changing user MCP configuration."""
from pathlib import Path
import subprocess
import sys
import json


def test_python_probe_uses_native_argv_stdin_and_resolved_executable():
    root = Path(__file__).resolve().parents[1]
    code = "const r=require('./mcp-server/register_all_ai_mcp.js'); console.log(JSON.stringify({python:r.resolvePython(process.argv[1])}));"
    result = subprocess.run(["node", "-e", code, sys.executable], cwd=root, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert Path(json.loads(result.stdout)["python"]).resolve() == Path(sys.executable).resolve()
