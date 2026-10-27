"""
SOLIDWORKS automation skill preflight.

Handle two startup risks:
1. Ask for authorization before automatically installing missing Python COM dependencies with pip.
2. Stop if SOLIDWORKS is unavailable and explain manual installation or COM registration repair.
"""
from __future__ import annotations

import argparse
import importlib
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence

try:
    from .cad_installation import discover_installation
except ImportError:
    from cad_installation import discover_installation


PIP_REQUIREMENTS = ("pywin32>=305", "comtypes>=1.2.0")
DEPENDENCY_PROMPT = "Python ortamında comtypes / win32com eksik. AI aracısının yerel ortamı otomatik yapılandırmasına izin veriyor musunuz? [Y/N]"


def _configure_stdio_utf8() -> None:
    """Prefer UTF-8 diagnostics on Windows systems with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_stdio_utf8()


class DependencyInstallDeclined(RuntimeError):
    """Kullanıcı Python COM bağımlılıklarının otomatik kurulumunu reddetti."""


class SolidWorksNotInstalledError(RuntimeError):
    """Bu sistemde SOLIDWORKS bulunamadı."""


@dataclass
class PreflightResult:
    """Preflight result."""

    missing_packages: List[str]
    dependencies_ready: bool
    solidworks_ready: Optional[bool]


def _module_available(module_name: str) -> bool:
    """Check whether a Python module is importable."""
    try:
        importlib.import_module(module_name)
        return True
    except ModuleNotFoundError as exc:
        requested_root = module_name.split(".", 1)[0]
        if exc.name in {module_name, requested_root}:
            return False
        raise


def missing_com_dependencies() -> List[str]:
    """Return missing COM dependency package names."""
    checks = (
        ("comtypes", "comtypes>=1.2.0"),
        ("pythoncom", "pywin32>=305"),
        ("win32com.client", "pywin32>=305"),
    )
    missing: List[str] = []
    for module_name, requirement in checks:
        if not _module_available(module_name) and requirement not in missing:
            missing.append(requirement)
    return missing


def pip_install_command(
    python_executable: Optional[str] = None,
    requirements: Sequence[str] = PIP_REQUIREMENTS,
) -> List[str]:
    """Build a pip command to install missing dependencies."""
    return [python_executable or sys.executable, "-m", "pip", "install", *requirements]


def shell_command_text(command: Sequence[str]) -> str:
    """Build a command string suitable for a Windows shell."""
    special_chars = set(' <>&|^"')
    parts = []
    for part in command:
        text = str(part)
        if any(char in special_chars for char in text):
            parts.append('"' + text.replace('"', r'\"') + '"')
        else:
            parts.append(text)
    return " ".join(parts)


def install_com_dependencies(
    python_executable: Optional[str] = None,
    requirements: Sequence[str] = PIP_REQUIREMENTS,
) -> None:
    """Run pip to install missing Python COM dependencies."""
    subprocess.check_call(pip_install_command(python_executable, requirements))
    importlib.invalidate_caches()


def ask_install_permission(
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> bool:
    """Request authorization to configure the local Python environment automatically."""
    output_func(DEPENDENCY_PROMPT)
    try:
        answer = input_func("").strip().lower()
    except EOFError:
        answer = ""
    return answer in {"y", "yes", "e", "evet"}


def ensure_com_dependencies(
    allow_install: Optional[bool] = None,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> List[str]:
    """
    Ensure comtypes / pywin32 are available.

    Args:
        allow_install: True installs directly, False declines, None asks interactively.
        input_func: Replaceable input function for tests.
        output_func: Replaceable output function for tests.

    Returns:
        Dependencies missing at entry.
    """
    missing = missing_com_dependencies()
    if not missing:
        return []

    should_install = allow_install
    if should_install is None:
        should_install = ask_install_permission(input_func=input_func, output_func=output_func)

    if not should_install:
        command = shell_command_text(pip_install_command())
        raise DependencyInstallDeclined(
            "Python ortamında SOLIDWORKS COM bağımlılıkları eksik. Elle çalıştırın:\n"
            f"{command}"
        )

    install_com_dependencies(requirements=tuple(missing))
    still_missing = missing_com_dependencies()
    if still_missing:
        raise ModuleNotFoundError(
            "Kurulum sonrasında hâlâ içe aktarılamayan bağımlılıklar: " + ", ".join(still_missing)
        )
    return missing


def import_com_dependencies(allow_install: Optional[bool] = None):
    """
    Import pythoncom, win32com, and VARIANT.

    Replace eager module-level imports to provide actionable diagnostics instead of a bare ModuleNotFoundError.
    """
    ensure_com_dependencies(allow_install=allow_install)
    pythoncom = importlib.import_module("pythoncom")
    client = importlib.import_module("win32com.client")
    return pythoncom, client, client.VARIANT


def _is_windows() -> bool:
    """Check whether the current system is Windows."""
    return os.name == "nt" or platform.system().lower().startswith("win")


def _solidworks_com_registered() -> bool:
    """Check SOLIDWORKS COM ProgID registration."""
    return bool(discover_installation("solidworks")["registered"])


def _solidworks_exe_candidates() -> Iterable[str]:
    """Enumerate common SOLIDWORKS executable locations."""
    executable = discover_installation("solidworks")["executable"]
    if executable:
        yield executable


def solidworks_installed() -> bool:
    """Detect a local SOLIDWORKS installation or COM registration."""
    if not _is_windows():
        return False
    installation = discover_installation("solidworks")
    if installation["registered"]:
        return True
    return bool(installation["executable"] and os.path.exists(installation["executable"]))


def ensure_solidworks_installed() -> None:
    """Stop immediately with clear guidance if SOLIDWORKS is unavailable."""
    if solidworks_installed():
        return
    raise SolidWorksNotInstalledError(
        "SOLIDWORKS bulunamadı. Önce elle kurun ve COM kaydını tamamlamak için en az bir kez başlatın; ardından bu skill aracını kullanın."
    )


def run_preflight(
    allow_install: Optional[bool] = None,
    check_solidworks: bool = True,
) -> PreflightResult:
    """Check dependencies and SOLIDWORKS installation status."""
    solidworks_ready: Optional[bool] = None
    if check_solidworks:
        ensure_solidworks_installed()
        solidworks_ready = True
    missing = ensure_com_dependencies(allow_install=allow_install)
    return PreflightResult(
        missing_packages=missing,
        dependencies_ready=True,
        solidworks_ready=solidworks_ready,
    )


def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="SOLIDWORKS otomasyon skill ön denetimi.")
    parser.add_argument("--yes", action="store_true", help="Eksik bağımlılıkların kurulumuna doğrudan izin ver.")
    parser.add_argument("--no-install", action="store_true", help="Eksik bağımlılıkları otomatik kurma.")
    parser.add_argument("--no-solidworks-check", action="store_true", help="SOLIDWORKS kurulum denetimini atla.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = _parse_args()
    allow_install = True if args.yes else False if args.no_install else None
    result = run_preflight(
        allow_install=allow_install,
        check_solidworks=not args.no_solidworks_check,
    )
    print("SOLIDWORKS otomasyon skill ön denetimi başarılı.")
    if result.missing_packages:
        print("Kurulan bağımlılıklar: " + ", ".join(result.missing_packages))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DependencyInstallDeclined as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
    except SolidWorksNotInstalledError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(3)
