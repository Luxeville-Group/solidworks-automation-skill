#!/usr/bin/env python
'Generate SolidWorks parametric plans from natural-language requirements. This minimal VibeCAD workflow creates reviewable JSON for API wrappers; it does not directly control SolidWorks.'
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


THREAD_RULES = {
    "M3": {"pitch": 0.5, "tap_drill": 2.5, "mouth_chamfer": 0.3},
    "M4": {"pitch": 0.7, "tap_drill": 3.3, "mouth_chamfer": 0.4},
    "M5": {"pitch": 0.8, "tap_drill": 4.2, "mouth_chamfer": 0.5},
    "M6": {"pitch": 1.0, "tap_drill": 5.0, "mouth_chamfer": 0.6},
    "M8": {"pitch": 1.25, "tap_drill": 6.8, "mouth_chamfer": 0.8},
    "M10": {"pitch": 1.5, "tap_drill": 8.5, "mouth_chamfer": 1.0},
    "M12": {"pitch": 1.75, "tap_drill": 10.2, "mouth_chamfer": 1.2},
}


def parse_triplet_mm(text: str) -> tuple[float, float, float] | None:
    'Parse dimensions such as 90x60x8mm.'
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*mm",
        text,
    )
    if not match:
        return None
    return tuple(float(match.group(index)) for index in range(1, 4))


