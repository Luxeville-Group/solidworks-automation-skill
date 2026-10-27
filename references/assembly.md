# Assembly and Motion Mate Reference

## Official references

- AddMate5: `https://help.solidworks.com/2023/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.iassemblydoc~addmate5.html`
- GetModelDoc2: `https://help.solidworks.com/2019/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.icomponent2~getmodeldoc2.html`
- GetCorresponding: `https://help.solidworks.com/2019/English/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.icomponent2~getcorresponding.html`
- IsCylinder / CylinderParams: `https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISurface~IsCylinder.html`, `https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISurface~CylinderParams.html`
- Gear Mates: `https://help.solidworks.com/2024/English/solidworks/sldworks/t_Gear_Mates_SWassy.htm`
- Hinge Mates: `https://help.solidworks.com/2023/english/SolidWorks/sldworks/t_hinge_mates.htm`
- Mate Controller: `https://help.solidworks.com/2024/english/Solidworks/sldworks/c_assembly_mate_controller.htm`

## Adding components

Prefer `add_component()` in `scripts/sw_assembly.py`. With localized SW2024 and pywin32,
`AddComponent4()` may return `None` without an exception. The wrapper first tries the
eight-argument `AddComponent5()` signature and falls back to `AddComponent4()`. If both return null, it silently opens the part
in the SolidWorks session, reactivates the assembly and retries `AddComponent5()`.

```python
from sw_assembly import add_component

component = add_component(asm_model, r"E:\parts\base.SLDPRT", x=0, y=0, z=0)
```

Stable underlying call:

```python
component = asm_model.AddComponent5(
    CompPath, 0, "", False, ConfigName, X, Y, Z
)
```

If `AddComponent4` / `AddComponent5` fails, check that the part file exists, the assembly is active and the part has been saved. If necessary, open the part and reactivate the assembly. Real regression check:

```powershell
py -3.13 tests\solidworks_add_component_regression.py --output-dir C:\CADAutomationWorkbench\solidworks_add_component_regression
```

## Workflow for moving assemblies

1. Generate and save each part first. Close part documents no longer being edited to avoid excessive open documents.
2. Create the assembly and insert the base, bearing housings, shafts, gears, covers and other components.
3. Call `resolve_component(component)` before reading a component's features or faces; lightweight/suppressed components can make `GetModelDoc2()` return `None`.
4. Map part reference planes, cylindrical faces or sketch entities into assembly context with `IComponent2.GetCorresponding()`, then select with `Select2()`.
5. Fixed parts can be locked by coincident or distance mates on three reference planes; do not lock rotating parts this way.
6. Use concentric shaft/hole mates with `lock_rotation=False` to retain axial rotation.
7. Couple gears with Gear Mate, selecting axes, bore cylinders, cylindrical faces or axis entities and supplying the tooth-count ratio.
8. A cover hinge can use a concentric mate plus one planar coincident/distance mate to retain one rotational DOF. For Motion analysis, prefer the official GUI Hinge Mate or higher-level MateFeatureData API.
9. Traverse MateGroup subfeatures after creation to verify real mates in the tree. A preview animation only proves scripted movement, not that the assembly is draggable.
10. Export multiple preview views with `sw_review.py`, then manually drag a free part in SolidWorks to verify motion.

## Online engineering guidance

- Official Mechanical Mates documentation states that Gear Mate constrains relative rotation about selected axes by a ratio. Hinge Mate is equivalent to concentric plus coincident mates and can limit angle.
- GoEngineer's mate tutorial describes geometric constraints between parts. Mechanical mates express gear, rack-and-pinion, screw and universal-joint relations; they are not contact simulation: `https://www.goengineer.com/blog/introduction-to-solidworks-mates`
- CodeStack's lightweight-component example notes that `GetModelDoc2()` can return null for lightweight/suppressed components; resolve them or silently open the referenced model: `https://www.codestack.net/solidworks-api/document/assembly/components/lightweight-get-model-doc/`
- CAD Booster emphasizes that part and assembly contexts are not interchangeable. Prefer `GetCorresponding()` + `Select2()` when object references are available, minimizing coordinate-based selection: `https://cadbooster.com/entities-and-getcorresponding-in-the-solidworks-api/`
- A null `GetModelDoc2()` from a lightweight component is common. Resolve components before mating instead of interpreting `None` as a part without features.

## AddMate5 arguments

SolidWorks 2015+ `AddMate5` has 15 arguments; Python COM requires a `VARIANT` wrapper for the by-reference error code:

```python
errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
mate = asm_model.AddMate5(
    mate_type,          # swMateType_e
    align,              # swMateAlign_e; commonly 0=Aligned
    flip,               # bool
    distance,           # Distance mate value in meters
    distance_upper,     # Upper distance limit; equal to distance when unlimited
    distance_lower,     # Lower distance limit; equal to distance when unlimited
    gear_num,           # Gear Mate numerator
    gear_den,           # Gear Mate denominator
    angle,              # Angle in radians
    angle_upper,        # Upper angle limit
    angle_lower,        # Lower angle limit
    for_positioning_only,
    lock_rotation,      # Whether the concentric mate locks rotation
    width_mate_option,  # Width Mate option
    errors,
)
```

Prefer wrappers in `scripts/sw_assembly.py`:

