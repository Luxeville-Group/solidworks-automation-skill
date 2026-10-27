# Troubleshooting

## Connection issues

### Cannot connect to SolidWorks

```
Error: pywintypes.com_error: (-2147221005, 'Invalid class string', None, None)
```

**Cause**: SolidWorks is not installed, or COM is not registered.
**Resolution**: Confirm that SolidWorks is installed; try connecting with a version-specific identifier:
```python
sw = win32com.client.Dispatch("SldWorks.Application.32")  # SW 2024
```

### GetActiveObject fails

```
Error: pywintypes.com_error: (-2147221021, 'Operation unavailable', None, None)
```

**Cause**: SolidWorks is not running.
**Resolution**: Start SolidWorks manually first, or use `Dispatch` to start a new instance.

### Python 32/64-bit mismatch

**Cause**: Python and SolidWorks must use the same architecture (usually 64-bit).
**Resolution**: Install 64-bit Python.

## Type errors

### Apparently callable COM properties cause "Member not found"

Scenario: While traversing the feature tree or reading a model summary, pywin32 reports `callable=True` for members such as `FirstFeature`, `GetNextFeature`, or `GetTitle`, but calling them produces:

```text
(-2147352573, 'Member not found.', None, None)
```

Cause: Under dynamic dispatch, some SolidWorks COM members may appear as either properties or methods; `callable(member)` alone is not a reliable test.

Reliable approach: Prefer `sw_connect.get_com_member()` or `sw_assembly.safe_get_com_member()`.

```python
from sw_connect import get_com_member

feature = get_com_member(model, "FirstFeature")
while feature:
    print(get_com_member(feature, "Name"), get_com_member(feature, "GetTypeName2"))
    feature = get_com_member(feature, "GetNextFeature")
```

### Motion Study member reports "Member not found"

Scenario: `model.Extension.GetMotionStudyManager()` or `motion_mgr.CreateMotionStudy()` reports:

```text
(-2147352573, 'Member not found.', None, None)
```

Common causes:

1. The strongly typed Motion Study interfaces are in `swmotionstudy.tlb`, not the main `sldworks` type library.
2. Under pywin32 dynamic dispatch, `GetMotionStudyManager`, `CreateMotionStudy`, `Activate`, `Calculate`, and `Play` may appear as properties rather than methods.

Reliable approach: Prefer `sw_motion.py`.

```python
from sw_motion import create_motion_study, motion_member

study = create_motion_study(asm, name="Motion_60RPM", duration=4.0)
calculated = motion_member(study, "Calculate")
```

If low-level calls are necessary, load the type library first:

```python
from sw_motion import ensure_motion_type_library

ensure_motion_type_library(raise_on_error=True)
motion_mgr = asm.Extension.GetMotionStudyManager
study = motion_mgr.CreateMotionStudy
```

### SelectByID2 type mismatch

```
Error: TypeError: Objects of type 'NoneType' can not be converted to a COM VARIANT
```

**Resolution**: Use an explicit VARIANT for the Callout parameter:
```python
from win32com.client import VARIANT
import pythoncom
callout = VARIANT(pythoncom.VT_DISPATCH, None)
model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, callout, 0)
```

### By-reference parameter error

**Resolution**: Wrap output parameters in VARIANT objects:
```python
errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
```

### Pack and Go reports a missing parameter when obtaining the object

Scenario: `model.Extension.GetPackAndGo()` or strongly typed `IModelDocExtension.GetPackAndGo()` reports a required parameter missing, although the official API and Interop reflection both show a zero-argument method returning `IPackAndGo`.

Cause: On the local SW2024/2026 + pywin32 runtime, the object marshals `[out, retval] IPackAndGo**` incorrectly. Tests found that both the official zero-argument dynamic call and an explicit `VT_BYREF | VT_DISPATCH` argument can fail to return the pointer.

Reliable approach: Prefer `sw_delivery.pack_and_go()`. The wrapper first tries the official zero-argument pywin32 call; if pywin32 raises a signature error, it uses `comtypes` early binding to call native `IModelDocExtension.GetPackAndGo()` / `SavePackAndGo()`.

```python
from sw_delivery import pack_and_go

report = pack_and_go(assembly, r"E:\\delivery\\pack_and_go", flatten=True)
assert report["success"], report
```

### Pack and Go outputs only the top-level assembly

