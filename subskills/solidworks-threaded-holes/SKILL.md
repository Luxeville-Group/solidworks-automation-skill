---
name: solidworks-threaded-holes
description: SolidWorks ISO metric internal-thread automation subskill. Use to create and review M3-M12 coarse or custom metric internal threads with explicit tap-drill diameter, including blind/through holes, mouth chamfers, right/left hand, ThreadFeatureData/CosmeticThread fallback and delivery evidence. Also consult for Hole Wizard, existing-part modification, external/imperial/pipe threads or explicit profiles, but mark those capabilities pilot or manual-review according to the roadmap rather than claiming stable support.
---

# SolidWorks Threaded Holes

## Determine capability level first

The current stable script is `scripts/create_threaded_hole_template.py`, which generates ISO metric internal-thread holes in a new rectangular sample.

- `verified`: M3/M4/M5/M6/M8/M10/M12 coarse internal threads, blind or true `Through All` tap-drill cuts, mouth chamfers, right/left hand, tolerance properties, real `Metric Tap` Thread, STEP and review evidence. Blind and through cases were tested upstream on SolidWorks 2026.
- `reviewed`: out-of-table ISO metric sizes; the user must explicitly provide `--tap-drill`; do not guess.
- `pilot`: locating/modifying holes in existing parts, Hole Wizard/Advanced Hole, external/imperial/UN/UNF/NPT/BSP threads, multistart threads, explicit profiles and drill-point/relief geometry. Read the [roadmap](references/threaded-hole-roadmap.md) before execution.

## Stable workflow

1. Run `python scripts/sw_preflight.py` from the repository root.
2. Confirm thread size, internal/external, tolerance class, hand, blind/through, thread depth, tap-drill depth, position and whether a real thread profile is required.
3. Before COM calls, validate finite values, tap-drill diameter below nominal diameter, thread depth within tap-drill depth/part thickness, and boundary allowance for thread major diameter and chamfer.
4. Create real tap-drill geometry first: `swEndCondBlind=0` for blind and `swEndCondThroughAll=1` for through holes; do not substitute a blind cut of plate thickness + 1 mm.
5. Enumerate circular edges by center, radius and entry face; do not rely on `Edge1` or screen coordinates.
6. Attempt real Thread with `Type="Metric Tap"` and mark `1` on the planar circular edge. Do not also assign that edge to `StartEntity`, call nonexistent `LoadReferences`, or override the tap-drill cylinder with nominal diameter.
7. If Thread fails, try `InsertCosmeticThread3`; through cosmetic threads use `swEndConditionThrough=2`. A non-null COM result does not establish persistence; traverse the feature tree after rebuild.
8. With `--visible-thread fallback`, create a 3D sketch helix only if neither real nor cosmetic thread remains in the feature tree. Allow fractional turns to preserve pitch, export `*_thread_evidence.bmp` separately, then hide the sketch for clean standard previews.
9. Create the mouth chamfer and record thread size, tap-drill diameter, depths, tolerance, hand, end condition and final representation status.
10. Hide reference planes, save SLDPRT, export STEP, run `sw_review.run_review()`, and visually inspect isometric/three-view previews.

## Template usage

Default M6×1 right-hand 6H blind hole:

```powershell
python subskills/solidworks-threaded-holes/scripts/create_threaded_hole_template.py `
  --thread M6 `
  --output-dir C:\CADAutomationWorkbench\solidworks_threaded_hole_output
```

Out-of-table M8×1 fine thread, left-hand, through hole:

```powershell
python subskills/solidworks-threaded-holes/scripts/create_threaded_hole_template.py `
  --thread M8x1 `
  --tap-drill 7.0 `
  --through `
  --handedness left `
  --thread-class 6H `
  --output-dir C:\CADAutomationWorkbench\m8x1_lh_output
```

`--visible-thread` accepts `fallback` (default), `always` and `never`. Keep `fallback` for normal delivery; use `always` only for helix debugging.

## Delivery and verification

Required outputs:

- `*.SLDPRT`
- `*.step`
- `*_parameters.json`
- `*_review_report.json`
- `*_isometric.bmp` and three-view previews.
- `*_thread_evidence.bmp` only when a visible helix is created.

Check `thread_attempts`, `thread_evidence` and `thread_status` together in `*_parameters.json`. Delivery requires all of:

- `has_tap_drill_cut=true` and `has_mouth_chamfer=true`.
- `representation` is `real-thread`, `cosmetic-thread` or an explained `visible-helix`; `metadata-only` must block template delivery.
- Review fields `expected_outputs_exist` and `previews_not_blank` are `true`.
- Standard previews hide reference planes and 3D sketch lines through solids, with correct hole positions and chamfers.

See [threaded-hole lessons](references/threaded-hole-lessons.md) for tested APIs, failure causes and official documentation; see the [roadmap](references/threaded-hole-roadmap.md) for unimplemented capabilities and acceptance gates.