```python
from sw_assembly import (
    add_concentric_mate_by_cylinders,
    add_gear_mate_by_cylinders,
    collect_mate_feature_summary,
)

add_concentric_mate_by_cylinders(
    asm,
    shaft_comp,
    bearing_comp,
    radius_a=(0.004, 0.006),
    radius_b=(0.004, 0.006),
    name="shaft_bearing_concentric",
    lock_rotation=False,
)

add_gear_mate_by_cylinders(
    asm,
    small_gear_comp,
    large_gear_comp,
    teeth_a=18,
    teeth_b=26,
    radius_a=(0.004, 0.008),
    radius_b=(0.004, 0.008),
    name="small_large_gear_ratio_18_26",
)

print(collect_mate_feature_summary(asm))
```

## Mate type enums

Common values verified against the local SW 2024 `SolidWorks.Interop.swconst.dll`:

| Value | Name | Description |
|---:|---|---|
| 0 | `swMateCOINCIDENT` | Coincident |
| 1 | `swMateCONCENTRIC` | Concentric |
| 2 | `swMatePERPENDICULAR` | Perpendicular |
| 3 | `swMatePARALLEL` | Parallel |
| 4 | `swMateTANGENT` | Tangent |
| 5 | `swMateDISTANCE` | Distance |
| 6 | `swMateANGLE` | Angle |
| 10 | `swMateGEAR` | Gear |
| 11 | `swMateWIDTH` | Width |
| 16 | `swMateLOCK` | Lock |
| 22 | `swMateHINGE` | Hinge |

Common component suppression states:

| Value | Name | Description |
|---:|---|---|
| 0 | `swComponentSuppressed` | Suppressed |
| 1 | `swComponentLightweight` | Lightweight |
| 2 | `swComponentFullyResolved` | Fully resolved |
| 3 | `swComponentResolved` | Resolved |
| 4 | `swComponentFullyLightweight` | Fully lightweight |

## Selection and assembly context

Stable sequence:

```python
from sw_assembly import (
    get_component_feature,
    get_assembly_entity,
    find_component_by_name,
    resolve_component,
    select_entities_for_mate,
)

component_a = find_component_by_name(asm, "shaft")
component_b = find_component_by_name(asm, "bearing")
resolve_component(component_a)
resolve_component(component_b)

feature_a = get_component_feature(component_a, ["\u524d\u89c6\u57fa\u51c6\u9762", "Front Plane"])
feature_b = get_component_feature(component_b, ["\u524d\u89c6\u57fa\u51c6\u9762", "Front Plane"])
entity_a = get_assembly_entity(component_a, feature_a)
entity_b = get_assembly_entity(component_b, feature_b)

select_entities_for_mate(asm, entity_a, entity_b, mark=1)
```

Notes (the escaped strings above preserve legacy localized plane-name compatibility):

- Resolve components before selecting entities; `SetSuppression2()` may clear the selection set.
- Use `Select2(False, 1)` for the first entity and append the second with `Select2(True, 1)`.
- Before creating a mate, check `SelectionManager.GetSelectedObjectCount2(-1) == 2`.
- Gear and ordinary mates usually use selection mark `1`; Width Mate uses `16`, Cam-Follower uses `8`.

## Identifying cylindrical faces

Shafts, bores and gear axes are often identified by the largest cylindrical face:

```python
from sw_assembly import find_largest_cylinder_face

face = find_largest_cylinder_face(
    gear_component,
    min_radius=0.004,
    max_radius=0.008,
)
```

Underlying logic:

```python
bodies = part.GetBodies2(0, False)
for body in bodies:
    for face in body.GetFaces():
        surface = face.GetSurface()
        if surface.IsCylinder:
            params = surface.CylinderParams
            radius = params[6]  # Meters
```

## Can the assembly be manipulated interactively?

Yes, provided it contains real mates and is not overconstrained:

- Open the `.SLDASM` in SolidWorks.
- Use `Move Component` to drag a shaft, gear or cover.
- With a correct Gear Mate, rotating one gear around its axis drives the other at the defined ratio and direction.
- If dragging fails, check fixed parts, concentric Lock Rotation, extra planar mates locking a rotating part, and mate errors/overdefinition.

A scripted GIF/video proves only that components can be driven to multiple positions; actual interactivity depends on the SolidWorks mate solver and remaining DOFs.

## Interference and motion limits

Gear Mate does not prevent gear solids from penetrating each other; it defines only their rotation ratio. When geometric clearance matters:

- Verify using `InterferenceDetection` or the GUI interference check.
- Restrict travel with Limit Angle / Limit Distance.
- Save key positions in Mate Controller and generate a Motion Study animation.

```python
interference = asm.InterferenceDetection
interference.TreatSubAssembliesAsComponents = False
interference.TreatCoincidenceAsInterference = False
interference.Done()
count = interference.GetInterferenceCount()
```

## Large assemblies

- For more than 20 parts, generate in batches, save and close the documents, then assemble them.
- Confirm all paths exist before insertion and record failed components.
- Disable unnecessary graphics updates during automation; restore them, rebuild and export previews at the end.
- If too many open documents or internal COM errors cause instability, first use `CloseAllDocuments(False)`; restart the SolidWorks process only if necessary.