Scenario: `IModelDoc2.GetDependencies2()` returns the assembly's referenced `.SLDPRT` files, but `IPackAndGo.GetDocumentNames()` contains only the top-level `.SLDASM`, and the saved delivery package contains only that assembly file.

Resolution: Do not treat the enumeration before saving as the final output, and do not use `AddExternalDocuments` to supplement the assembly's native parts. `sw_delivery.pack_and_go()` first runs native `SavePackAndGo()`, then audits dependencies against the files actually written during this run. On SW2026 SP01.1, the basic two-part assembly produced the complete assembly and two parts in three consecutive runs. If written outputs still lack dependencies, the default policy creates an explicitly marked `pilot` staging package; strict policy returns `status=blocked` and `SW_PACK_AND_GO_DEPENDENCY_ENUMERATION_INCOMPLETE`. Both must preserve evidence of missing dependencies and undergo human review.

### STL export writes the current assembly instead of the target part

Scenario: `IModelDocExtension.SaveAs()` returns success, but the STL named after the target part is absent; instead, the directory contains
multiple files such as `PartName - AssemblyComponentName.STL`.

Cause: SW2024 STL export may read `ActiveDoc`; holding the target part's `IModelDoc2` alone does not guarantee
that the correct document is exported.

Resolution: Use `sw_export.batch_export_formats()`. Before exporting each format, it calls `ActivateDoc3()`
and strictly verifies the active document path. If the path differs, it stops rather than accepting the API's apparent success.

## Operation failures

### run_review captures only one part or subassembly

Scenario: The assembly's component count, visibility, and color readback are all correct, but images exported by `run_review()` show only one hub or small part, with the other geometry reduced to shadows or entirely invisible.

Common causes:

1. SolidWorks `SaveBMP()` uses the currently active graphics window, and the target `model` is not the active document.
2. After opening parts or subassemblies in a batch, the active document remains the last component opened.
3. Rule-based review checks only whether the preview is nonblank and cannot detect a screenshot of the wrong document.

Reliable approach: Use the updated `sw_review.save_preview()` / `run_review()`, which activates the target document by `GetTitle()` before capture. In a custom capture workflow, call `ActivateDoc3()` first, then `ClearSelection2(True)`, `ViewZoomtofit2()`, and `SaveBMP()`.

```python
errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
sw.ActivateDoc3(model.GetTitle(), False, 0, errors)
model.ClearSelection2(True)
model.ViewZoomtofit2()
model.SaveBMP(r"E:\review\assembly.bmp", 1600, 1000)
```

Always inspect the four views visually; `evaluation.status=pass` does not replace geometric judgment.

### Parts split from STEP all overlap at the assembly origin

Scenario: A colored STEP or assembly is split into separate STEP files, imported into SolidWorks as native parts, then placed in a new assembly. The component count is correct, but the preview shows only one wheel or a mass of overlapping shadows.

Cause: Some CAD exporters retain a body's original coordinates when exporting it separately. SolidWorks `AddComponent5(path, ..., x, y, z)` may place a component by its bounding-box center, so passing `(0,0,0)` centers and overlaps every part.

Reliable approach:

1. Record each body's global bounding-box center before export in the part export manifest.
2. Pass that center in meters when adding the component, rather than using `(0,0,0)` for every part.
3. After insertion, read `Transform2.ArrayData[9:12]` and `GetBox()` to verify that the assembly bounding box is close to the original machine's dimensions.
4. Recursively inspect components inside `.SLDASM` subassemblies; do not check only the top-level count.

```python
center_m = [value / 1000.0 for value in bbox_center_mm]
component = add_component(asm, native_path, x=center_m[0], y=center_m[1], z=center_m[2])
```

### GetModelDoc2 returns None

Scenario: A component visibly exists in the assembly, but `component.GetModelDoc2()` returns `None`, preventing subsequent access to planes, faces, or features.

Common causes:

1. The component is suppressed or lightweight.
2. Its referenced file is not loaded into memory.
3. The assembly has not resolved the newly inserted component yet.

Reliable approach: Resolve the component before reading its model; prefer `sw_assembly.get_component_model()`.

```python
from sw_assembly import get_component_model, resolve_component

resolve_component(component)  # Defaults to swComponentFullyResolved=2; falls back to swComponentResolved=3 on failure
part = get_component_model(component)
```

### AddComponent4 returns None

Scenario: With the Chinese-language SW2024 installation and pywin32, `asm.AddComponent4(path, "", x, y, z)` consistently returns `None` without an exception, preventing parts from being added to the assembly.

