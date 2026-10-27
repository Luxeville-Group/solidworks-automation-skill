# Part Modeling API Reference

## Sketch operations

### Selecting reference planes

```python
# English installation
model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
# Legacy localized alias, escaped to preserve runtime compatibility
model.Extension.SelectByID2("\u524d\u89c6\u57fa\u51c6\u9762", "PLANE", 0, 0, 0, False, 0, None, 0)
```

Reference-plane mapping:
| English name | Legacy alias (Unicode escapes) | Normal direction |
|---|---|---|
| Front Plane | `\u524d\u89c6\u57fa\u51c6\u9762` | Z axis |
| Top Plane | `\u4e0a\u89c6\u57fa\u51c6\u9762` | Y axis |
| Right Plane | `\u53f3\u89c6\u57fa\u51c6\u9762` | X axis |

### Sketch geometry quick reference

| Method | Parameters | Description |
|---|---|---|
| `CreateLine(x1,y1,z1, x2,y2,z2)` | Start/end coordinates (meters) | Line |
| `CreateCircleByRadius(cx,cy,cz, r)` | Center + radius | Circle |
| `CreateCenterRectangle(cx,cy,cz, rx,ry,rz)` | Center + corner | Center rectangle |
| `CreateCornerRectangle(x1,y1,z1, x2,y2,z2)` | Opposite corners | Corner rectangle |
| `CreateArc(cx,cy,cz, x1,y1,z1, x2,y2,z2, dir)` | Center + endpoints + direction | Arc |
| `CreatePolygon(cx,cy,cz, sx,sy,sz, sides, inscr)` | Center + vertex + side count | Regular polygon |
| `CreateEllipse(cx,cy,cz, mx,my,mz, r)` | Center + major-axis endpoint + minor radius | Ellipse |
| `CreateSpline2(pointArray, closed)` | Point array + closure flag | Spline |
| `CreateSketchSlot(type, w, w, ...)` | Type + width + endpoints | Slot |

### Sketch constraints

```python
# Add a constraint after selecting entities.
model.SketchAddConstraints("sgHORIZONTAL")
```

Common relations: `sgHORIZONTAL`, `sgVERTICAL`, `sgCOLINEAR`, `sgPARALLEL`, `sgPERPENDICULAR`, `sgTANGENT`, `sgCONCENTRIC`, `sgEQUAL`, `sgSYMMETRIC`, `sgMIDPOINT`, `sgCOINCIDENT`. Use `sgFIXED` only for deliberately fixed references; do not bulk-fix entities to pretend a parametric sketch is fully defined.

Coordinates set initial geometry; they are not driving dimensions or geometric relations. Basic circle/rectangle sketches may use `sw_sketch_quality.fully_define_sketch(model)` in edit mode; it adds dimensions/relations from the real origin and reads back constraint state, dimension count and Fix count. Explicitly define design parameters for complex sketches, then check with `inspect_model_sketches(model)`. Missing dimensions, dangling entities or insufficient evidence require review.

### Native patterns

`sw_part.linear_pattern()` delegates to `sw_pattern`, selecting the exact seed feature and a real straight edge parallel to the direction vector, then calling the 20-argument `FeatureLinearPattern4`. Direction vectors are dimensionless; spacing remains meters. Stop on selection failure. Circular patterns use explicit axis names/entities; `InsertAxis2` is not a FeatureManager member. Real SW2026 tests verified that hole counts and centers remain unchanged after saving, reopening and changing thickness.

### Stable sketch selection

Prefer the `sw_part.sketch()` context manager or `end_sketch()` return value over relying solely on handwritten `SelectByID2("Sketch1", "SKETCH", ...)`. Repeated failed name-based SKETCH selection has been reported in localized SolidWorks 2024.

Recommended:

```python
with sketch(model, "Front Plane") as sketch_name:
    sketch_circle(model, 0, 0, mm(25))
feature = extrude_boss(model, sketch_name, mm(50))
```

Manual workflow:

```python
start_sketch(model, "Front Plane")
sketch_circle(model, 0, 0, mm(25))
sketch_ref = end_sketch(model)
feature = extrude_boss(model, sketch_ref, mm(50))
```

