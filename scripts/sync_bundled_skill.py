"""Build the runtime skill snapshot embedded in the CAD Studio desktop package."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SKILL = ROOT / "apps/workbench-ui/src-tauri/resources/skill"

TOP_LEVEL_FILES = (
    "README.md",
    "README.tr.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SKILL.md",
    "SUBSKILLS.md",
    "capabilities.yaml",
    "golden-workflows.yaml",
    "requirements.txt",
    "requirements-mesh.txt",
    "requirements-occt.txt",
    "requirements-pdf.txt",
)
RUNTIME_ROOTS = (
    "agents",
    "dotnet",
    "docs",
    "examples",
    "mcp-server",
    "localization",
    "references",
    "scripts",
    "subskills",
    "apps/desktop/cad_workbench",
)
RUNTIME_FILES = (
    "apps/desktop/__init__.py",
    "apps/desktop/README.md",
    "apps/workbench-ui/README.md",
    "apps/workbench-ui/README.tr.md",
)
SKIPPED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "output",
    "release-output",
}
SKIPPED_SUFFIXES = {".pyc", ".pyo"}


def _validate_target(root: Path, target: Path) -> None:
    """@brief Restrict synchronization targets to repository Tauri resources/skill."""
    expected_parent = (root / "apps/workbench-ui/src-tauri/resources").resolve()
    resolved_target = target.resolve()
    if resolved_target.parent != expected_parent or resolved_target.name != "skill":
        raise ValueError(f"Beklenmeyen gömülü skill dizinine yazma reddedildi: {resolved_target}")


def _is_runtime_file(path: Path, source_root: Path) -> bool:
    """@brief Exclude caches, build artifacts, and bytecode; retain distributable sources."""
    relative = path.relative_to(source_root)
    return not any(part in SKIPPED_DIRECTORIES for part in relative.parts) and path.suffix.casefold() not in SKIPPED_SUFFIXES


def collect_runtime_files(root: Path) -> dict[Path, Path]:
    """@brief Collect bundled skill sources keyed by repository-relative path."""
    files: dict[Path, Path] = {}
    for relative_name in (*TOP_LEVEL_FILES, *RUNTIME_FILES):
        source = root / relative_name
        if not source.is_file():
            raise FileNotFoundError(f"Gömülü skill kaynak dosyası eksik: {source}")
        files[Path(relative_name)] = source
    for relative_root in RUNTIME_ROOTS:
        source_root = root / relative_root
        if not source_root.is_dir():
            raise FileNotFoundError(f"Gömülü skill kaynak dizini eksik: {source_root}")
        for source in source_root.rglob("*"):
            if source.is_file() and _is_runtime_file(source, source_root):
                files[source.relative_to(root)] = source
    return files


def sync_bundled_skill(root: Path = ROOT, target: Path = BUNDLED_SKILL) -> dict[str, object]:
    """@brief Synchronize runtime files and remove stale target copies with no source."""
    root = root.resolve()
    target = target.resolve()
    _validate_target(root, target)
    source_files = collect_runtime_files(root)
    target.mkdir(parents=True, exist_ok=True)
    for relative_path, source in source_files.items():
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    pruned: list[str] = []
    expected = set(source_files)
    for bundled_file in sorted(path for path in target.rglob("*") if path.is_file()):
        relative_path = bundled_file.relative_to(target)
        if relative_path not in expected:
            bundled_file.unlink()
            pruned.append(relative_path.as_posix())
    for directory in sorted((path for path in target.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return {
        "status": "pass",
        "target": str(target),
        "files": len(source_files),
        "pruned": pruned,
    }


def main() -> int:
    """@brief Command-line entry point."""
    parser = argparse.ArgumentParser(description="CAD Studio gömülü skill dosyalarını eşitle")
    parser.parse_args()
    print(json.dumps(sync_bundled_skill(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
