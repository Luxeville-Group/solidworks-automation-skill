# Design-Specification-Driven Modeling

Describe a part in a **version-controlled design specification**, then let the executor rebuild it idempotently.

## Why use it?

Imperative calls (`sketch_circle` -> `extrude_boss` -> `save`) suit one-off scripts, but are less suitable
for product iteration. Engineers want to change a mounting plate to 8 mm thick and its four M6 holes to M8,
rather than rewrite the entire modeling sequence. A specification provides:

1. **Diffs and commits**: version the design intent instead of a one-off script.
2. **Idempotent rebuilding**: the same specification produces the same feature-tree structure.
3. **Built-in verification**: the `verify` section reads geometry after building and compares it with expectations.

## Minimal usable specification

```json
{
  "schema_version": "1.0",
  "part_name": "motor_mount",
  "units": "mm",
  "base": { "type": "rect_plate", "width": 120, "height": 80, "thickness": 8 },
  "holes": [
    { "id": "H1", "type": "through", "diameter": 6.6, "position": [15, 15] },
    { "id": "H2", "type": "through", "diameter": 6.6, "position": [105, 15] },
    { "id": "H3", "type": "through", "diameter": 6.6, "position": [15, 65] },
    { "id": "H4", "type": "through", "diameter": 6.6, "position": [105, 65] }
  ],
  "fillets": [ { "radius": 4, "axis": "z", "convex_only": true } ],
  "verify": { "envelope_mm": [120, 80, 8], "hole_count": 4, "tolerance_mm": 0.1 }
}
```

## Coordinate convention (important)

**The origin is the plate's lower-left corner**. The plate lies in the first quadrant of XY and extrudes along +Z.

Thus `position: [15, 15]` means 15 from the left edge and 15 from the bottom edge, with no mental center-offset calculation.
The specification directly adopts this common drawing convention for locating holes.

> If a hole center lies outside the plate or its wall crosses a boundary, the executor reports and lists the offending holes **before** creation.
> SolidWorks may silently reject out-of-bounds holes, appearing to create a feature that is not present.
> Early validation identifies a coordinate problem immediately instead of suggesting an API failure.

## Field reference

### base (base solid)

| type | Required fields | Description |
|---|---|---|
| `rect_plate` | `width` `height` `thickness` | Rectangular plate with lower-left origin |
| `cylinder` | `diameter` `height` | Cylinder centered at the origin |
| `none` | — | No base solid; create only subsequent features (must be **explicit**) |

Omitting `base` returns `SPEC_EMPTY`: an omission and an intentional feature-only model are different intentions.

### holes

| type | Required fields |
|---|---|
| `through` | `diameter` `position` |
| `blind` | `diameter` `depth` `position` |
| `counterbore` | `diameter` `counterbore_diameter` `counterbore_depth` `position` |
| `countersink` | `diameter` `countersink_diameter` `angle` (default 90, included angle) `position` |

Always supply `id` where possible. Missing IDs are numbered automatically (`H1`, `H2`...) with a warning because inspection records need
stable traceability; inserting a new hole can shift every automatic ID.

**Hole patterns**: add a `pattern` field to define multiple holes; the executor expands and renumbers individual holes:

```json
{ "id": "B", "type": "through", "diameter": 5.5, "position": [60, 40],
  "pattern": { "type": "circular", "count": 6, "radius": 30, "start_angle": 0 } }
```

```json
{ "id": "L", "type": "through", "diameter": 5.5, "position": [10, 10],
  "pattern": { "type": "linear", "count": 4, "dx": 20, "dy": 0 } }
```

`circular` positions are offsets from `position`; `start_angle` is degrees, with zero along +X.

### fillets

```json
{ "radius": 4, "axis": "z", "convex_only": true }
```

| Field | Description |
|---|---|
| `radius` | Fillet radius |
| `axis` | `x` / `y` / `z` / `vertical` / `all`; fillet only edges parallel to that axis |
| `convex_only` | Convex exterior edges only |
| `concave_only` | Concave internal edges only |

A radius exceeding half the plate thickness produces a DFM warning: SolidWorks may fail or produce self-intersection.

If no edges are found, the fillet is **skipped with a warning**. Execution does not fall back to operating on the current selection set,
which could fillet the wrong edges and produce difficult-to-diagnose geometry.

### verify (post-build verification)

| Field | Description |
|---|---|
| `envelope_mm` | Expected bounding-box size `[length, width, height]` |
| `hole_count` | Expected hole count |
| `tolerance_mm` | Dimensional tolerance (default 0.1) |
| `min_mass_g` / `max_mass_g` | Lower/upper mass limits |

Verification has three states: `pass` (all match), `warn` (deviations requiring human review),
and `skipped` (no verify section). **Deviations do not automatically mean failure**: a design change can also
change dimensions, so an engineer must judge them.

## Units

`units` accepts `mm` (default), `cm`, `m` and `in`. Express all specification lengths in that unit;
the executor converts them to millimeters. **Units are never guessed**: unknown units cause an error.

## Usage

```
# Validate only; repeat while editing the specification.
design_spec_validate  { "spec_path": "D:/designs/motor_mount.json" }

# Validate and build.
design_spec_build     { "spec_path": "D:/designs/motor_mount.json",
                        "output_path": "D:/designs/motor_mount.sldprt" }
```

Direct Python usage:

```python
from scripts.design_spec import load_design_spec
from scripts.build_from_spec import build_from_spec
from scripts.sw_connect import connect_solidworks, new_document, save_document

validation = load_design_spec("D:/designs/motor_mount.json")
assert validation["status"] == "ok", validation["errors"]

sw, _ = connect_solidworks()
model = new_document(sw, "part")
audit = build_from_spec(model, validation["normalized"])
print(audit["status"], audit["verification"])
save_document(model, "D:/designs/motor_mount.sldprt")
```

## Result structure and evidence

The audit result from `build_from_spec` includes:

| Field | Meaning |
|---|---|
| `status` | `ok` / `warn` / `error` |
| `steps` | Actual execution of each step: feature name, position and success |
| `hole_count_requested` / `hole_count_created` | Requested versus actually created hole counts |
| `fillet_results` | Selected-edge count and feature name for each fillet |
| `warnings` | Nonblocking issues: DFM guidance, skipped fillets, missing material |
| `errors` | Blocking issues with actionable next steps |
| `measurements.bounding_box` | Read-back bounding box in millimeters |
| `measurements.mass_properties` | Read-back mass, volume and material |
| `verification` | Comparison with the `verify` section |

For incremental inspection, examine `steps`: it records each hole's position and resulting feature
so the drawing can be checked item by item.

## Common error codes

| Error code | Meaning and action |
|---|---|
| `SPEC_UNIT_UNSUPPORTED` | Unsupported unit; use mm/cm/m/in |
| `SPEC_EMPTY` | Missing `base`; supply it or explicitly use `"type": "none"` |
| `SPEC_HOLE_ID_DUPLICATE` | Duplicate hole ID; make it unique |
| `SPEC_FIELD_MISSING` | A required dimension for the hole type is missing |
| `SPEC_NOT_POSITIVE` | A dimension must be positive |
| `SPEC_HOLE_TYPE` | Unknown hole type |
| `SPEC_HOLES_TOO_MANY` | Hole count exceeds the limit of 200 |
| `SPEC_JSON_INVALID` | Invalid JSON; includes parsing location |
| `SPEC_FILE_MISSING` | File path does not exist; use an absolute path |

The validator returns **all errors together** rather than stopping at the first, allowing one complete correction pass.
