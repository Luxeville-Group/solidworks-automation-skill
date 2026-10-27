"""@brief Desktop project data and filesystem utilities."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
CN_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    """@brief Return an ISO timestamp using the legacy China time zone."""
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


def default_output_root() -> Path:
    """@brief Return the default project output root."""
    return Path.home() / "Documents" / "CADAutomationWorkbench"


def repo_root() -> Path:
    """@brief Return skill  repository root."""
    return Path(__file__).resolve().parents[3]


def slugify_project_name(name: str) -> str:
    """@brief Convert a project name to a short folder-safe name."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if slug:
        return slug[:60]
    return "project_" + datetime.now(CN_TZ).strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """@brief Write UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """@brief Read UTF-8 JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_project_tree(project_dir: Path) -> None:
    """@brief Create the expected MVP project directory layout."""
    for rel in [
        "inputs",
        "generated",
        "outputs/model",
        "outputs/drawing",
        "outputs/package",
        "previews",
        "reviews",
        "logs",
    ]:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)


def build_project_payload(project_name: str, output_root: Path) -> dict[str, Any]:
    """@brief Create project.json data."""
    project_id = datetime.now(CN_TZ).strftime("%Y%m%d_%H%M%S")
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "project_type": "3d_print_shell",
        "unit": "mm",
        "drawing_standard": "GB_T_style",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "output_root": str(output_root),
        "status": "draft",
    }


def default_parameters() -> dict[str, Any]:
    """@brief Return default shell MVP parameters."""
    return {
        "schema_version": SCHEMA_VERSION,
        "units": "mm",
        "shell": {
            "outer_length": 120.0,
            "outer_width": 80.0,
            "outer_height": 35.0,
            "wall_thickness": 1.6,
            "bottom_thickness": 2.0,
            "corner_radius": 4.0,
            "edge_chamfer": 0.5,
            "open_direction": "top",
        },
        "printing": {
            "process": "FDM",
            "nozzle_diameter": 0.4,
            "hole_compensation": 0.2,
            "fit_clearance": 0.3,
            "min_wall_warning": 1.2,
        },
        "features": {
            "holes": [
                {
                    "id": "H1",
                    "name": "Montaj deliği",
                    "hole_type": "round",
                    "face": "bottom",
                    "diameter": 3.4,
                    "quantity": 4,
                    "datum_x": "left",
                    "datum_y": "bottom",
                    "center_x": 10.0,
                    "center_y": 10.0,
                    "pitch_x": 100.0,
                    "pitch_y": 60.0,
                    "through": True,
                    "note": "M3  vida geçiş deliği, FDM Önerilen pay",
                }
            ],
            "cutouts": [
                {
                    "id": "I1",
                    "interface_type": "USB-C",
                    "face": "front",
                    "cutout_width": 10.0,
                    "cutout_height": 4.0,
                    "cutout_diameter": 0.0,
                    "corner_radius": 1.0,
                    "center_x": 60.0,
                    "center_y": 15.0,
                    "quantity": 1,
                    "clearance": 0.3,
                }
            ],
            "bosses": [
                {
                    "id": "B1",
                    "screw_size": "M3",
                    "boss_outer_diameter": 7.0,
                    "hole_diameter": 2.8,
                    "boss_height": 8.0,
                    "face": "bottom",
                    "center_x": 10.0,
                    "center_y": 10.0,
                    "quantity": 4,
                    "rib_enabled": True,
                }
            ],
            "vents": [],
        },
        "drawing": {
            "paper_size": "A3",
            "scale": "1:1",
            "title": "3DBaskı muhafazası",
            "material": "PLA/PETG",
            "projection": "first_angle",
            "required_exports": ["dwg", "dxf", "pdf", "png"],
        },
    }


def create_project(project_name: str, output_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """@brief Create the project directory and write default project data."""
    root = Path(output_root).expanduser().resolve()
    project_dir = root / slugify_project_name(project_name)
    ensure_project_tree(project_dir)
    project = build_project_payload(project_name, root)
    params = default_parameters()
    write_json(project_dir / "project.json", project)
    write_json(project_dir / "parameters.json", params)
    (project_dir / "inputs" / "brief.md").write_text(
        "# Proje açıklaması\n\nYapısal ölçüleri, delik konumlarını, arayüzleri ve üretim gereksinimlerini uygulamada tamamlayın.\n",
        encoding="utf-8",
    )
    return project_dir, project, params
