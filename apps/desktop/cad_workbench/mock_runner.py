"""@brief Mock executor for the desktop prototype."""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any, Callable

from .core import now_iso, read_json, write_json


LogCallback = Callable[[str], None]

STAGES = [
    ("preflight", "Ortam öz denetimi"),
    ("build_model", "Model oluştur"),
    ("export_model", "Modeli dışa aktar"),
    ("build_drawing", "Çizim oluştur"),
    ("export_drawing", "Çizimi dışa aktar"),
    ("review", "Standart incelemesi"),
    ("package", "Teslim paketini düzenle"),
]

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _assert_inside(parent: Path, child: Path) -> None:
    """@brief Ensure recursive operation targets remain within the project directory."""
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    if parent_resolved not in [child_resolved, *child_resolved.parents]:
        raise RuntimeError(f"Operation outside project directory rejected: {child_resolved}")


def _log(callback: LogCallback | None, message: str) -> None:
    if callback:
        callback(message)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_parameters(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    """@brief Run MVP P0 parameter-completeness checks."""
    checks: list[dict[str, Any]] = []

    def add(check_id: str, status: str, target: str, message: str, suggestion: str = "") -> None:
        checks.append(
            {
                "id": check_id,
                "severity": "P0",
                "status": status,
                "target": target,
                "message": message,
                "suggestion": suggestion,
            }
        )

    shell = parameters.get("shell", {})
    for key, label in [
        ("outer_length", "Dış uzunluk"),
        ("outer_width", "Dış genişlik"),
        ("outer_height", "Dış yükseklik"),
        ("wall_thickness", "Duvar kalınlığı"),
        ("bottom_thickness", "Taban kalınlığı"),
    ]:
        value = shell.get(key)
        if not _is_number(value) or value <= 0:
            add("model-main-dimensions", "fail", "model", f"{label} Eksik veya pozitif sayı değil", "Muhafazanın temel ölçülerini tamamlayın")
    if _is_number(shell.get("wall_thickness")) and shell["wall_thickness"] < 0.8:
        add("print-min-wall", "fail", "printing", "Duvar kalınlığı şu değerin altında:  0.8 mm Kesin alt sınır", "Duvar kalınlığını artırın veya özel baskı yöntemini doğrulayın")

    features = parameters.get("features", {})
    for group, label in [("holes", "Delik"), ("cutouts", "Arayüz açıklığı"), ("bosses", "Vida yuvası (boss)")]:
        for item in features.get(group, []):
            item_id = item.get("id") or "Numarasız"
            for required in ["id", "face", "quantity", "center_x", "center_y"]:
                if item.get(required) in ("", None):
                    add(
                        f"{group}-position-complete",
                        "fail",
                        "drawing",
                        f"{label} {item_id} Eksik {required}",
                        "Özellik, adet ve  X/Y  konumlandırma; yalnızca kılavuz çizgisi yeterli değildir",
                    )
            if group == "holes" and item.get("diameter") in ("", None, 0):
                add("hole-spec-complete", "fail", "drawing", f"Delik {item_id} Çap eksik", "Delik çapını tamamlayın")
            if group == "cutouts":
                has_rect = item.get("cutout_width") not in ("", None, 0) and item.get("cutout_height") not in ("", None, 0)
                has_round = item.get("cutout_diameter") not in ("", None, 0)
                if not has_rect and not has_round:
                    add("cutout-spec-complete", "fail", "drawing", f"Arayüz açıklığı {item_id} Ölçüler eksik", "Genişlik/yükseklik veya çapı tamamlayın")
            if group == "bosses":
                for required in ["screw_size", "boss_outer_diameter", "hole_diameter", "boss_height"]:
                    if item.get(required) in ("", None, 0):
                        add("boss-spec-complete", "fail", "drawing", f"Vida yuvası (boss) {item_id} Eksik {required}", "Vida yuvası özelliklerini tamamlayın")

    if not any(check["status"] == "fail" for check in checks):
        checks.extend(
            [
                {
                    "id": "model-cut-through",
                    "severity": "P0",
                    "status": "pass",
                    "target": "model",
                    "message": "Parametre tablosu gerçek delik/kanal kesimi için özellikleri ve konumları içeriyor",
                    "suggestion": "",
                },
                {
                    "id": "drawing-hole-position",
                    "severity": "P0",
                    "status": "pass",
                    "target": "drawing",
                    "message": "Delikler, arayüz açıklıkları ve vida yuvaları için özellik, adet ve konum alanları var",
                    "suggestion": "",
                },
                {
                    "id": "drawing-frame-title",
                    "severity": "P0",
                    "status": "pass",
                    "target": "drawing",
                    "message": "Seçildi GB/T  çizim çerçevesi, antet, birimler ve ölçek",
                    "suggestion": "",
                },
            ]
        )
    return checks


def run_mock(project_dir: Path, callback: LogCallback | None = None) -> dict[str, Any]:
    """@brief Generate a mock delivery package and final review report."""
    project_dir = Path(project_dir)
    project = read_json(project_dir / "project.json")
    parameters = read_json(project_dir / "parameters.json")
    checks = validate_parameters(parameters)
    failed = any(item["status"] == "fail" for item in checks)

    for _, label in STAGES:
        _log(callback, f"{label} ...")

    name = project.get("project_name", "project")
    stem = Path(name).stem or "project"
    model_dir = project_dir / "outputs" / "model"
    drawing_dir = project_dir / "outputs" / "drawing"
    package_dir = project_dir / "outputs" / "package"
    reviews_dir = project_dir / "reviews"
    previews_dir = project_dir / "previews"

    outputs = {
        "sldprt": model_dir / f"{stem}.sldprt",
        "step": model_dir / f"{stem}.step",
        "stl": model_dir / f"{stem}.stl",
        "dwg": drawing_dir / f"{stem}.dwg",
        "dxf": drawing_dir / f"{stem}.dxf",
        "pdf": drawing_dir / f"{stem}.pdf",
        "preview": previews_dir / "drawing_preview.png",
    }

    if not failed:
        outputs["sldprt"].write_text("MOCK SLDPRT PLACEHOLDER - Later versions use  SolidWorks COM  generation.\n", encoding="utf-8")
        outputs["step"].write_text("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('MOCK STEP'),'1');\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        outputs["stl"].write_text("solid mock_shell\nendsolid mock_shell\n", encoding="utf-8")
        outputs["dwg"].write_text("MOCK DWG PLACEHOLDER - Later versions use  AutoCAD COM  generation.\n", encoding="utf-8")
        outputs["dxf"].write_text("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")
        outputs["pdf"].write_text("MOCK PDF PLACEHOLDER - Later versions export actual  PDF.\n", encoding="utf-8")
        outputs["preview"].write_bytes(PNG_1X1)
        (previews_dir / "model_iso.png").write_bytes(PNG_1X1)
        (previews_dir / "package_cover.png").write_bytes(PNG_1X1)

    model_review = {
        "schema_version": "0.1",
        "status": "warning" if not failed else "fail",
        "checked_at": now_iso(),
        "message": "Mevcut durum:  mock  model incelemesi; gerçek geometri kontrolü  SolidWorks  bağlantıdan sonra etkinleştirilir.",
    }
    drawing_review = {
        "schema_version": "0.1",
        "status": "warning" if not failed else "fail",
        "checked_at": now_iso(),
        "message": "Mevcut durum:  mock  çizim incelemesi; gerçek  DWG Ölçü nesneleri ve görsel kontrol şu aşamada:  AutoCAD  bağlantıdan sonra etkinleştirilir.",
    }
    print_review = {
        "schema_version": "0.1",
        "status": "warning" if not failed else "fail",
        "checked_at": now_iso(),
        "message": "Parametre düzeyinde kontrol uygulandı:  3D  baskı kurallarının kontrolü.",
    }
    write_json(reviews_dir / "model_review.json", model_review)
    write_json(reviews_dir / "drawing_review.json", drawing_review)
    write_json(reviews_dir / "printability_review.json", print_review)

    final_review = {
        "schema_version": "0.1",
        "overall_status": "fail" if failed else "warning",
        "project_id": project.get("project_id"),
        "checked_at": now_iso(),
        "checks": checks
        + [
            {
                "id": "mock-runner-not-real-cad",
                "severity": "P1",
                "status": "warning",
                "target": "package",
                "message": "Bu masaüstü prototipidir mock  execution, CAD Dosya bir yer tutucu; üretimde kullanılamaz.",
                "suggestion": "Later integration SolidWorks/AutoCAD  ardından teslim edilebilir duruma geçer",
            }
        ],
        "outputs": {key: str(path.relative_to(project_dir)) for key, path in outputs.items()},
    }
    write_json(reviews_dir / "final_review.json", final_review)

    manifest = {
        "schema_version": "0.1",
        "generated_at": now_iso(),
        "project_name": project.get("project_name", "CAD Proje"),
        "status": final_review["overall_status"],
        "files": [
            {"kind": key, "path": str(path.relative_to(project_dir)), "exists": path.exists()}
            for key, path in outputs.items()
        ]
        + [
            {"kind": "review", "path": "reviews/final_review.json", "exists": True},
            {"kind": "source", "path": "parameters.json", "exists": True},
            {"kind": "source", "path": "project.json", "exists": True},
        ],
    }
    write_json(project_dir / "outputs" / "manifest.json", manifest)

    readme = project_dir / "README_Teslim açıklaması.md"
    readme.write_text(
        "\n".join(
            [
                f"# {project.get('project_name', 'CAD Proje')} Teslim açıklaması",
                "",
                "- Birim: mm",
                "- Çizim standardı: GB/T Stil",
                "- Mevcut durum: mock Prototip çıktısı; doğrudan üretime uygun değildir",
                "- İnceleme raporu: reviews/final_review.json",
                "- Sonraki: Bağlantı SolidWorks/AutoCAD  then output actual  SLDPRT/STEP/STL/DWG/DXF/PDF",
                "",
            ]
        ),
        encoding="utf-8",
    )

    delivery = package_dir / f"{stem}_delivery"
    if delivery.exists():
        _assert_inside(project_dir, delivery)
        shutil.rmtree(delivery)
    delivery.mkdir(parents=True)
    for rel in ["project.json", "parameters.json", "README_Teslim açıklaması.md", "outputs/manifest.json"]:
        shutil.copy2(project_dir / rel, delivery / Path(rel).name)
    shutil.copytree(reviews_dir, delivery / "reviews")

    project["updated_at"] = now_iso()
    project["status"] = final_review["overall_status"]
    write_json(project_dir / "project.json", project)
    _log(callback, f"Üretildi mock Teslim klasörü: {delivery}")
    return final_review
