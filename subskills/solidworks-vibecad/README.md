# SolidWorks VibeCAD

`solidworks-vibecad` is the parametric-design planning subskill in `solidworks-automation`. It converts natural-language mechanical-design requirements into structured plans, manufacturing-rule checks, SolidWorks API execution outlines and review gates.

## Why this is a subskill

The value is in making repeated mechanical-design work reusable:

```text
Domain knowledge + parameter schemas + prompt templates + stable API wrappers + automated review.
```

It therefore belongs in the SolidWorks automation repository alongside CNC fillets/chamfers, threaded holes, assemblies and MCP capabilities.

## Current capabilities

- Generate parametric design-plan JSON from natural-language requirements.
- Include initial M3-M12 tap-drill, clearance-hole, CNC fillet/chamfer and minimum-wall rules.
- Provide a strict LLM planning prompt to avoid unstable directly generated macros.
- Generate a SolidWorks API execution outline mapping each step to a stable parent-skill wrapper.
- Generate review gates requiring save, export, multiview previews and a review report.

## Directory

```text
solidworks-vibecad/
├── SKILL.md
├── README.md
├── manifest.yaml
├── knowledge/
│   └── manufacturing_rules.yaml
├── prompts/
│   └── solidworks_parametric_planner.md
├── schemas/
│   └── design_plan.schema.json
├── scripts/
│   ├── plan_from_brief.py
│   └── sw_execution_outline.py
├── examples/
│   ├── motor_mount_brief.txt
│   ├── motor_mount_plan.json
│   └── motor_mount_execution.md
└── references/
    └── vibecad-roadmap.md
```

## Quick run

Run from the `solidworks-automation` repository root:

```powershell
py subskills\solidworks-vibecad\scripts\plan_from_brief.py `
  --brief-file subskills\solidworks-vibecad\examples\motor_mount_brief.txt `
  --out subskills\solidworks-vibecad\examples\motor_mount_plan.json

py subskills\solidworks-vibecad\scripts\sw_execution_outline.py `
  --plan subskills\solidworks-vibecad\examples\motor_mount_plan.json `
  --out subskills\solidworks-vibecad\examples\motor_mount_execution.md
```

## Example output

The example requirement identifies:

- Base plate: `90 x 60 x 8 mm`.
- Mounting holes: clearance for `M5` screws, diameter `5.5 mm`.
- Center hole: `22 mm`.
- Outline fillets: `R6`.
- Top-edge chamfer: `C1`.
- Review: `SLDPRT + STEP + parameters_json + review_report_json + isometric_preview`.

## Next step

Prioritize connecting the `cnc_mount` executor to the parent skill:

1. Read `design_plan.json`.
2. Call `sw_preflight.py`.
3. Create a part with `SolidWorksSession()`.
4. Create the planned base plate, holes, pockets, fillets and chamfers.
5. Save `SLDPRT` and export `STEP`.
6. Run `sw_review.run_review()`.
7. On failure, retry with the plan's bounded `risk_register` fallback.