Reliable approach: Prefer `sw_assembly.add_component()`. The current wrapper checks the file path, calls `AddComponent5(path, 0, "", False, config, x, y, z)`, and falls back to `AddComponent4()` on failure. If the result is still empty, it silently opens the part, reactivates the assembly, and retries `AddComponent5()`.

```python
from sw_assembly import add_component, get_components

component = add_component(asm, r"E:\parts\probe_block.SLDPRT", x=0, y=0, z=0)
if component is None:
    raise RuntimeError("Failed to add component")
print(get_components(asm))
```

Regression verification in a real SolidWorks session:

```powershell
py -3.13 tests\solidworks_add_component_regression.py --output-dir C:\CADAutomationWorkbench\solidworks_add_component_regression
```

Pass criteria: `component_count >= 1`, nonempty `component_name`, successful `.SLDASM` save, and `review_evaluation.status` equal to `pass`, or at least `review_checks.expected_outputs_exist=true`.

### A created Mate does not appear as a real mate in the feature tree

Scenario: The script reports success, but SolidWorks has no Gear Mate / Concentric Mate, and dragging does not produce coupled movement.

Checks:

1. Does `AddMate5()` return `None`?
2. Does by-reference `ErrorStatus` contain a success code? `swAddMateError_NoError=1`; some versions also return 0 on success.
3. Does the selection set contain exactly two objects before creation?
4. Are the selected objects assembly-context entities, rather than entities from the part document?
5. Was the Mate added as a subfeature of `MateGroup`?

Reliable approach:

```python
from sw_assembly import add_mate5_checked, collect_mate_feature_summary

mate = add_mate5_checked(asm, 1, lock_rotation=False, name="shaft_concentric")
print(collect_mate_feature_summary(asm))
```

### AddMate5 returns a Mate but error_status=1

Scenario: `AddMate5()` returns a nonempty Mate and the mate appears in the SolidWorks feature tree, but the script reports failure:

```text
AddMate5 failed: type=1, error_status=1
```

Cause: In `swAddMateError_e`, `1=swAddMateError_NoError` denotes success, not an error. Do not accept only `0` as success.

Verification command:

```powershell
Add-Type -Path 'E:\Solidworks\SOLIDWORKS\SolidWorks.Interop.swconst.dll'
[int][SolidWorks.Interop.swconst.swAddMateError_e]::swAddMateError_NoError
```

Reliable approach: Use the updated `sw_assembly.add_mate5_checked()`, which accepts both `0` and `1` as success codes while still checking that the Mate is nonempty.

### The selection set is cleared

Scenario: The first face is selected successfully. After resolving a component or switching documents, the second face is selected successfully, but `AddMate5()` fails.

Cause: `SetSuppression2()`, document activation, and some rebuild operations clear or modify the selection set.

Reliable sequence:

1. Resolve every component participating in the Mate.
2. Map the entities into assembly context with `GetCorresponding()`.
3. Clear the selection set, then select both entities consecutively.
4. Call `AddMate5()` immediately.

```python
from sw_assembly import select_entities_for_mate

select_entities_for_mate(asm, entity_a, entity_b, mark=1)
```

### GetCorresponding returns None

Scenario: A plane or face exists in the part, but `component.GetCorresponding(face_or_feature)` returns `None`.

Common causes:

1. The supplied object does not belong to that component's referenced document.
2. The component is unresolved.
3. The wrong component instance was used; when a part is inserted multiple times, call `GetCorresponding()` on the intended instance.
4. The selected geometry is temporary or the object is stale.

Reliable approach: Find the feature or face in the model returned by `get_component_model(component)`, then map it through the same `component`.

### A part cannot rotate after a concentric Mate

The cause is usually a locked rotational degree of freedom, rather than a missing hinge:

1. `lock_rotation=True`, or Lock Rotation is enabled in the GUI.
2. Three coincident plane mates additionally constrain the rotating part completely.
3. The component itself is fixed.
4. Too many axial positioning mates overdefine the assembly.

For a moving assembly, the default concentric Mate setting should be:

```python
add_concentric_mate_by_cylinders(..., lock_rotation=False)
```

For a lid hinge, a concentric Mate can retain rotation, while one coincident plane or distance Mate limits axial movement.

### Feature creation fails (returns None)

