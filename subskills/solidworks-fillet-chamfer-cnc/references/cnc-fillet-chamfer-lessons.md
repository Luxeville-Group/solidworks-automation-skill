# CNC Fillet/Chamfer Modeling and Acceptance Lessons

## Version 2 capability boundaries

Beyond constant-radius edge fillets, angle chamfers and hole-mouth chamfers, six isolated advanced paths have native tests. Declare support by version and input topology; UI availability alone does not establish stability across environments:

- Three-intermediate-point variable radius, setback corner, face fillet, full-round, plane–cylinder G2 and asymmetric width-width chamfers have minimal SW2026 SP1.1 native regressions.
- Hold-line/hold-face fillets remain blocked on local SW2026 SP1.1. Projected split lines and marks 2/4/8 are deterministic, but Python, C# PIA, SWBasic and in-process unmanaged C++ all converge on ISetHoldLines failure. Native probes may crash the SOLIDWORKS server; rerun only with explicit authorization in an isolated instance.
- Vertex chamfers, freeform-surface G1/G2, complex relief grooves and five-axis surface cleanup are not covered.

For extensions, consult target-version official APIs, then create/save/close/reopen/read features/export STEP/review multiple views on a minimal part. Upgrade capability levels only after repeated regressions pass.

## Version 2 offline gates

scripts/cnc_strategy.py checks before COM:

- Finite numbers and positive dimensions; permitted zero fillet/chamfer values explicitly disable the operation.
- Boss-to-base shoulder width and limits on fillet radius/chamfer depth.
- Mounting counterbores, locating holes, center slots and weight-reduction pockets: envelopes, walls and clearances.
- Remaining floor thickness below counterbores/pockets, and counterbore diameter greater than through-hole diameter.
- DFM warnings for sharp internal corners in rectangular pockets; obround pockets are the default.

Default locating holes are now at (0, ±24) mm. The old (±32, 0) mm positions intersect a 62 mm-long, 16 mm-wide center slot and cannot be delivered as independent locating holes.

## Lessons from validation

The CNC aluminum-mount validation showed repeatable multi-fillet/chamfer COM modeling when feature order and edge selection are controlled. The successful model included a baseplate, center boss, mounting holes/counterbores, locating holes, center slot, weight-reduction pockets and real Fillet/Chamfer features, passing sw_review rules.

Key findings:

- Begin with simple topology and add complexity gradually.
- Large fillets and outer chamfers are more stable before holes/slots than after every cut.
- Actual edge-object selection is more stable than generated names or coordinate clicks.
- Check each feature return for None/False; stop or explicitly degrade on failure.
- Saving to a same-name output already open in SOLIDWORKS can fail, commonly with SaveAs error 1.

## Recommended APIs and wrappers

Prefer the existing parent wrappers:

```python
from sw_session import SolidWorksSession
from sw_connect import mm, get_com_member, create_empty_dispatch_variant
from sw_export import export_to_step
from sw_review import run_review
from sw_appearance import set_document_appearance
```

Common SOLIDWORKS APIs:

```python
model.FeatureManager.FeatureExtrusion3(...)
model.FeatureManager.FeatureCut4(...)
model.FeatureManager.FeatureFillet(195, radius, 0, 0, None, None, None)
model.FeatureManager.InsertFeatureChamfer(4, 1, distance, math.pi / 4, 0, 0, 0, 0)
edge.Select2(append, 0)
model.GetBodies2(0, False)
body.GetEdges()
edge.GetCurve()
curve.IsLine()
curve.IsCircle()
curve.CircleParams()
```

In pywin32, GetStartVertex, GetEndVertex, FirstFeature and similar members may be callable-looking properties; read with get_com_member().

## Stable edge selection

Avoid Edge1/Edge2 or unnamed coordinate selections. Recommended pattern:

```python
def edge_points(edge):
    start_vertex = get_com_member(edge, "GetStartVertex")
    end_vertex = get_com_member(edge, "GetEndVertex")
    if not start_vertex or not end_vertex:
        return None
    return (
        tuple(get_com_member(start_vertex, "GetPoint")),
        tuple(get_com_member(end_vertex, "GetPoint")),
    )

def midpoint(edge):
    points = edge_points(edge)
    if not points:
        return None
    start, end = points
    return tuple((start[i] + end[i]) / 2.0 for i in range(3))

def select_edges(model, predicate):
    model.ClearSelection2(True)
    count = 0
    for body in get_com_member(model, "GetBodies2", 0, False) or []:
        for edge in get_com_member(body, "GetEdges") or []:
            if predicate(edge) and edge.Select2(count > 0, 0):
                count += 1
    return count
```

