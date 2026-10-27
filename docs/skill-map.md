# Skill Map

This repository is managed as one SolidWorks automation skill family. The root skill owns the shared SolidWorks COM layer, while subskills own domain workflows and references.

## Root Skill

| Name | Role |
|---|---|
| `solidworks-automation` | SolidWorks session management, document IO, modeling helpers, export, review, MCP server, API lookup rules |

## Subskills

| Name | Status | Trigger Words | Main Output |
|---|---|---|---|
| `solidworks-vibecad` | experimental | text-to-CAD, VibeCAD, parametric design plans, industry knowledge bases, prompt templates | `design_plan.json`, execution outline |
| `solidworks-fillet-chamfer-cnc` | stable | CNC mounts, connecting blocks, brackets, constant/variable radius, face/full-round/setback, chamfers, weight-reduction pockets | `SLDPRT`, `STEP`, parameters/capabilities JSON, review report |
| `solidworks-threaded-holes` | stable | threaded holes, tapped holes, tap-drill holes, M6x1, CosmeticThread | `SLDPRT`, `STEP`, threaded-hole parameters, review report |

## Recommended Agent Routing

```text
1. Need SolidWorks connection/export/review only
   -> solidworks-automation

2. Natural language brief with missing parameters
   -> solidworks-vibecad
   -> then route to execution subskill

3. CNC part with many fillets/chamfers/pockets
   -> solidworks-fillet-chamfer-cnc

4. Threaded or tapped holes
   -> solidworks-threaded-holes
```

## Shared Review Contract

Every CAD-generating subskill should produce or require:

- Native SolidWorks file when applicable.
- STEP/STL/PDF/DXF export according to the user request.
- Parameter JSON for reproducibility.
- `sw_review.run_review()` report.
- At least isometric preview; front/top/right when geometry needs inspection.

## Productization Docs

| File | Purpose |
|---|---|
| `docs/market-research-2026.md` | Market research, user pain points, competitor signals, and product positioning |
| `docs/product-mvp-spec.md` | MVP specification for the local desktop CAD delivery workbench |

## Adding a New Subskill

Create:

```text
subskills/<name>/
├── SKILL.md
├── README.md
├── manifest.yaml
├── scripts/
├── references/
└── examples/
```

Then update:

- `SUBSKILLS.md`
- `README.md`
- `project.yaml`
- this file
