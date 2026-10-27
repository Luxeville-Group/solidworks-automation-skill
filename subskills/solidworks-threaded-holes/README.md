# SolidWorks Threaded Holes

`solidworks-threaded-holes` is the ISO metric internal-thread subskill of `solidworks-automation`. It validates tap-drill diameter, end conditions, thread depth and hole boundaries, then reads back the feature tree after rebuild; it does more than create geometry resembling a hole.

## Current capabilities

- M3/M4/M5/M6/M8/M10/M12 coarse ISO metric internal threads.
- ISO metric sizes outside the table require an explicit tap-drill diameter; do not guess it.
- Blind holes and true `Through All` holes.
- Three fallback levels: real `Metric Tap` Thread, CosmeticThread, and a 3D evidence helix with exact pitch.
- Right/left hand, thread-tolerance properties, hole-mouth chamfers, STEP, multiple views and structured review evidence.

Upstream tested M6×1 6H right-hand blind and through holes on SolidWorks 2026; both retained real Thread features after rebuild and passed delivery review.

## Quick start

```powershell
python scripts\sw_preflight.py

python subskills\solidworks-threaded-holes\scripts\create_threaded_hole_template.py `
  --thread M6 `
  --output-dir C:\CADAutomationWorkbench\solidworks_threaded_hole_output
```

Through-hole and left-hand examples:

```powershell
python subskills\solidworks-threaded-holes\scripts\create_threaded_hole_template.py `
  --thread M8x1 `
  --tap-drill 7.0 `
  --through `
  --handedness left `
  --thread-class 6H `
  --output-dir C:\CADAutomationWorkbench\m8x1_lh_output
```

## Delivery evidence

Default output is `SLDPRT + STEP + parameters.json + review_report.json + isometric/three-view previews`. If neither real Thread nor CosmeticThread remains in the feature tree, also generate a separate `*_thread_evidence.bmp`; hide the 3D helix afterward so it does not obscure standard previews.

## Capabilities not yet claimed stable

Hole Wizard/Advanced Hole, existing-part modification, external threads, UNC/UNF/NPT/BSP, multistart threads, drill points/tap reliefs and automatic acceptance of drawing hole callouts are future extensions; see [threaded-hole-roadmap.md](references/threaded-hole-roadmap.md).

## Directory

```text
solidworks-threaded-holes/
├── SKILL.md
├── README.md
├── manifest.yaml
├── agents/
├── references/
│   ├── threaded-hole-lessons.md
│   └── threaded-hole-roadmap.md
└── scripts/
    └── create_threaded_hole_template.py
```