Common causes:
1. **Incorrect entity selected** - Check the entity name and type passed to SelectByID2.
2. **Sketch is not fully defined** - Add sufficient relations and dimensions.
3. **Sketch has an open contour** - Extrusion requires a closed profile.
4. **Incorrect units** - The API uses meters, not millimeters.

### SelectByID2("SKETCH") consistently returns False

Scenario: In Chinese-language SolidWorks 2024, both `SelectByID2("\u8349\u56fe1", "SKETCH", ...)` (the localized Sketch1 alias) and `SelectByID2("Sketch1", "SKETCH", ...)` return `False`; `FeatureExtrusion3()` then returns `None`.

Root cause: Selecting sketches by name is unstable in some versions/locales. An older `sw_part._ensure_sketch_selected()` also treated any nonempty selection set as success, so the first few parts worked accidentally through residual selections, while all subsequent attempts failed after the selection set was cleared.

Reliable approach:

1. Prefer `with sketch(model, "...") as sketch_name:`; `sw_part.py` caches the actual sketch object reference during creation.
2. Do not rely on residual selections before feature creation; switching documents, rebuilding, resolving components, and failed API calls may all clear the selection set.
3. Prefer object-level `Select2()` on the Sketch Feature / Sketch; fall back to `SelectByID2("SKETCH")` only last.
4. For a custom low-level workflow, pass the return value of `end_sketch(model)` directly to `extrude_boss()` / `extrude_cut()`.

```python
from sw_part import end_sketch, extrude_boss, sketch_circle, start_sketch

start_sketch(model, "Front Plane")
sketch_circle(model, 0, 0, 0.025)
sketch_ref = end_sketch(model)
feature = extrude_boss(model, sketch_ref, 0.05)
if feature is None:
    raise RuntimeError("Extrusion failed: check sketch closure, direction, and object selection")
```

Regression verification in a real SolidWorks session:

```powershell
py -3.13 tests\solidworks_sketch_selection_regression.py --output-dir C:\CADAutomationWorkbench\solidworks_skill_regression
```

Pass criteria: The script reports `selection_count=0` after each of two `ClearSelection2(True)` calls, then still creates `Boss-Extrude1` and `Cut-Extrude1` (localized names may differ), saves `.SLDPRT`, exports `.step`, and returns `review_evaluation.status=pass`.

### Long FeatureCut4 argument lists are unstable

Scenario: A handwritten `FeatureCut4(...)` call returns `None`, although the same sketch cuts successfully through the GUI or wrapper.

Cause: `FeatureCut4` has many arguments. Any mismatch in end condition, direction reversal, `FlipSide`, `NormalCut`, or selection state can fail silently. Do not assemble the long argument list from memory.

Reliable approach:

1. Prefer `sw_part.extrude_cut()`.
2. If a low-level call is necessary, test directions and end conditions on a minimal cylinder or rectangle first.
3. Check the returned feature after every cut; do not continue saving delivery files after a failure.

```python
from sw_part import extrude_cut

feature = extrude_cut(model, sketch_name, 0, direction=True, flip=False)
if feature is None:
    feature = extrude_cut(model, sketch_name, 0, direction=True, flip=True)
if feature is None:
    raise RuntimeError("Cut failed: check sketch, direction, or end condition")
```

### Cutting a slot from a central plane splits the shaft

Scenario: A shaft needs an obround slot or keyway. The script sketches it on `Front Plane` and performs a blind cut, producing a large axial planar cut that looks like half the cylinder has been removed.

Cause: `Front Plane` often passes through the shaft axis rather than its outer surface. Cutting directly from the central plane produces a section cut instead of a surface recess.

Reliable approach: Create a tangent offset reference plane first, sketch the slot on that plane, and make a blind cut to the slot depth; see "Obround slot on a cylindrical surface" in `references/part-modeling.md`.

### The slot feature exists but is invisible in the preview

Scenario: The feature tree contains `Cut_*_Slot` and `run_review()` passes, but the slot is absent from the isometric or front view.

Checks:

1. Was the slot cut on the back side? Try reversing `flip` or exporting the opposite view.
2. Was the slot cut from a central plane and concealed by the current shading? Inspect top/right views.
3. Did the feature remove only invisible internal volume? Check a section view or adjust the tangent reference plane.
4. Does a selected reference plane in the preview obscure the slot profile?

Resolution: Do not rely solely on `feature is not None`. Export `isometric/front/top/right` and visually confirm that the critical geometry exists.

### Plane selection fails

