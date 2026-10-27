#!/usr/bin/env python
'Convert a VibeCAD plan into a SolidWorks execution outline. Does not call COM directly; applies engineering gates and identifies API wrappers and steps needing human confirmation or fallback before modeling.'
from __future__ import annotations

import argparse
import json
from pathlib import Path


API_MAP = {
    "close_same_name_documents": "sw_session.SolidWorksSession.close",
    "new_part": "sw_session.SolidWorksSession.new_part",
    "base_plate": "sw_part.sketch_rectangle + sw_part.extrude_boss",
    "outer_fillet_and_chamfer": "FeatureFillet / InsertFeatureChamfer with edge.Select2",
    "pockets": "sw_part.sketch_rectangle or sketch_slot + extrude_cut",
    "through_holes": "sw_part.sketch_circle + extrude_cut",
    "counterbores": "sw_part.sketch_circle + shallow extrude_cut",
    "threaded_holes": "solidworks-threaded-holes stable workflow",
    "slots": "sw_part.sketch_slot + extrude_cut",
    "mouth_chamfers": "InsertFeatureChamfer with circle edge selection",
    "custom_properties": "model.Extension.CustomPropertyManager",
    "save_export_review": "session.save + session.export + sw_review.run_review",
}


def load_plan(path: Path) -> dict:
    'Read design-plan JSON.'
    return json.loads(path.read_text(encoding="utf-8"))


def build_outline(plan: dict) -> dict:
    'Generate the execution outline.'
    steps = []
    for index, operation in enumerate(plan["operation_sequence"], start=1):
        steps.append(
            {
                "index": index,
                "operation": operation,
                "preferred_api": API_MAP.get(operation, "api_lookup_required"),
                "status": "ready" if operation in API_MAP else "needs_api_lookup",
            }
        )

    feature_gate = []
    for feature in plan["features"]:
        feature_gate.append(
            {
                "feature": feature["name"],
                "type": feature["type"],
                "required": feature["required"],
                "fallback": feature.get("fallback", ""),
            }
        )

    return {
        "source_part_family": plan["part_family"],
        "execution_mode": "solidworks_com_serial",
        "unit_policy": "plan uses mm; SolidWorks API receives meters via sw_connect.mm()",
        "steps": steps,
        "feature_gate": feature_gate,
        "review_gate": plan["review_plan"],
        "stop_conditions": [
            "SolidWorks preflight fails",
            "required base geometry feature returns None",
            "save/export output file missing or zero bytes",
            "review report marks previews blank",
        ],
    }


def write_markdown(outline: dict) -> str:
    'Generate a Markdown outline.'
    lines = [
        '# SolidWorks yürütme özeti / Execution outline',
        "",
        f"- Parça ailesi / Part family: `{outline['source_part_family']}`",
        f"- Yürütme modu / Execution mode: `{outline['execution_mode']}`",
        f"- Birim politikası / Unit policy: {outline['unit_policy']}",
        "",
        '## Adımlar / Steps',
        "",
    ]
    for step in outline["steps"]:
        lines.append(
            f"{step['index']}. `{step['operation']}` -> `{step['preferred_api']}` [{step['status']}]"
        )
    lines.extend(["", '## Unsur kontrolleri / Feature gates', ""])
    for item in outline["feature_gate"]:
        fallback = f"; geri dönüş / fallback: {item['fallback']}" if item["fallback"] else ""
        lines.append(f"- `{item['feature']}` ({item['type']}), required={item['required']}{fallback}")
    lines.extend(["", '## Durdurma koşulları / Stop conditions', ""])
    for condition in outline["stop_conditions"]:
        lines.append(f"- {condition}")
    return "\n".join(lines) + "\n"


def main() -> int:
    'Command-line entry point.'
    parser = argparse.ArgumentParser(description='SolidWorks yürütme özeti oluştur / Generate a SolidWorks execution outline')
    parser.add_argument("--plan", type=Path, required=True, help='Tasarım planı JSON / Design-plan JSON')
    parser.add_argument("--out", type=Path, required=True, help='Çıktı Markdown yolu / Output Markdown path')
    args = parser.parse_args()

    outline = build_outline(load_plan(args.plan))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(write_markdown(outline), encoding="utf-8")
    print(str(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