Classify by endpoints, circle center, radius, direction and plane. The template uses 0.05 mm tolerance and exact counts: four base vertical corners, eight outer edges after filleting and six mouth circles for four counterbores plus two locating holes.

Record signatures independent of generated edge names for every selection:

```json
{
  "curve": "circle",
  "center_mm": [46.0, 28.0, 18.0],
  "radius_mm": 6.5
}
```

A wrong count indicates ambiguous topology, not simply insufficient tolerance. Stop and report all candidate signatures; do not expand to millimeter-scale tolerances or continue to feature creation.

### Selecting edges in existing models

The template's 4/8/6 counts apply only to that mounting-body topology. For existing parts:

1. Export candidate edge signatures and an isometric preview.
2. Restrict targets using supplied datums, features, dimensional ranges and adjacent faces; do not reuse fixed template counts.
3. Record the new expected count in the job plan and obtain human confirmation.
4. Re-enumerate edges after editing; do not reuse COM Edge objects cached before filleting/chamfering.

## Recommended feature order

For CNC mounts, connector blocks and machined bases:

1. Extrude the rectangular baseplate.
2. Extrude the top boss.
3. Apply large outer fillets and top/bottom edge chamfers.
4. Cut weight-reduction pockets.
5. Cut through mounting holes.
6. Add counterbores/countersunk steps.
7. Add locating holes.
8. Cut the central obround slot.
9. Apply small mouth chamfers.
10. Save, export STEP and review previews.

Moving step 3 after holes/slots can cause long solves on complex topology. If necessary, reduce radius and selected-edge count, testing one class at a time.

## Radius and fallback policies

Conservative example defaults:

- Base vertical-corner fillets: R6–R10.
- Boss vertical-corner fillets: R3–R6.
- Outer chamfers: C0.8–C2.
- Boss top chamfers: C0.5–C1.
- Hole-mouth chamfers: C0.3–C0.8.

The template defines two policies:

- strict: try only the requested dimensions and stop on failure; appropriate when dimensions are nonnegotiable.
- progressive: try 100%, 75%, then 50% of the request, never below 0.1 mm.

Progressive is not silent repair. Record requested_value_mm, actual_value_mm, degraded status and each failure in parameter JSON; external descriptions must use actual dimensions.

Manual troubleshooting order:

1. Reduce radius/chamfer distance.
2. Select fewer edges at once.
3. Move large fillets before holes/slots.
4. With user permission, explicitly set noncritical pocket/slot fillets to 0 and regenerate the plan.
5. Never silently skip critical fillets/chamfers; retain blocked status when requirements cannot be met.

A nonempty feature return still requires ForceRebuild3(False) and named feature-tree read-back. Only None permits the next fallback size. If a returned feature disappears after rebuild, stop instead of stacking more features.

## Recommended extensions

Ordered by benefit and risk:

1. **General edge inventory for existing models:** export edge/face adjacency, curve type, length, bounds and signatures for human confirmation of semantic groups.
2. **Additional machining features:** keyways, dovetail slots, T-slots, relief grooves, O-ring grooves and countersinks; add parameter/collision checks for each before connecting COM.
3. **Multiple bodies and configurations:** store edge-selection evidence independently for each body and configuration; never reuse temporary topology references across configurations.
4. **Advanced fillets/chamfers:** use six independent execution paths and evidence sets for multipoint variable-radius, face/full-round, setback, G2 surface combinations and distance-distance chamfers; do not use one universal wrapper. Keep hold-line negative probes separate.

## SolidWorks 2026 advanced fillet test results

- Variable radius: use `FeatureFillet3`, mark 1 for the target edge and mark 256 for intermediate `POINTREF` objects. Read back R3/R6/R4 at 25%/50%/75%; returned positions are percentages `25/50/75`, not fractions `0.25/0.5/0.75`.
- Face fillet: `CreateDefinition(swFmFillet)` → `Initialize(swFaceFillet)` → `SetFaces`; both face sets must read back `Type=2`.
- G2 surface combination: put the cylinder top plane and cylindrical side face into separate face sets and set `CurvatureContinuous=true`; after reopening, verify `Type=2` and the G2 flag.
- Full-round: also use `ISimpleFilletFeatureData2`; populate side set 1, center set and side set 2 separately, check their counts, and read back `Type=3`.
- Setback: in `FeatureFillet3`, mark the three intersecting edges 1 and the corner vertex 0; distances require `SAFEARRAY<double>`. With pywin32, COM can accept an ordinary `tuple` while the solver returns `None`; use `VARIANT(VT_ARRAY | VT_R8, ...)`.
- Distance-distance chamfer: set `InsertFeatureChamfer` `ChamferType=2` and write the two distances to `Width/OtherDist`, not the vertex-chamfer parameter slots; `GetEdgeChamferDistance` side indices are `0/1`.
- Generate a separate part for each of the six cases so an earlier advanced fillet does not change later topology. Mark `verified` only after save, STEP export, reopen, FeatureData readback and review report all pass.
- Hold lines: the official API requires face-set marks `2/4`, hold-line mark `8` and `HoldLines`; `ISetHoldLines` explicitly supports only in-process unmanaged C++. The implementation therefore includes C# PIA, SWBasic and an MSVC x64 native bridge rather than relying only on Python. SW2026 SP1.1 / Revision 34.1.1 still reproduces a server fault at native `ISetHoldLines`, so the default returns a structured block. Regression requires `GetHoldLineCount=1` both after creation and after reopening; an ordinary `Fillet` or split-line feature must not be reported as success.