**Cause**: Plane names differ between English and localized installations.
**Resolution**:
```python
# Try the English name
success = model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, None, 0)
if not success:
    # Try the legacy localized Front Plane name (Unicode escapes preserve compatibility)
    model.Extension.SelectByID2("\u524d\u89c6\u57fa\u51c6\u9762", "PLANE", 0, 0, 0, False, 0, None, 0)
```

### Save/export fails

Check the error codes:
```python
errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
success = model.Extension.SaveAs(path, 0, 1, None, errors, warnings)
print(f"Error code: {errors.value}, warning code: {warnings.value}")
# See the error-code table in references/export.md
```

### Opening STEP/IGES with OpenDoc6 crashes or shows a template dialog

Scenario: Opening `.step/.stp/.igs/.iges` with `OpenDoc6()` exits SolidWorks or disconnects RPC; or
`LoadFile4(path, "", importData, errors)` displays the "New SOLIDWORKS Document" template dialog and blocks.

Cause: Foreign files other than DXF/DWG and Pro/E should be imported into a new SolidWorks document through `LoadFile4`,
with `ArgString` set to `"r"`. In SW2024, an empty string may trigger the template selection UI and is unsuitable for automation.

Reliable approach: Prefer `sw_connect.open_document()` / `SolidWorksSession.open()`; for STEP/STP/IGES/IGS the wrapper
automatically calls `LoadFile4(file_path, "r", sw.GetImportFileData(file_path), errors)`.
Before import, it also calls `ensure_default_templates()` to set default part/assembly/drawing templates and enable
`swAlwaysUseDefaultTemplates=111`, avoiding the "New SOLIDWORKS Document" template window.

```python
from sw_session import SolidWorksSession

session = SolidWorksSession(version=2024, visible=True)
model = session.open(r"E:\parts\body.step", silent=True, raise_on_error=True)
session.save(model, r"E:\parts\body.SLDPRT")
```

Regression verification in a real SolidWorks session:

```powershell
py -3.13 tests\solidworks_loadfile4_import_regression.py --output-dir C:\CADAutomationWorkbench\solidworks_loadfile4_import_regression
```

Pass criteria: `status=pass`, `body_count >= 1`, a successful save of the imported `.SLDPRT`, and a four-view review report.

Note: The string preference enumerations for default template paths are `swDefaultTemplatePart=8`,
`swDefaultTemplateAssembly=9`, and `swDefaultTemplateDrawing=10`. Do not confuse them with file-location enumerations or old values,
or `NewDocument()` / `LoadFile4()` may still show a template dialog.

If a complete large STEP repeatedly causes `pywintypes.com_error: (-2147023170, 'The remote procedure call failed.')`,
do not keep retrying blindly in the same SolidWorks process. Save the logs, restart SolidWorks, then import smaller parts,
use Parasolid as an intermediate format, or have the user manually handle the template dialog. `ensure_default_templates()` reduces the likelihood of dialogs,
but cannot guarantee silent import for every local SW2024 template configuration.

### OpenDoc6 cannot open OBJ/STL, or LoadFile4 reports a type mismatch

Scenario: `OpenDoc6(path, swDocPART, ...)` cannot open a public mesh reference, vehicle exterior model, or test cube in `.obj/.stl` format,
returning error `2097152` (`swFileRequiresRepairError`). Switching to
`LoadFile4(path, "r", None, errors)` reports `com_error(-2147352571, 'Type mismatch.')`.

Cause: In some SolidWorks 2024 COM environments, OBJ/STL cannot be opened as an ordinary part document;
Python `None` is also invalid for the third `LoadFile4()` parameter. This does not necessarily mean the mesh is damaged: even
a simple 684-byte STL cube can reproduce the same failure.

Reliable approach: Prefer `scripts/sw_import_mesh_reference.py`, or use this minimal import:

```python
from sw_connect import connect_solidworks, create_empty_dispatch_variant, save_document
from win32com.client import VARIANT
import pythoncom

sw, _ = connect_solidworks(visible=True)
sw.SetUserPreferenceIntegerValue(208, 0)   # swImportStlVrmlModelType_Graphics
sw.SetUserPreferenceIntegerValue(210, 2)   # swMETER
sw.SetUserPreferenceToggle(303, True)      # swImportStlVrmlTextureInformation
sw.SetUserPreferenceToggle(679, True)      # swVrmlStlImportAsPSMesh

errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
model = sw.LoadFile4(
    r"E:\work\reference_scaled_m.obj",
    "r",
    create_empty_dispatch_variant(),
    errors,
)
assert model is not None, errors.value
save_document(model, r"E:\work\reference.SLDPRT")
```

