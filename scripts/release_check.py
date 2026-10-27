"""Static consistency gate before release."""
from __future__ import annotations

import json
import re
from filecmp import cmp
from pathlib import Path

try:
    from .sync_bundled_skill import collect_runtime_files
except ImportError:
    from sync_bundled_skill import collect_runtime_files

ROOT = Path(__file__).resolve().parents[1]
BUNDLED_SKILL = ROOT / "apps/workbench-ui/src-tauri/resources/skill"


def _version(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    if not match:
        raise AssertionError(f"Sürüm okunamadı: {path}")
    return match.group(1)


def find_bundled_skill_drift(root: Path, bundled_skill: Path, expected_paths=None) -> list[str]:
    """@brief Return relative paths missing or inconsistent in the desktop bundled skill."""
    if not bundled_skill.is_dir():
        return ["<bundled-skill-missing>"]
    drift: list[str] = []
    for bundled_path in sorted(path for path in bundled_skill.rglob("*") if path.is_file()):
        relative_path = bundled_path.relative_to(bundled_skill)
        source_path = root / relative_path
        relative_name = relative_path.as_posix()
        if not source_path.is_file():
            drift.append(f"missing-source:{relative_name}")
        else:
            try:
                if not cmp(source_path, bundled_path, shallow=False):
                    drift.append(relative_name)
            except FileNotFoundError:
                # Tauri build.rs rebuilds resources/skill without full atomicity; concurrent checks
                # record transient disappearance as missing rather than leaking a filesystem exception.
                drift.append(f"missing-bundle:{relative_name}")
    for relative_path in sorted(expected_paths or [], key=lambda value: Path(value).as_posix()):
        relative = Path(relative_path)
        if not (bundled_skill / relative).is_file():
            drift.append(f"missing-bundle:{relative.as_posix()}")
    return drift


def run_release_check() -> dict[str, object]:
    """@brief Validate application versions, the capability source of truth, and required release files."""
    ui_version = _version(ROOT / "apps/workbench-ui/package.json", r'"version"\s*:\s*"([^"]+)"')
    tauri_version = _version(ROOT / "apps/workbench-ui/src-tauri/tauri.conf.json", r'"version"\s*:\s*"([^"]+)"')
    cargo_version = _version(ROOT / "apps/workbench-ui/src-tauri/Cargo.toml", r'(?m)^version\s*=\s*"([^"]+)"')
    app_version = _version(ROOT / "apps/workbench-ui/src/App.tsx", r'const APP_VERSION\s*=\s*"([^"]+)"')
    if len({ui_version, tauri_version, cargo_version, app_version}) != 1:
        raise AssertionError(f"Sürüm uyuşmazlığı: npm={ui_version}, tauri={tauri_version}, cargo={cargo_version}, app={app_version}")
    manifest = json.loads((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    capabilities = manifest.get("capabilities", [])
    ids = [item.get("id") for item in capabilities]
    if len(ids) != len(set(ids)) or len(ids) < 10:
        raise AssertionError("Capability listesinde yinelenen ID veya yetersiz kayıt var")
    required = [
        "SKILL.md",
        "README.md",
        "capabilities.yaml",
        "scripts/stability_regression.py",
        "scripts/release_check.py",
        "scripts/dfm_review.py",
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    if missing:
        raise AssertionError("Eksik sürüm dosyası: " + ", ".join(missing))
    expected_runtime_files = collect_runtime_files(ROOT)
    bundled_drift = find_bundled_skill_drift(ROOT, BUNDLED_SKILL, expected_runtime_files)
    if bundled_drift:
        preview = ", ".join(bundled_drift[:10])
        suffix = " ..." if len(bundled_drift) > 10 else ""
        raise AssertionError(f"Masaüstü gömülü skill ile kök skill farklı: {preview}{suffix}")
    bundled_file_count = sum(1 for path in BUNDLED_SKILL.rglob("*") if path.is_file())
    return {
        "status": "pass",
        "version": ui_version,
        "capabilities": len(capabilities),
        "bundled_skill_files": bundled_file_count,
        "missing": [],
    }


if __name__ == "__main__":
    print(json.dumps(run_release_check(), ensure_ascii=False, indent=2))