def parse_first_number_before(text: str, keywords: tuple[str, ...]) -> float | None:
    'Parse the first mm value near a keyword.'
    aliases = "(?:" + "|".join(map(re.escape, keywords)) + ")"
    number = r"(\d+(?:\.\d+)?)\s*mm"
    # Both word orders occur naturally in Turkish and English requirements.
    for pattern in (number + r"\s*" + aliases, aliases + r"\s*[:=]?\s*" + number):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def parse_radius_or_chamfer(text: str, prefix: str, default: float) -> float:
    'Parse shorthand such as R6 and C1.'
    match = re.search(rf"{re.escape(prefix)}\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    return float(match.group(1)) if match else default


def detect_thread(text: str) -> str | None:
    'Identify thread sizes such as M3/M4/M5.'
    match = re.search(r"\b(M(?:3|4|5|6|8|10|12))\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def build_plan(brief: str) -> dict:
    'Build a design plan.'
    dims = parse_triplet_mm(brief) or (90.0, 60.0, 8.0)
    length, width, thickness = dims
    thread = detect_thread(brief) or "M5"
    thread_rule = THREAD_RULES[thread]
    center_hole_diameter = parse_first_number_before(
        brief, ('center hole', 'centre hole', 'shaft hole', 'merkez deliği', 'merkez delik',
                'mil deliği', 'through hole', 'geçiş deliği')
    ) or 22.0
    corner_fillet = parse_radius_or_chamfer(brief, "R", 6.0)
    edge_chamfer = parse_radius_or_chamfer(brief, "C", 1.0)

    assumptions = []
    if parse_triplet_mm(brief) is None:
        assumptions.append('Taban boyutları algılanamadı; varsayılan 90x60x8 mm kullanıldı / Base dimensions missing; default 90x60x8 mm used.')
    if detect_thread(brief) is None:
        assumptions.append('Montaj deliği ölçüsü algılanamadı; M5 kullanıldı / Mounting-hole size missing; M5 used.')
    assumptions.extend(
        [
            'Dört köşe deliği varsayılan 10 mm kenar paylı dikdörtgen düzende / Four corner holes use a rectangular layout with 10 mm edge margin.',
            'Montaj delikleri geçiş deliğidir; kılavuz deliği için threaded_hole kullanın / Mounting holes are clearance holes; use threaded_hole for tapped holes.',
            'Hafifletme cepleri en az 3 mm duvar ve 2 mm taban bırakır / Pockets preserve at least 3 mm walls and 2 mm bottoms.',
        ]
    )

    hole_edge_margin = 10.0
    hole_positions = [
        [-length / 2 + hole_edge_margin, -width / 2 + hole_edge_margin],
        [length / 2 - hole_edge_margin, -width / 2 + hole_edge_margin],
        [-length / 2 + hole_edge_margin, width / 2 - hole_edge_margin],
        [length / 2 - hole_edge_margin, width / 2 - hole_edge_margin],
    ]

    features = [
        {
            "name": "BasePlate",
            "type": "base_plate",
            "params": {"length": length, "width": width, "thickness": thickness},
            "required": True,
        },
        {
            "name": "OuterCornerFillet",
            "type": "fillet",
            "params": {"radius": corner_fillet, "target": "outer_vertical_edges"},
            "required": True,
            "fallback": 'Radyüs çözümü başarısızsa R4 veya tek tek kenarlar denenir / If fillet solving fails, reduce to R4 or add edges individually.',
        },
        {
            "name": "TopEdgeChamfer",
            "type": "chamfer",
            "params": {"distance": edge_chamfer, "target": "top_outer_edges"},
            "required": True,
            "fallback": 'Tam çevre pahı başarısızsa kenar gruplarıyla yeniden denenir / If a full-loop chamfer fails, retry with grouped edge objects.',
        },
        {
            "name": "CornerMountingHoles",
            "type": "through_hole_pattern",
            "params": {
                "fastener": thread,
                "clearance_diameter": clearance_diameter(thread),
                "positions_xy": hole_positions,
            },
            "required": True,
        },
        {
            "name": "CenterShaftClearance",
            "type": "through_hole",
            "params": {"diameter": center_hole_diameter, "position_xy": [0.0, 0.0]},
            "required": True,
        },
        {
            "name": "SideLighteningPockets",
            "type": "pocket_pair",
            "params": {
                "count": 2,
                "min_wall": 3.0,
                "min_floor": 2.0,
                "placement": "left_and_right_of_center_hole",
            },
            "required": False,
            "fallback": 'Cep deliklerle çakışırsa küçültün veya atlayıp kaydedin / If a pocket collides with holes, shrink or skip it and record the change.',
        },
        {
            "name": "HoleMouthChamfers",
            "type": "chamfer",
            "params": {
                "distance": max(0.4, thread_rule["mouth_chamfer"]),
                "target": "all_hole_mouth_edges",
            },
            "required": True,
        },
    ]

    return {
        "plan_version": 1,
        "source_brief": brief.strip(),
        "part_family": "cnc_mount",
        "parameters": {
            "unit": "mm",
            "material": "6061 aluminum",
            "base_plate": {"length": length, "width": width, "thickness": thickness},
            "fixed_hole_fastener": thread,
            "tap_drill_reference": {
                "thread": thread,
                "tap_drill": thread_rule["tap_drill"],
                "pitch": thread_rule["pitch"],
                "note": 'Mevcut montaj delikleri geçiş deliğidir; kılavuz deliği için bu ön delik referansını kullanın / Current holes are clearance through holes; this tap-drill reference applies to tapped holes.',
            },
            "center_hole_diameter": center_hole_diameter,
            "corner_fillet": corner_fillet,
            "edge_chamfer": edge_chamfer,
        },
        "features": features,
        "operation_sequence": [
            "close_same_name_documents",
            "new_part",
            "base_plate",
            "outer_fillet_and_chamfer",
            "pockets",
            "through_holes",
            "mouth_chamfers",
            "custom_properties",
            "save_export_review",
        ],
        "assumptions": assumptions,
        "risk_register": [
            {
                "risk": 'Karmaşık delik/kanal işlemlerinden sonra radyüs/pah çözümü başarısız veya yavaş olabilir / Fillet/chamfer solving may fail or slow after complex cuts.',
                "mitigation": 'Önce dış radyüs/pah, ardından delik/kanal; başarısızsa radyüsü azaltıp kenarları ayrı deneyin / Follow CNC ordering and bounded edge-by-edge fallback.',
            },
            {
                "risk": 'Delik ağzı kenar seçimi kararsız / Hole-mouth edge selection is unstable.',
                "mitigation": 'body.GetEdges() ile kenarları merkez, yarıçap ve üst yüz yüksekliğine göre eşleyip edge.Select2() kullanın / Match edges geometrically and select objects.',
            },
            {
                "risk": "SolidWorks'te açık çıktı dosyası SaveAs hatasına neden olabilir / An open output document can cause SaveAs failure.",
                "mitigation": 'Önce aynı adlı eski belgeyi kapatın; kayıttan sonra dosya varlığı ve boyutunu kontrol edin / Close the old same-name document and check saved file existence/size.',
            },
        ],
        "review_plan": {
            "expected_outputs": ["SLDPRT", "STEP", "parameters_json", "review_report_json", "isometric_preview"],
            "views": ["isometric", "front", "top", "right"],
            "checks": [
                "expected_outputs_exist",
                "previews_created",
                "previews_not_blank",
                "feature_summary_available",
                "features_include_fillet_chamfer_cut",
            ],
        },
        "solidworks_mapping": [
            {
                "operation": "new_part",
                "preferred_api": "sw_session.SolidWorksSession.new_part",
                "notes": 'Belge yaşam döngüsünü session ile yönetin / Manage document lifecycle through session.',
            },
            {
                "operation": "base_plate",
                "preferred_api": "sw_part.sketch_rectangle + sw_part.extrude_boss",
                "notes": 'Taban eskizini basit tutun; başlangıçta karmaşık radyüslü kontur çizmeyin / Keep the base sketch simple.',
            },
            {
                "operation": "outer_fillet_and_chamfer",
                "preferred_api": "FeatureFillet + InsertFeatureChamfer with edge.Select2",
                "notes": 'Kenar nesnelerini seçin; Edge1 veya ekran koordinatlarına güvenmeyin / Select edge objects, not temporary names or clicks.',
            },
            {
                "operation": "save_export_review",
                "preferred_api": "session.save + session.export + sw_review.run_review",
                "notes": 'Çoklu görünüş önizlemesi ve review report zorunludur / Multiview previews and review report are required.',
            },
        ],
    }


def clearance_diameter(thread: str) -> float:
    'Return common screw-clearance diameters.'
    table = {"M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0}
    return table.get(thread, THREAD_RULES[thread]["tap_drill"] + 0.5)


def main() -> int:
    'Command-line entry point.'
    parser = argparse.ArgumentParser(description='SolidWorks parametrik tasarım planı oluştur / Generate a SolidWorks parametric design plan')
    parser.add_argument("--brief", help='Doğal dilde gereksinim / Natural-language requirement')
    parser.add_argument("--brief-file", type=Path, help='Gereksinim metin dosyası / Requirement text file')
    parser.add_argument("--out", type=Path, required=True, help='Çıktı JSON yolu / Output JSON path')
    args = parser.parse_args()

    if not args.brief and not args.brief_file:
        parser.error('--brief veya --brief-file gereklidir / --brief or --brief-file is required')

    brief = args.brief if args.brief else args.brief_file.read_text(encoding="utf-8")
    plan = build_plan(brief)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