Internal selection order for `extrude_boss()` / `extrude_cut()`: active sketch reference -> reference cached at creation -> FeatureByName -> SelectByID2("SKETCH"). A leftover selection set is no longer evidence that the intended sketch is selected.

## Feature operations

### FeatureExtrusion3 arguments

```python
feature_mgr.FeatureExtrusion3(
    Sd,           # bool: single direction (True) or both directions (False)
    Flip,         # bool: reverse cutting side
    Dir,          # bool: reverse extrusion direction
    T1,           # int: end condition 1 (table below)
    T2,           # int: end condition 2 (for both directions)
    D1,           # float: depth 1 (meters)
    D2,           # float: depth 2
    Dchk1,        # bool: draft 1
    Dchk2,        # bool: draft 2
    Ddir1,        # bool: draft 1 outward
    Ddir2,        # bool: draft 2 outward
    Dang1,        # float: draft angle 1 (radians)
    Dang2,        # float: draft angle 2
    OffsetReverse1, # bool: reverse offset 1
    OffsetReverse2, # bool: reverse offset 2
    TranslateSurface, # bool: translate surface
    Merge,        # bool: merge result
    UseFeatScope, # bool: automatic body scope
    UseAutoSelect, # bool: automatic selection
    T0,           # bool:
    StartOffset   # float: start offset
)
```

End-condition enums:
| Value | Name | Description |
|---|---|---|
| 0 | swEndCondBlind | Specified depth |
| 1 | swEndCondThroughAll | Through all |
| 2 | swEndCondThroughAllBoth | Through both sides |
| 5 | swEndCondUpToSurface | Up to surface |
| 6 | swEndCondMidPlane | Symmetric about midplane |
| 7 | swEndCondUpToBody | Up to body |

### FeatureCut4 arguments

Similar to FeatureExtrusion3, but for cuts. Additional arguments:
- `NormalCut`: normal cut
- `FlipSide`: reverse cutting side

### FeatureRevolve2 arguments

```python
feature_mgr.FeatureRevolve2(
    SingleDir,     # bool: single direction
    IsSolid,       # bool: solid revolve (True)
    IsThin,        # bool: thin revolve
    IsCut,         # bool: revolved cut
    ReverseDir,    # bool: reverse direction
    BothDirectionUpToSameEntity, # bool
    Dir1Type,      # int: end condition (0=Blind)
    Dir2Type,      # int
    Dir1Angle,     # float: revolution angle (radians)
    Dir2Angle,     # float
    OffsetReverse1, # bool
    OffsetReverse2, # bool
    OffsetDistance1, # float
    OffsetDistance2, # float
    ThinType,      # int: thin-feature type
    ThinThickness1, # float
    ThinThickness2, # float
    Merge,         # bool
    UseFeatScope,  # bool
    UseAutoSelect  # bool
)
```

### Recommended stepped-shaft workflow

Create shaft bodies with a half-section profile, centerline and revolved boss in one operation rather than extruding and merging successive cylinders. This keeps the feature tree shorter and makes shoulder positions and total length easier to drive from parameters.

Recommended approach:

1. Describe shaft segments in a millimeter parameter table: `start_mm`, `end_mm`, `diameter_mm`.
2. Draw a centerline on `Front Plane` as the revolution axis.
3. Build a closed half-section profile from the segment radii.
4. Call `FeatureRevolve2(..., 2*pi, ...)` and immediately verify the returned feature is not `None`.
5. Record tolerances, GD&T and roughness as engineering requirements in properties or delivery notes; do not perturb nominal solid dimensions to express them.

Minimal pattern:

```python
segments = [
    {"start": 0, "end": 43, "diameter": 56},
    {"start": 43, "end": 113, "diameter": 65},
]

with sketch(model, "Front Plane") as sketch_name:
    model.SketchManager.CreateCenterLine(mm(-5), 0, 0, mm(120), 0, 0)
    points = [(0, 0), (0, 28), (43, 28), (43, 32.5), (113, 32.5), (113, 0), (0, 0)]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        model.SketchManager.CreateLine(mm(x1), mm(y1), 0, mm(x2), mm(y2), 0)

model.ClearSelection2(True)
model.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
feature = model.FeatureManager.FeatureRevolve2(
    True, True, False, False, False, False,
    0, 0, 2 * math.pi, 0,
    False, False, 0, 0, 0, 0, 0,
    True, True, True,
)
if feature is None:
    raise RuntimeError("Failed to create the stepped shaft revolved body")
```