Note: STEP/STP/IGES/IGS and OBJ/STL need different import-data arguments. Neutral CAD files continue to use
`sw.GetImportFileData(path)`; OBJ/STL mesh references use an empty Dispatch variant. Do not mix these approaches.

### SaveAs error code 1 or overwrite failure

Scenario: `session.save(model, path)` or `model.Extension.SaveAs(...)` fails with error code `1`, even though the target file exists and its path is correct.

Common cause: A same-named document is already open in the SolidWorks session, or the current SolidWorks process holds the target file, preventing overwrite.

Reliable approach:

```python
session = SolidWorksSession()
session.sw.CloseDoc("Drawing_Stepped_Shaft.SLDPRT")
model = session.new_part()
```

Note: Close only output documents that this script explicitly intends to overwrite. Do not blindly call `CloseAllDocuments()` unless the user authorizes clearing the entire session.

### A temporary SLDPRT cannot be deleted

Scenario: PowerShell `Remove-Item` reports:

```text
The process cannot access the file ... because it is being used by another process.
```

Cause: The debugging part remains open in SolidWorks.

Resolution sequence:

1. Close the corresponding document with `sw.CloseDoc("<filename>.SLDPRT")`.
2. Remove the temporary file with `Remove-Item -LiteralPath <path> -Force`.
3. Before deletion, verify that the path matches only the intended temporary file, for example `debug_*.SLDPRT`.

### Reference planes or sketches obscure preview images

Scenario: BMP images exported by `run_review()` show large orange reference planes, sketches, or selection highlights that hinder inspection of the solid geometry.

Reliable approach:

```python
for plane_name in created_plane_names:
    model.ClearSelection2(True)
    selected = model.Extension.SelectByID2(
        plane_name, "PLANE", 0, 0, 0, False, 0,
        create_empty_dispatch_variant(), 0,
    )
    if selected:
        model.BlankRefGeom()

model.BlankSketch()
model.ClearSelection2(True)
model.ForceRebuild3(False)
```

`BlankRefGeom()` usually requires selecting the reference geometry to hide first; calling it alone may not hide planes newly created by the script.

### A multicolor assembly appears almost entirely green

Scenario: The script assigns red, blue, silver, black, and other colors, but the assembly or BMP preview is almost entirely green.

There are usually two distinct causes; verify each separately:

1. Passing an ordinary Python `list` directly to `MaterialPropertyValues` causes COM array marshaling errors.
2. Components, faces, or edges remain selected before capture, so SolidWorks' green selection highlight overrides the actual appearance.

Reliable approach:

```python
from sw_appearance import set_component_appearance, verify_appearance

assert set_component_appearance(component, "signal_red")
assert verify_appearance(component, "signal_red")["ok"]

model.ClearSelection2(True)
model.GraphicsRedraw2()
```

Do not simply change the list to a tuple and keep trying. Consistently use `material_variant()` to generate
`VT_ARRAY | VT_R8`. Do not test the result with `bool(SetMaterialPropertyValues2(...))`,
because this method returns `void`. Verification command:

```powershell
python tests\solidworks_appearance_regression.py
```

### MathUtility.CreateTransform is unstable

Scenario: `sw.GetMathUtility().CreateTransform(data)` or `math_utility.CreateTransform()` raises a COM exception, returns an empty object, or moves a component without solving it.

Reliable approach: Read the component's existing `Transform2`, modify `ArrayData`, and call `SetTransformAndSolve2()`; on failure, fall back to `component.Transform2 = transform`.

```python
from sw_assembly import apply_component_transform_x
from sw_connect import deg

ok = apply_component_transform_x(component, 0.1, 0.0, 0.0, deg(30))
```

Note: Editing transforms directly is suitable for demonstration frames or placement. To make the assembly draggable in SolidWorks, real Mates must retain the required degrees of freedom.

### SolidWorks internal errors or slow COM calls

Scenario: After generating many parts/assemblies, `AddComponent4`, save, export, or feature operations fail intermittently.

Common causes: Too many open documents, accumulated graphics-window/feature-tree refresh work, or a long-running process.

Resolution sequence:

