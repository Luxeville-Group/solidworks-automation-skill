# Result Self-Review Reference

## Required checks

After generating, modifying or exporting SolidWorks files, check at least:

1. COM return values are not `None` and key feature objects were created.
2. `save_document()`, `session.save()` and `session.export()` report success.
3. Output `.sldprt`, `.sldasm`, `.slddrw`, `.step`, `.stl`, etc. files exist and have plausible sizes.
4. The model has rebuilt: `model.ForceRebuild3(False)`.
5. The view fits the model: `model.ViewZoomtofit2()`.
6. At least one isometric BMP was exported; include front, top and right views for complex models.

## Structured self-review report

```python
import sys
sys.path.insert(0, r"SKILL_DIR/scripts")

from sw_review import run_review

model.ForceRebuild3(False)
report, report_path = run_review(
    model,
    r"C:\temp\solidworks_review",
    basename="model",
    views=("isometric", "front", "top", "right"),
    expected_outputs=[r"C:\temp\model.sldprt", r"C:\temp\model.step"],
)
print(report_path)
print(report["checks"])
```

`run_review()` produces:

- Multiple BMP preview views.
- A structured `*_review_report.json`.
- A readable `*_review_summary.md` suitable for delivery notes, issues or PRs.
- `evaluation.status`: `pass` / `warn` / `fail`.
- `evaluation.score`: rule-based score out of 100.
- `evaluation.issues`: machine-readable issue list.
- `evaluation.recommendations`: repair suggestions.
- `checks.previews_created`: whether previews were created.
- `checks.previews_not_blank`: whether previews appear nonblank.
- `checks.expected_outputs_exist`: whether expected outputs exist and have nonzero size.
- `checks.feature_summary_available`: whether a feature-tree summary can be read.

The structured report catches obvious failures; it cannot replace human or visual-model judgment about geometric intent.

Manufacturing tasks must also produce separate machine-readable specification evidence, for example:

```json
{
  "cad_spec": {
    "envelope_mm": {"length": 60, "width": 40, "thickness": 12},
    "holes": [
      {"diameter_mm": 10, "count": 1, "positions_xy_mm": [[0, 0]]},
      {"diameter_mm": 4, "count": 4, "positions_xy_mm": [[-24, -14], [24, -14], [-24, 14], [24, 14]]}
    ]
  },
  "measurement_source": "SolidWorks API/B-Rep/parameter readback",
  "units": "mm"
}
```

If the task specifies an envelope or hole diameter but delivery lacks independent JSON evidence, the Reviewer Gate must fail. Codex's summary or an executor's success claim cannot replace evidence. Record hole counts/positions, edge distances, center distances, fillets, wall thickness and assembly DOFs as required by the task.

For complex holes/slots, `collect_geometry_measurements()` also returns:

- `hole_groups`: hole segments grouped by spatial axis.
- `compound_holes`: coaxial counterbore/compound-hole candidates with different diameters.
- `slot_arc_candidates`: internal cylindrical slot-end arcs with multiple boundary edges, excluded from round-hole counts.
- `validate_hole_positions()`: per-hole acceptance by axis distance and diameter tolerance.

```python
from sw_review import collect_geometry_measurements, validate_hole_positions

measurements = collect_geometry_measurements(model)
position_checks = validate_hole_positions(
    measurements,
    [{"id": "H1", "diameter_mm": 8, "position_mm": [20, 20, 0]}],
    position_tolerance_mm=0.1,
    diameter_tolerance_mm=0.05,
)
assert position_checks["status"] == "pass"
```

Cylindrical B-Rep can establish diameter, axis and cylindrical-segment length, but cannot reliably distinguish blind from through holes alone. Cross-check blind depth, countersink angle and hole type against creation evidence from `sw_hole_features.py` or feature-definition readback.

## One-command review

```bash
python scripts/sw_review.py ^
  --file C:\temp\model.sldprt ^
  --output-dir C:\temp\solidworks_review ^
  --basename model ^
  --expected C:\temp\model.sldprt ^
  --expected C:\temp\model.step
```

Exit codes:

- `0`: `pass` or `warn`; report generated.
- `1`: `warn` with `--fail-on-warn`.
- `2`: `fail`; issues requiring repair.

## Visual inspection checklist

- The main body is visible; the view is not blank or only a sketch.
- Key components are present: wheels, holes, shafts, enclosures, brackets, BOM tables, etc.
- Successful cut/hole/slot tree features are actually visible on the intended surfaces; `feature is not None` does not prove design intent.
- Scale is plausible; confusing millimeters and meters can create huge models.
- Orientation is correct, such as wheels on the sides rather than on top.
- Components do not obviously overlap, float, penetrate or lack constraints.
- Filenames, output directories and export formats match the request.

## When problems are found

1. Do not merely report that a file was saved.
2. Determine whether the cause is sketching, selection, extrusion direction, units, reference planes or export.
3. Correct the script, regenerate and export fresh previews.
4. State which previews were checked and which limitations remain in the final response.
