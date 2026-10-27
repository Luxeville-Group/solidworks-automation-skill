---
name: solidworks-vibecad
description: SolidWorks VibeCAD parametric-design planning subskill. Use to turn natural-language mechanical-design requirements into structured plans, manufacturing-rule checks, SolidWorks API execution outlines and review gates; applies to text-to-CAD, reusable automation, domain knowledge, prompt templates, parametric modeling plans and batch CNC mounting-base, connector-block or bracket generation.
---

# SolidWorks VibeCAD

## Purpose

This subskill converts natural-language ideas into executable, reviewable SolidWorks parametric design plans and reusable mechanical-design assets:

```text
Domain knowledge + parameter schemas + prompt templates + stable API wrappers + automated review.
```

The LLM interprets intent and fills parameters; SolidWorks API executes deterministically; the knowledge base supports engineering checks; the review chain detects visually plausible but geometrically incorrect results.

## Suitable tasks

- Turn a user's natural-language part description into a parametric modeling plan.
- Template frequent parts such as CNC mounting bases, connector blocks, L-brackets, base plates and hole patterns.
- Capture domain rules such as tap-drill sizes, clearance holes, counterbores, chamfers, fillets and minimum walls.
- Supply JSON plans and risk gates to the SolidWorks automation executor.
- Turn successful cases into reusable templates.

## Workflow

1. Read the user request and confirm part family, process, material, output formats and constraints.
2. Consult `knowledge/manufacturing_rules.yaml` for conservative defaults.
3. Use `prompts/solidworks_parametric_planner.md` to constrain LLM output to a structured plan.
4. Validate fields against `schemas/design_plan.schema.json`.
5. Run `scripts/plan_from_brief.py` for a local rule-based plan, or save LLM output as JSON with the same schema.
6. Run `scripts/sw_execution_outline.py` to generate the SolidWorks execution outline.
7. For subsequent execution, use parent-skill `scripts/sw_session.py`, `scripts/sw_part.py`, `scripts/sw_review.py` and relevant specialist subskills.

## Quick commands

```powershell
py subskills\solidworks-vibecad\scripts\plan_from_brief.py `
  --brief-file subskills\solidworks-vibecad\examples\motor_mount_brief.txt `
  --out subskills\solidworks-vibecad\examples\motor_mount_plan.json

py subskills\solidworks-vibecad\scripts\sw_execution_outline.py `
  --plan subskills\solidworks-vibecad\examples\motor_mount_plan.json `
  --out subskills\solidworks-vibecad\examples\motor_mount_execution.md
```

## Relationship to the parent skill

- `solidworks-automation`: core skill for connecting to SolidWorks, modeling, export and review.
- `solidworks-vibecad`: natural language → parametric design plan.
- `solidworks-fillet-chamfer-cnc`: execution lessons for complex CNC fillets/chamfers.
- `solidworks-threaded-holes`: execution lessons for threaded holes, tap-drill holes and thread representation.

For CNC plans with many fillets/chamfers, also read:

```text
subskills/solidworks-fillet-chamfer-cnc/SKILL.md
```

For plans with M3/M4/M5/M6/M8 threaded holes, also read:

```text
subskills/solidworks-threaded-holes/SKILL.md
```

## Avoid common mistakes

- Do not have the LLM directly produce SolidWorks COM calls with long parameter lists.
- Plan JSON is not proof of geometry success; native SolidWorks execution and `sw_review` are required.
- Conservative defaults may fill uncertain parameters, but record them in `assumptions`.
- Distinguish clearance, counterbored and tapped mounting holes; do not silently interpret an `M5 screw mounting hole` as an M5 tapped hole.
- Plans must include `review_plan` before automated modeling can begin.

## Current status

The minimal workflow from requirement text to design plan and execution outline is implemented. Integrating a native SolidWorks executor with the parent skill's stable APIs is the next phase.