Official API references:

- [IFeatureManager.FeatureFillet3](https://help.solidworks.com/2026/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeatureManager~FeatureFillet3.html)
- [ISimpleFilletFeatureData2](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISimpleFilletFeatureData2.html)
- [HoldLines](https://help.solidworks.com/2025/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISimpleFilletFeatureData2~HoldLines.html)
- [ISetHoldLines (in-process unmanaged C++ only)](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISimpleFilletFeatureData2~ISetHoldLines.html)
- [InsertFeatureChamfer](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~InsertFeatureChamfer.html)

## Open-source complex bracket regression

The second complex regression uses the MIT-licensed [parametric-bracket-library](https://github.com/archimedes-market/parametric-bracket-library) `l_gusset`, pinned to commit `5b285130...`, CadQuery 2.8.0 and generated STEP SHA-256 `cc2d38a4...`. The CadQuery model contains two perpendicular mounting plates, a triangular gusset and six holes; the SW2026 STEP-import baseline is `1 solid / 18 faces / 49 edges`. On the same body, the enhancement script creates a four-point variable-radius fillet (positions `20/40/60/80%`, radii `1.2/1.8/0.9/1.5 mm`) and a C0.8/C1.4 distance-distance chamfer. Evidence includes final `20 faces / 55 edges`, reopened FeatureData and four-view review.

The existing FreeCAD-library case provides another independent source and geometry-signature check:

Use FreeCAD-library `2020_corner_bracket-Corner.step`, pinned to commit `b342740f...` and SHA-256 `25e3fbc1...`. It contains a base plate, upright plate, reinforcing structure, holes and an obround slot; the source topology is `1 solid / 40 faces / 98 edges / 64 vertices`. The script selects the unique diagonal edge with endpoints `(-0,-20,3)→(-0,-3,20) mm` and length `24.041631 mm`, then creates a real C0.2/C0.4 distance-distance chamfer. Processed and reopened topology must both be `1 solid / 41 faces / 101 edges / 66 vertices`. This complex case adds solver and persistence evidence on real topology; the six controlled cases still provide independent exact readback of advanced parameters.

The case uses FreeCAD-library under [CC BY 3.0](https://github.com/FreeCAD/FreeCAD-library); contributor attribution and download hashes are recorded in `examples/open_source_corner_bracket_case.json`.
5. **Manufacturing acceptance:** add tool diameter, tool length, minimum internal radius, clamping direction, accessibility and operation recommendations. Passing rules still requires CAM/process-engineer review.

## Common failures

### Extrusion returns None

A complex rounded sketch is often not closed. Extrude a simple rectangular sketch, then apply real Fillet features to the vertical corners.

### Fillet/chamfer takes too long

Likely causes include complex topology after hole cuts, excessive radius or overly broad edge selection. Test each edge group separately: base vertical corners, boss vertical corners, top edges, bottom edges and hole mouths.

### SaveAs error code 1

The target file may already be open in SolidWorks. Close a document with the same name before creating it:

```python
try:
    session.close(title=Path(output_part).name)
except Exception:
    pass
```

### Preview appears transparent or oddly colored

Do not treat an appearance problem as geometry failure. First check the review report and ensure previews are not blank. For precise appearance requirements, use `set_document_appearance(model, "silver")` or split into assembly components and color them separately.

## Review checklist

Read the review report after completion and confirm at least:

- `evaluation.status`
- `checks.previews_created`
- `checks.previews_not_blank`
- `checks.expected_outputs_exist`
- Whether `model.features` contains the expected `Fillet`, `Chamfer` and `Cut` features.

After rule-based review passes, also inspect the `isometric` and `top` previews manually for proportions, hole positions, counterbores, slots, pockets and fillet directions.
