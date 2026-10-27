# SolidWorks Fillet Chamfer CNC

`solidworks-fillet-chamfer-cnc` is the CNC fillet/chamfer subskill in solidworks-automation. It creates machined parts with parameter preflight, semantic edge selection, dimensional fallback evidence, feature-tree read-back and STEP review.

## When to use

- CNC aluminum mounts, connector blocks, brackets, baseplates and counterbored mounting plates.
- Large outer fillets, top/bottom chamfers and hole-mouth chamfers.
- Environment probes/native regressions for three/four-intermediate-point variable radius, face fillet, full-round, three-edge setback, plane–cylinder G2 combinations and asymmetric width-width chamfers.
- Safe capability probes and versioned blocked evidence for Python, C# PIA, SWBasic and in-process unmanaged C++ hold-line backends.
- Round-trip regression of a complex FreeCAD-library corner bracket pinned by commit/SHA-256 with CC BY 3.0 attribution, applying C0.2/C0.4 width-width chamfers to a uniquely signed edge.
- CNC-friendly obround pockets, center slots, counterbores, locating holes and inter-feature clearance checks.
- Stable edge selection, STEP export and multi-view preview review.

## Core principles

The main challenges are topology, edge selection and feature order:

1. Start with a simple base body.
2. Before COM, check hole/slot collisions, minimum walls, clearances and remaining floor thickness.
3. Prefer large fillets and outer chamfers before hole/slot cuts.
4. Add holes, slots and pockets after main-body edge treatment; small hole-mouth chamfers come last.
5. Select by geometry signatures, edge.Select2() and exact count assertions, not Edge1 or screen coordinates.
6. Read features back after rebuild and run sw_review.run_review().

## Quick commands

Run offline preflight from the repository root:

```powershell
py subskills\solidworks-fillet-chamfer-cnc\scripts\create_cnc_mount_template.py `
  --dry-run `
  --set base_corner_radius=6 `
  --output-dir C:\CADAutomationWorkbench\solidworks_fillet_chamfer_output
```

Inspect CNC_Mount_Template_plan.json, then remove --dry-run to execute native modeling. A parameter file is also supported:

```powershell
py subskills\solidworks-fillet-chamfer-cnc\scripts\create_cnc_mount_template.py `
  --params-json subskills\solidworks-fillet-chamfer-cnc\examples\cnc_mount_precision_params.json `
  --failure-policy strict `
  --output-dir C:\CADAutomationWorkbench\solidworks_fillet_chamfer_output
```

strict never changes requested dimensions; progressive tries 100%/75%/50%, and any degraded result must report its actual dimensions.

Probe advanced interfaces before selectively running native validation:

```powershell
py subskills\solidworks-fillet-chamfer-cnc\scripts\verify_advanced_fillets.py `
  --verify-solidworks `
  --modes variable face surface_combo full_round setback width_width_chamfer `
  --output-dir C:\CADAutomationWorkbench\advanced_fillet_verified
```

interface_ready means the interface exists; verified means modeling, rebuild, save, STEP, reopen and preview review all passed. The six examples above completed native validation on SW2026 SP1.1. Hold lines are not a Python-only limitation: C# PIA, SWBasic and official in-process unmanaged C++ paths were retested and still fail at ISetHoldLines, so blocked is the safe default. Other service packs require isolated revalidation.

Complex open-source example:

```powershell
py subskills\solidworks-fillet-chamfer-cnc\scripts\verify_open_source_bracket.py `
  --source C:\CADAutomationWorkbench\sources\l_gusset.step `
  --source-commit 5b285130bff480cda282499e83604b295dd0aa4d `
  --version 2026 `
  --output-dir C:\CADAutomationWorkbench\opensource_l_gusset

py subskills\solidworks-fillet-chamfer-cnc\scripts\verify_open_source_complex_case.py `
  --version 2026 `
  --output-dir C:\CADAutomationWorkbench\opensource_corner_bracket
```

## Directory

```text
solidworks-fillet-chamfer-cnc/
├── SKILL.md
├── README.md
├── manifest.yaml
├── agents/
├── references/
│   └── cnc-fillet-chamfer-lessons.md
├── examples/
│   ├── cnc_mount_precision_params.json
│   └── open_source_corner_bracket_case.json
└── scripts/
    ├── cnc_strategy.py
    ├── advanced_fillet_strategy.py
    ├── create_cnc_mount_template.py
    ├── verify_advanced_fillets.py
    ├── verify_open_source_bracket.py
    └── verify_open_source_complex_case.py
```

## Related capabilities

- Parent: solidworks-automation.
- Upstream planning: solidworks-vibecad.
- Use solidworks-threaded-holes when actual threaded holes are required.