1. Save critical outputs.
2. Call `sw.CloseAllDocuments(False)` to clear the session.
3. Reopen the required parts in batches and assemble them.
4. If instability continues, obtain user confirmation before restarting `SLDWORKS.exe`.
5. Log the failing component and API in the script; do not merely print "Complete".

### FeatureFillet reports "Parameter not optional"

Scenario: `model.FeatureManager.FeatureFillet(195, radius, 0, 0, None, None, None)` reports

```text
com_error: (-2147352561, 'Parameter not optional.', None, None)
```

Cause: `IFeatureManager::FeatureFillet` **accepts only four parameters**: `(Options, Radius, R1, R2)`.
Passing seven parameters (appending three `None` values) fails on both SolidWorks 2024 and 2026. This incorrect call appears in older documentation and early
wrappers; testing on real installations confirmed the issue.

Reliable approach:

```python
from sw_edge_select import select_edges
from sw_part import fillet
from sw_connect import mm

# First create a nonempty edge selection set
selection = select_edges(model, {"axis": "z", "convex_only": True})
if selection["status"] != "ok":
    raise RuntimeError(f"No edges selected: {selection['errors']}")
feature = fillet(model, mm(4))
```

`sw_part.fillet()` raises `ValueError` when the selection set is empty instead of proceeding. With an empty selection,
SolidWorks may fillet the "current profile", creating an incorrect feature that is difficult to diagnose.

### Fillet/chamfer selects the wrong edges

Scenario: The script reports no error, but fillets are applied to unintended edges, or changing model dimensions changes every fillet location.

Cause: `SelectByID2("Edge1", "EDGE", x, y, z, ...)` relies on hardcoded entity coordinates that break when the model changes,
and failure is silent (`False` is returned, but the subsequent feature may not report an error).

Reliable approach: Use `sw_edge_select.select_edges()` to select edges by B-Rep geometry criteria. See
[references/edge-selection.md](edge-selection.md).

```python
from sw_edge_select import select_edges

# Preview the selected edges and the reason each excluded edge was rejected
preview = select_edges(model, {"axis": "z", "convex_only": True})
print(preview["selected_count"], preview["selected"])
print(preview["rejected_sample"])
```

### IEdge.Select4 reports "Type mismatch"

Scenario: `edge.Select4(True, None, False)` reports

```text
com_error: (-2147352571, 'Type mismatch.', None, None)
```

Cause: The second argument of `Select4(Append, Callout)` is a **Callout object** and must be a Dispatch VARIANT,
not Python `None`.

Reliable approach: Prefer `Select2(Append, Mark)`, which avoids this issue. If Select4 is required, pass
`create_empty_dispatch_variant()`.

```python
from sw_connect import create_empty_dispatch_variant

edge.Select2(True, 0)                                    # Preferred
edge.Select4(True, create_empty_dispatch_variant())      # Fallback
```

### A hole reports success but does not appear in the model

Scenario: `create_through_hole()` returns feature evidence, but the feature tree has no cut, or it reports
`SolidWorks did not create the feature`.

Check each item:

1. **Units**. `sw_hole_features` expects `center` / `diameter` / `depth` in **meters**.
   Passing millimeters (for example, 10 to mean 10 mm) makes a sketch 1000 times too large. The cut lies entirely outside the solid and is
   silently rejected. This caused a tested 100x60x6 mm plate to have a 13300 mm bounding box.
   ```python
   from sw_connect import mm
   create_through_hole(model, center=(mm(10), mm(10)), diameter=mm(6.6))
   ```
2. **Whether the hole location is inside the solid**. SolidWorks returns `None` without an error when the cut sketch is entirely outside the body.
   Use `build_from_spec.validate_holes_inside_base()` or check the boundaries yourself.
3. **Incorrect return-value key**. `HoleFeatureEvidence.to_dict()` contains `feature_names` (a tuple),
   not `status` / `feature_name`. Using `result.get("status")` incorrectly classifies a successful hole as a failure.

### Check feature return values for None, not truthiness

Most SolidWorks feature APIs return `None` on failure. **Do not** merely use `if feature:` and continue saving,
or ignore the return value. Check after every feature creation, and abort or degrade the operation on failure:

```python
feature = extrude_boss(model, sketch_ref, mm(8))
if feature is None:
    raise RuntimeError("Extrusion failed: check sketch closure, direction, and nonzero depth")
```

### Bounding-box dimensions are 1000 or 0.001 times the expected size

Scenario: The return value of `model.GetPartBox(True)` is incorrectly interpreted in millimeters or meters.

