"""@file solidworks_drawing_version_matrix.py
@brief SolidWorks 2024/2025/2026 real-machine drawing regression matrix.

Start regression only for a registered exact-version ProgID. Record uninstalled versions as unavailable;
never fall back to the default ProgID and falsely report success for the requested version.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows systems may only produce a blocked matrix
    winreg = None


DEFAULT_YEARS = (2024, 2025, 2026)


def prog_id_for_year(year: int) -> str:
    """@brief Return the exact SolidWorks COM ProgID for a year."""
    year = int(year)
    if year < 2010 or year > 2035:
        raise ValueError(f"Unsupported SolidWorks version year: {year}")
    return f"SldWorks.Application.{year - 1992}"


def is_version_registered(year: int) -> bool:
    """@brief Check only the exact-version ProgID; a default ProgID may point to another year."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id_for_year(year)):
            return True
    except OSError:
        return False


def discover_registered_versions(years: Iterable[int] = DEFAULT_YEARS) -> dict[int, bool]:
    """@brief Return COM registration state for the target year."""
    return {int(year): is_version_registered(int(year)) for year in years}


def _default_regression_runner(output_root: Path, *, version: int, run_id: str) -> dict[str, Any]:
    """@brief Lazy-load single-version regression so offline matrix tests do not connect to COM."""
    from solidworks_week4_drawing_regression import run_regression

    return run_regression(output_root, version=version, run_id=run_id)


def run_matrix(
    output_root: Path,
    *,
    years: Iterable[int] = DEFAULT_YEARS,
    registered_versions: dict[int, bool] | None = None,
    runner: Callable[..., dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """@brief Run installed versions serially and write an auditable matrix report."""
    target_years = tuple(dict.fromkeys(int(year) for year in years))
    if not target_years:
        raise ValueError("Specify at least one SolidWorks year")
    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    registration = registered_versions if registered_versions is not None else discover_registered_versions(target_years)
    execute = runner or _default_regression_runner
    entries = []
    for year in target_years:
        prog_id = prog_id_for_year(year)
        if not registration.get(year, False):
            entries.append({
                "year": year,
                "prog_id": prog_id,
                "status": "unavailable",
                "reason": "exact_version_prog_id_not_registered",
            })
            continue
        version_root = output_root / f"SW{year}"
        try:
            result = execute(version_root, version=year, run_id=f"{run_id}_sw{year}")
            actual_year = int((result.get("solidworks") or {}).get("year", 0) or 0)
            if result.get("status") != "ok" or actual_year != year:
                entries.append({
                    "year": year,
                    "prog_id": prog_id,
                    "status": "failed",
                    "reason": "regression_failed_or_version_mismatch",
                    "actual_year": actual_year or None,
                    "result": result,
                })
            else:
                entries.append({
                    "year": year,
                    "prog_id": prog_id,
                    "status": "pass",
                    "actual_year": actual_year,
                    "revision": (result.get("solidworks") or {}).get("revision"),
                    "report": result.get("report"),
                    "output_dir": result.get("output_dir"),
                })
        except Exception as exc:
            entries.append({
                "year": year,
                "prog_id": prog_id,
                "status": "failed",
                "reason": "regression_exception",
                "error": str(exc),
            })
    passed = sum(item["status"] == "pass" for item in entries)
    failed = sum(item["status"] == "failed" for item in entries)
    unavailable = sum(item["status"] == "unavailable" for item in entries)
    status = "failed" if failed else "pass" if passed == len(entries) else "partial" if passed else "blocked"
    report = {
        "status": status,
        "run_id": run_id,
        "target_years": list(target_years),
        "summary": {"pass": passed, "failed": failed, "unavailable": unavailable},
        "versions": entries,
        "manual_review_required": True,
        "limitations": [
            "unavailable means only that the exact version is not registered locally, not that it is unsupported.",
            "The matrix must verify the readback year; default ProgID success cannot replace an exact-version result.",
        ],
    }
    report_path = output_root / f"solidworks-drawing-version-matrix-{run_id}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    '@brief Command-line entry point.'
    parser = argparse.ArgumentParser(description="Run the real SolidWorks drawing version matrix")
    parser.add_argument("--output-dir", default=str(Path(tempfile.gettempdir()) / "solidworks_drawing_version_matrix"))
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    report = run_matrix(
        Path(args.output_dir),
        years=args.years,
        run_id=args.run_id or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"pass", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
