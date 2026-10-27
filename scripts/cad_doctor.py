"""CAD Studio environment diagnostics CLI.

Read environment information without starting or closing CAD. Return JSON for the
desktop and CI, using stable check IDs and statuses to identify installation,
dependency and permission problems.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
from cad_installation import discover_all, discover_installations


_AGENT_DOWNLOADS = {
    "codex": "https://developers.openai.com/codex/cli/",
    "claude": "https://docs.anthropic.com/en/docs/claude-code/overview",
    "gemini": "https://github.com/google-gemini/gemini-cli",
    "opencode": "https://opencode.ai/",
}


def _check(
    name: str,
    ok: bool,
    message: str,
    *,
    severity: str = "error",
    code: str | None = None,
    action: str | None = None,
    install_command: str | None = None,
    download_url: str | None = None,
    required: bool = False,
) -> dict[str, Any]:
    """@brief Construct a stable check with actionable repair information on failure."""
    result: dict[str, Any] = {
        "id": name,
        "status": "passed" if ok else severity,
        "code": code or name.upper(),
        "message": message,
    }
    if not ok:
        if action:
            result["action"] = action
        if install_command:
            result["installCommand"] = install_command
        if download_url:
            result["downloadUrl"] = download_url
        result["required"] = required
    return result


def _collect_remediations(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """@brief Convert failed checks into deduplicated desktop/CLI repair actions."""
    remediations: list[dict[str, Any]] = []
    seen: set[str] = set()
    agent_available = any(
        item["id"].startswith("agent.") and item["status"] == "passed"
        for item in checks
    )
    for item in checks:
        if item["status"] == "passed" or not item.get("action"):
            continue
        # Agent CLIs are alternatives: finding one suppresses suggestions to install other providers.
        if agent_available and item["id"].startswith("agent."):
            continue
        remediation_id = str(item["id"])
        if remediation_id in seen:
            continue
        seen.add(remediation_id)
        remediation = {
            "id": remediation_id,
            "title": item["action"],
            "reason": item["message"],
            "required": bool(item.get("required", False)),
        }
        for source, target in (("installCommand", "installCommand"), ("downloadUrl", "downloadUrl")):
            if item.get(source):
                remediation[target] = item[source]
        remediations.append(remediation)
    return remediations


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".cad-studio-doctor-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _solidworks_installation() -> dict[str, Any]:
    installation = discover_all()["solidworks"]
    available = discover_installations("solidworks")
    return {
        "registered": installation["registered"],
        "executables": [installation["executable"]] if installation["executable"] else [],
        "executable": installation["executable"],
        "source": installation["source"],
        "version": installation["version"],
        "servicePack": installation.get("servicePack"),
        "displayName": installation.get("displayName"),
        "shortcut": installation["shortcut"],
        "available": available,
    }


def run_doctor(*, probe_cad: bool = False) -> dict[str, Any]:
    """Run diagnostics and return redacted JSON data."""
    checks: list[dict[str, Any]] = []
    python_ready = sys.version_info >= (3, 10)
    checks.append(_check(
        "python",
        python_ready,
        f"Python {platform.python_version()}" if python_ready else f"Python {platform.python_version()} önerilen 3.10 sürümünden eski",
        code="PYTHON_VERSION_UNSUPPORTED" if not python_ready else "PYTHON_READY",
        action="Python 3.10 veya daha yeni sürümünü yükleyin",
        install_command="winget install -e --id Python.Python.3.12",
        download_url="https://www.python.org/downloads/windows/",
        required=True,
    ))
    dependencies = (
        (("win32com.client",), "pywin32", "warning", "SolidWorks COM otomasyon bağımlılıklarını yükleyin", 'python -m pip install "pywin32>=305"', "https://pypi.org/project/pywin32/"),
        (("comtypes",), "comtypes", "warning", "Windows COM uyumluluk bağımlılıklarını yükleyin", 'python -m pip install "comtypes>=1.2.0"', "https://pypi.org/project/comtypes/"),
        (("ezdxf",), "ezdxf", "warning", "Headless DXF okuma/yazma bağımlılıklarını yükleyin", 'python -m pip install "ezdxf>=1.3,<2"', "https://pypi.org/project/ezdxf/"),
        (("OCP",), "OCP", "warning", "OCCT açık format geometri backend yükleyin", "python -m pip install -r requirements-occt.txt", "https://pypi.org/project/cadquery-ocp/"),
        (("fitz", "pymupdf"), "PyMuPDF", "warning", "PDF önizleme ve metin inceleme bağımlılıklarını yükleyin", "python -m pip install -r requirements-pdf.txt", "https://pymupdf.readthedocs.io/en/latest/installation.html"),
    )
    for module_names, label, severity, action, install_command, download_url in dependencies:
        available = False
        for module_name in module_names:
            try:
                available = available or importlib.util.find_spec(module_name) is not None
            except (ImportError, ModuleNotFoundError):
                continue
        checks.append(_check(
            f"python.{label.lower()}",
            available,
            f"{label} {'Yüklü' if available else 'Yüklü değil; yalnızca ilgili capability etkilenir, diğer backend seçenekleri kullanılabilir'}",
            severity=severity,
            code="DEPENDENCY_MISSING" if not available else "DEPENDENCY_READY",
            action=action,
            install_command=install_command,
            download_url=download_url,
        ))

    try:
        from fea_analysis import discover_solver

        calculix = discover_solver("calculix")
        calculix_ready = calculix.get("status") == "pass"
    except Exception:
        calculix_ready = False
    checks.append(_check(
        "solver.calculix",
        calculix_ready,
        "CalculiX bulundu" if calculix_ready else "CalculiX bulunamadı; yalnızca açık FEA çözümü engellenir, modelleme, çizimler ve önizleme etkilenmez",
        severity="warning",
        code="CALCULIX_READY" if calculix_ready else "CALCULIX_NOT_FOUND",
        action="CalculiX indirin ve CADSTUDIO_CALCULIX_EXE değerini ccx.exe konumuna ayarlayın",
        download_url="https://www.calculix.de/",
    ))

    for cli in ("codex", "claude", "gemini", "opencode"):
        found = shutil.which(cli) or shutil.which(f"{cli}.exe")
        checks.append(_check(
            f"agent.{cli}",
            bool(found),
            f"{cli}: {'Bulundu' if found else 'Bulunamadı; desteklenen Agent CLI seçeneklerinden birini yükleyin'}",
            severity="warning",
            code="AGENT_NOT_FOUND" if not found else "AGENT_READY",
            action=f"Kur: {cli} CLI",
            download_url=_AGENT_DOWNLOADS[cli],
        ))

    sw = _solidworks_installation()
    sw_ready = bool(sw["registered"] or sw["executables"])
    checks.append(_check(
        "cad.solidworks",
        sw_ready,
        "SolidWorks COM veya kurulum dizini bulundu" if sw_ready else "SolidWorks bulunamadı; yalnızca SLDPRT/SLDASM/SLDDRW native formatları engellenir. STEP/IGES/BREP/STL/GLB gibi açık formatlar kullanılabilir",
        severity="warning",
        code="SOLIDWORKS_READY" if sw_ready else "SOLIDWORKS_NOT_FOUND",
        action="SolidWorks native formatları için resmi kanaldan yükleyip lisansını etkinleştirin",
        download_url="https://www.solidworks.com/",
    ))
    autocad = discover_all()["autocad"]
    autocad_ready = bool(autocad["installed"])
    checks.append(_check(
        "cad.autocad",
        autocad_ready,
        "AutoCAD kurulumu bulundu" if autocad_ready else "AutoCAD bulunamadı; yalnızca native DWG backend engellenir. Headless DXF/SVG/PDF/PNG çıktıları kullanılabilir",
        severity="warning",
        code="AUTOCAD_READY" if autocad_ready else "AUTOCAD_NOT_FOUND",
        action="Native DWG için Autodesk resmi kanalından yükleyip lisansını etkinleştirin",
        download_url="https://www.autodesk.com/products/autocad/overview",
    ))

    documents = Path.home() / "Documents"
    documents_writable = _is_writable(documents)
    checks.append(_check(
        "filesystem.documents",
        documents_writable,
        f"Belge dizini yazılabilir: {documents.name}",
        code="DOCUMENTS_READY" if documents_writable else "DOCUMENTS_NOT_WRITABLE",
        action="Geçerli kullanıcıya belge dizini yazma izni verin veya CAD Studio içinde başka çıktı dizini seçin",
        required=True,
    ))
    temp_writable = _is_writable(Path(os.environ.get("TEMP", str(Path.home()))))
    checks.append(_check(
        "filesystem.temp",
        temp_writable,
        "Geçici dizin yazılabilir",
        code="TEMP_READY" if temp_writable else "TEMP_NOT_WRITABLE",
        action="Geçerli kullanıcının geçici dizin izinlerini düzeltip diagnostics işlemini yineleyin",
        required=True,
    ))

    if probe_cad and sw["registered"]:
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            from sw_connect import connect_solidworks

            app, _ = connect_solidworks(wait_seconds=8, visible=False)
            checks.append(_check("cad.solidworks.com", app is not None, "SolidWorks COM bağlantısı başarılı", code="SOLIDWORKS_COM_FAILED"))
        except Exception as exc:  # pragma: no cover - requires a real Windows environment
            checks.append(_check("cad.solidworks.com", False, str(exc), code="SOLIDWORKS_COM_FAILED"))

    errors = sum(item["status"] == "error" for item in checks)
    warnings = sum(item["status"] == "warning" for item in checks)
    remediations = _collect_remediations(checks)
    return {
        "schemaVersion": "1.0",
        "tool": "cad-studio doctor",
        "platform": platform.platform(aliased=True),
        "python": {"version": platform.python_version(), "executable": Path(sys.executable).name},
        "installations": {
            "solidworks": {key: value for key, value in sw.items() if key != "executables"},
            "autocad": autocad,
        },
        "checks": checks,
        "remediations": remediations,
        "summary": {"status": "error" if errors else ("warning" if warnings else "passed"), "errors": errors, "warnings": warnings},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAD Studio yerel çalışma ortamını denetle")
    parser.add_argument("--probe-cad", action="store_true", help="COM kayıtlıysa SolidWorks bağlantısını dene")
    parser.add_argument("--output", type=Path, help="JSON dosyasına yaz")
    args = parser.parse_args(argv)
    result = run_doctor(probe_cad=args.probe_cad)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if result["summary"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