Cause: `GetPartBox` has two modes with different units:

| Call | Return units |
|---|---|
| `GetPartBox(True)` | **Meters** (system units) |
| `GetPartBox(False)` | **Millimeters** (document units; depends on the document's unit system) |

`sw_measure.collect_bounding_box()` consistently uses `True` and converts to millimeters; use the wrapper directly.

```python
from sw_measure import collect_bounding_box
box = collect_bounding_box(model)
print(box["size_mm"])   # [length, width, height], in millimeters
```

### Mass properties report "No material assigned"

Scenario: `collect_mass_properties()` includes "No material assigned to document" in `warnings`.

Cause: SolidWorks uses the default density (1000 kg/m³) for documents without an assigned material. It can produce numeric values,
but these **cannot be used directly for engineering decisions** (motor sizing, shipping weight, and cost estimates will be inaccurate).

Resolution: Assign a material in the document, or explicitly override density:

```python
result = collect_mass_properties(model, density_kg_m3=7850.0)   # Grade 45 steel
```

Also, `IMassProperty.Status` is unavailable in some versions (tested on SW2024 SP5); a returned `status: null`
is normal and does not affect mass values.

### An MCP call remains unresponsive

Scenario: Any SolidWorks MCP tool call never returns, and all subsequent tool calls also hang.

Cause: When SolidWorks displays a modal dialog (template selection, license notice, or overwrite confirmation), it stops responding to
Automation calls without timing out. The previous operation holding the lock consequently stalls.

Resolution:

1. Call `solidworks_recover` to diagnose the issue. It enumerates SolidWorks windows and reports detected modal dialogs
   and the operation currently holding the lock.
2. Switch to the SolidWorks window and close the dialog **manually**. For automatic dismissal, pass
   `{"dismiss_dialogs": true}`; note that `WM_CLOSE` can discard unsaved changes, so automatic dismissal is disabled by default.
3. If the window is completely unresponsive, end `SLDWORKS.exe` in Task Manager, then call `solidworks_connect`.

The lock timeout limit is 300 seconds; after that, the tool returns a structured error instead of blocking forever.

## Calling unwrapped APIs

When a task requires a SolidWorks API that this skill has not yet wrapped:

1. Consult official SolidWorks API documentation or the local SDK documentation to confirm the interface signature and enumerations.
2. Validate the interface with a minimal script before embedding it in a large task.
3. Check COM return values for `None` / `False`, and print error/warning codes.
4. Add the reliable implementation to `scripts/` and document the pitfall here or in the relevant `references/*.md`.

Documentation template:

```text
### <API or error symptom>

Scenario:
Error/symptom:
Cause:
Reliable approach:
  # Minimal runnable example
Verification:
```

## Performance optimization

### Large assembly operations are slow

```python
# Enable background processing mode
model.FeatureManager.EnableFeatureTree = False
model.ActiveView.EnableGraphicsUpdate = False

# ... Perform operations ...

# Restore and refresh
model.FeatureManager.EnableFeatureTree = True
model.ActiveView.EnableGraphicsUpdate = True
model.GraphicsRedraw2()
```

### Optimizing batch operations

```python
# Disable automatic rebuild
sw.UserControl = False

# Perform batch operations...

# Rebuild manually
model.EditRebuild3()
sw.UserControl = True
```

## Version mapping

| SolidWorks | Revision number | ProgID |
|---|---|---|
| 2020 | 28 | SldWorks.Application.28 |
| 2021 | 29 | SldWorks.Application.29 |
| 2022 | 30 | SldWorks.Application.30 |
| 2023 | 31 | SldWorks.Application.31 |
| 2024 | 32 | SldWorks.Application.32 |
| 2025 | 33 | SldWorks.Application.33 |
| 2026 | 34 | SldWorks.Application.34 |

Formula: `revision number = (year - 2000) + 8`

## License and add-in boundaries

A successful connection to base SolidWorks COM does not establish that Simulation, Routing, Motion, or mold add-ins have usable licenses. Capability probes must separately record add-in registration, load state, and the result of a minimal real operation. When legitimate authorization is missing, return `blocked` with the specific dependency; do not misreport a licensing issue as an ordinary script failure.

This project does not patch licenses, bypass activation, modify licensing services, or fabricate capabilities for unauthorized installations. Legal headless backends such as OCP, CalculiX, and ezdxf can still perform tasks within the scope of open formats.