### Oblong slots on cylindrical surfaces

For keyways, oblong slots or local recesses on a cylindrical exterior, do not cut directly from the center plane. Such cuts can split the shaft and appear as a large planar opening instead of a surface recess.

Stable approach:

1. Create a reference plane parallel to `Front Plane`, offset by approximately the target cylinder radius.
2. Draw the oblong slot on that tangent plane using `sketch_slot()`.
3. Express slot depth as a blind cut; try one direction first, then reverse `flip` if it fails.
4. Hide the temporary plane after successful creation so orange reference graphics do not obscure the preview.

```python
plane = model.FeatureManager.InsertRefPlane(8, mm(radius_mm), 0, 0, 0, 0)
plane.Name = "Plane_Keyway_Tangent"

model.Extension.SelectByID2(plane.Name, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0)
model.SketchManager.InsertSketch(True)
sketch_name = model.SketchManager.ActiveSketch.Name
sketch_slot(model, mm(x1), 0, mm(x2), 0, mm(slot_width_mm / 2))
model.SketchManager.InsertSketch(True)

feature = extrude_cut(model, sketch_name, mm(depth_mm), direction=True, flip=True)
if feature is None:
    feature = extrude_cut(model, sketch_name, mm(depth_mm), direction=True, flip=False)
if feature is None:
    raise RuntimeError("Failed to create the cylindrical-surface slot")
```

Note: `CreateSketchSlot`'s `radius` argument relates to slot width; verify its actual behavior in a local test. For precise manufacturing widths, check exported geometry by measurement or drawing.

### Fillets/chamfers

```python
# FeatureFillet arguments
feature_mgr.FeatureFillet(
    Options,   # int: 195 = common default
    R1,        # float: radius (meters)
    R2,        # float: second radius
    R3,        # float: third radius
    Rarray1,   # variant: radius array 1
    Rarray2,   # variant: radius array 2
    Rarray3    # variant: radius array 3
)

# InsertFeatureChamfer
feature_mgr.InsertFeatureChamfer(
    Options,     # int: 4 = angle-distance
    ChamferType, # int: 1 = equal distance
    Width,       # float: distance (meters)
    Angle,       # float: angle (radians)
    OtherDist,   # float: other distance
    VertexDist1, # float
    VertexDist2, # float
    VertexDist3  # float
)
```

### Current reliability limits for fillets/chamfers

The central problem is **stable selection of the intended edges/faces**, not merely API arguments. Version, UI language, feature order and sketch profiles can change automatically named `Edge`/`Face` entities. Random-coordinate SelectByID2 followed by FeatureFillet is not a high-reliability workflow.

Recommended strategy:

1. Baseline demos and unattended batch scripts should not use cosmetic fillets/chamfers as their success criterion.
2. When a fillet is needed, prefer stable sketch profiles where suitable, such as arcs, slots or rounded rectangles.
3. For required feature fillets/chamfers, enumerate bodies/faces/edges, filter by geometric conditions, then select entity objects. Do not rely on temporary names such as `Edge1`.
4. On a cosmetic fillet failure, retain the sharp-edge model and explicitly report that the appearance fillet was not applied, rather than failing the entire generation flow.

## SelectByID2 entity types

| Type string | Description |
|---|---|
| `"PLANE"` | Reference plane |
| `"FACE"` | Face |
| `"EDGE"` | Edge |
| `"VERTEX"` | Vertex |
| `"SKETCH"` | Sketch |
| `"BODYFEATURE"` | Body feature |
| `"COMPONENT"` | Component |
| `"AXIS"` | Axis |
| `"SKETCHSEGMENT"` | Sketch segment |
| `"SKETCHPOINT"` | Sketch point |
| `"EXTSKETCHSEGMENT"` | External sketch segment |
| `"REFERENCECURVES"` | Reference curve |
