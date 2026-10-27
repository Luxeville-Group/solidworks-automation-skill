# Complex Hole and Slot Automation

## Supported scope

`scripts/sw_hole_features.py` creates these structures with sketches and cut features:

- Fixed-depth blind holes.
- Through-all holes.
- Two-stage compound holes: through hole + cylindrical counterbore.
- Through hole + conical countersink with a specified included angle.
- Straight slots with semicircular ends, through-all or fixed-depth.
- Hole patterns built from explicit coordinates.

This module does not call `HoleWizard5`. Until official signatures and real-version behavior are verified, do not assemble Hole Wizard's long argument lists from memory.

## Units and references

- All input lengths are meters; use `sw_connect.mm()` for conversion.
- `center`, `start` and `end` are local 2D coordinates in the target sketch plane.
- The default reference is `Front Plane`; `sw_part.start_sketch()` handles localized aliases.
- Creation evidence includes meter and millimeter fields; millimeter fields are reporting-only and are not passed back to COM.

## Example

```python
from sw_connect import mm
from sw_hole_features import (
    create_blind_hole,
    create_counterbore_hole,
    create_countersink_hole,
    create_semicircular_slot,
)

blind = create_blind_hole(model, (mm(20), mm(20)), mm(8), mm(10), name="H1_BlindHole")
counterbore = create_counterbore_hole(
    model,
    (mm(50), mm(20)),
    hole_diameter=mm(6),
    counterbore_diameter=mm(12),
    counterbore_depth=mm(4),
    name="H2_Counterbore",
)
countersink = create_countersink_hole(
    model,
    (mm(80), mm(20)),
    hole_diameter=mm(5),
    countersink_diameter=mm(10),
    included_angle_deg=90,
    name="H3_Countersink",
)
slot = create_semicircular_slot(
    model,
    (mm(30), mm(50)),
    (mm(60), mm(50)),
    width=mm(10),
    depth=0,
    name="S1_SemicircularEndedSlot",
)
```

## Acceptance evidence

Creation functions return parameter evidence, not geometric acceptance. Before delivery:

1. Read B-Rep cylindrical faces with `sw_review.collect_geometry_measurements()`.
2. Verify hole diameters and axis positions with `sw_review.validate_hole_positions()`.
3. Read back blind-hole depth, counterbore depth and countersink angle from feature definitions, or review them in a section view.
4. Slot-end cylindrical faces must appear in `slot_arc_candidates`; do not count them as round holes.
5. Compound holes should appear in `compound_holes` as coaxial segments of different diameters.

For each hole, record at least its type, specification, quantity, location from datum edges, center distances, depth/through condition, dimensional tolerances and evidence source.

## Known limitations

- Conical countersinks use an angle/distance chamfer on the through-hole entrance edge. Select that edge by center, radius and reference-plane position, not transient edge names; inspect a section after chamfering to confirm entrance direction.
- B-Rep alone cannot reliably distinguish blind and through holes; cross-check creation parameters or feature-definition readback.
- Current hole patterns create individual features at explicit positions for auditability. Large regular patterns may later use Linear/Circular Pattern wrappers.
