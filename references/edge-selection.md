# Semantic Edge Selection for Fillets and Chamfers

## Why coordinate-based SelectByID2 is unreliable

A traditional SolidWorks edge-selection call is:

```python
model.Extension.SelectByID2("Edge1", "EDGE", 0.05, 0.03, 0.0, False, 0, None, 0)
```

Here `x, y, z` are **hard-coded entity coordinates** with two serious problems:

1. **Model changes invalidate them.** A changed plate thickness or new hole shifts coordinates and selection may fail silently.
2. **Failure can be silent.** When `SelectByID2` returns `False`, a subsequent `FeatureFillet` may
   operate on the current selection set, which can be empty or left over from an earlier operation,
   creating a wrong feature that is difficult to diagnose.

## Select by B-Rep geometry

`scripts/sw_edge_select.py` traverses B-Rep topology and selects edges by **geometric conditions**,
then calls each edge object's `Select2`. It avoids name/coordinate strings and remains usable after rebuilds.

```python
from scripts.sw_edge_select import select_edges
from scripts.sw_part import fillet
from scripts.sw_connect import mm

# Chamfer only convex edges parallel to Z (vertical exterior edges of the plate).
result = select_edges(model, {"axis": "z", "convex_only": True})
if result["status"] == "ok":
    fillet(model, mm(4))
```

Corresponding MCP tools:

```
solidworks_list_edges  { "axis": "z" }              # Inspect available edges first.
solidworks_fillet      { "radius_mm": 4, "axis": "z", "convex_only": true, "dry_run": true }
solidworks_fillet      { "radius_mm": 4, "axis": "z", "convex_only": true }
```

**Use `dry_run: true` first** to confirm the intended edges before executing.

## Filters

| Parameter | Values | Description |
|---|---|---|
| `axis` | `x` / `y` / `z` / `vertical` / `all` | Keep only **straight edges** parallel to the axis; `all` disables direction filtering |
| `min_length_mm` / `max_length_mm` | Numeric | Filter by edge length |
| `circular` | `true` / `false` | Keep circular / noncircular edges |
| `diameter_mm` + `diameter_tolerance_mm` | Numeric | Filter circular edges by diameter, e.g. hole entrances |
| `position_mm` + `position_tolerance_mm` | `[x,y,z]` | Require the edge midpoint near these coordinates |
| `convex_only` | `true` | Exterior convex edges only, for outside fillets |
| `concave_only` | `true` | Interior concave edges only, for inside fillets |

`convex_only` and `concave_only` cannot both be true.

## Typical usage

**Exterior fillets on plate corners**

```json
{ "axis": "z", "convex_only": true }
```

**Hole-entrance chamfer** (locate circular edges by diameter)

```json
{ "circular": true, "diameter_mm": 6.6, "diameter_tolerance_mm": 0.05 }
```

**Long edges only** (avoid intersecting fillets on short edges)

```json
{ "axis": "all", "min_length_mm": 50 }
```

**Internal fillets in weight-reduction pockets**

```json
{ "axis": "z", "concave_only": true }
```

## Return value

```json
{
  "status": "ok",
  "selected_count": 4,
  "selected": [
    { "index": 3, "length_mm": 8.0, "mid_point_mm": [0.0, 0.0, 4.0],
      "is_circle": false, "diameter_mm": null, "convexity": "convex" }
  ],
  "rejected_count": 8,
  "rejected_sample": [ { "index": 0, "reasons": ["Direction is not parallel to the z axis"] } ]
}
```

`rejected_sample` explains **why each edge was excluded**, enabling targeted adjustments instead of blindly relaxing filters.

**If no edges match, return `status: "error"` and create no feature.** This is deliberate:
continuing silently could apply fillets to wrong edges. The error includes a suggestion to
call `solidworks_list_edges`.

## Convexity classification

`convexity` is computed from the normals of adjacent faces, a geometric definition independent of SolidWorks
display settings.

Adjacent-face parameters must be read. **A read failure returns `null` and does not exclude the edge**, favoring inclusion
over silently omitting a requested edge. Review such cases with `solidworks_list_edges`.

## Known limits

- Circular edges have no straight axis direction and are excluded by `axis`; use `circular` + `diameter_mm` for hole entrances.
- Tangent edges between surfaces, including edges introduced by existing fillets, are returned as ordinary edges. **When applying
  several fillet/chamfer groups, later groups may select tangent edges created by earlier groups.** Inspect topology with
  `solidworks_list_edges` before each operation, or separate groups into distinct modeling stages.
- Hold-line fillets remain limited; see `subskills/solidworks-fillet-chamfer-cnc/`.

## API notes

The second argument of `IEdge::Select4(Append, Callout)` is a **Callout object**
and must be a Dispatch VARIANT. Passing Python `None` causes
`Type mismatch` (`0x80020005`).

`IEdge::Select2(Append, Mark)` avoids this issue, so the wrapper **tries Select2 first and falls back to
Select4 only on failure**. Use the same order in custom selection code.

```python
# Correct
edge.Select2(True, 0)
# When Select4 is required
from scripts.sw_connect import create_empty_dispatch_variant
edge.Select4(True, create_empty_dispatch_variant())
```

## A fillet API pitfall

`IFeatureManager::FeatureFillet` accepts only **four arguments**:

```python
model.FeatureManager.FeatureFillet(195, radius, 0, 0)   # (Options, Radius, R1, R2)
```

Do not pass seven arguments by appending `None`; SolidWorks 2024/2026 reports
a nonoptional/required argument error (`0x8002000F`). Older documentation and early wrappers contained this mistake.

The selected-edge set must also be nonempty. `sw_part.fillet()` checks it explicitly and raises
`ValueError` when empty, recommending `select_edges()`.
