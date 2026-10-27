# SolidWorks API Verification Workflow

When a task needs a SolidWorks API not yet wrapped in `scripts/`, verify it before implementing it. Do not reconstruct long argument lists, enum values or return semantics from memory.

## Preferred sources

1. Official web documentation: `https://help.solidworks.com`
   - Suggested search terms:
     - `site:help.solidworks.com SolidWorks API Help <InterfaceName> <MethodName>`
     - `site:help.solidworks.com <MethodName> Method (SOLIDWORKS API Help)`
     - `site:help.solidworks.com swSaveAsOptions_e`
2. Local SDK / API Help:
   - Common locations under the SolidWorks installation: `api`, `api\help`, `api\redist`
   - Common interop libraries: `SolidWorks.Interop.sldworks.dll`, `SolidWorks.Interop.swconst.dll`
3. This repository's wrappers and experience:
   - Search `scripts/*.py` first.
   - Then consult `references/*.md`.
   - Write a new minimal verification script only afterward.

## API categories requiring verification

- `IModelDocExtension.SaveAs*`, `OpenDoc*`, `CloseDoc` and export APIs
- `SelectByID2`, selection marks, selection-type strings and append-selection behavior
- Long-argument methods such as `FeatureManager.FeatureExtrusion*`, `FeatureCut*`, sweeps, lofts, fillets and chamfers
- `IAssemblyDoc.AddComponent*`, `AddMate*`, component transforms and lightweight/suppressed states
- Moving assemblies: verify `IAssemblyDoc.AddMate5`, `IComponent2.GetModelDoc2`, `IComponent2.GetCorresponding`, `IComponent2.SetSuppression2`, `ISurface.IsCylinder`, `ISurface.CylinderParams` and `IComponent2.SetTransformAndSolve2`.
- Motion Study: verify `IModelDocExtension.GetMotionStudyManager`, `IMotionStudyManager.CreateMotionStudy`, `IMotionStudy.CreateDefinition`, `IMotionStudy.CreateFeature`, `ISimulationMotorFeatureData.ConstantSpeedMotor` and `ISimulationMotorFeatureData.LoadReferences`.
- Appearance/material: `MaterialPropertyValues`, `IMaterialVisualPropertiesData`, component-level appearance and display states
- Drawings: view creation, BOM, dimensions, printing/export to PDF
- Interfaces requiring `VARIANT`, by-reference arguments, enums or bitmasks

## Verification record template

Keep a minimal record in the task script or commit description for future reuse:

```text
API:
Source:
Version:
Signature:
Key parameters:
Enums/constants:
Return value:
Failure symptoms:
Verification script:
Added to scripts/references:
```

## Motion-assembly API notes

- `AddMate5`: confirm the 15-argument signature; final `ErrorStatus` is a by-reference integer. Gear Mate uses `GearRatioNumerator` / `GearRatioDenominator`; moving concentric mates require `LockRotation=False`.
- `GetModelDoc2`: official documentation states that suppressed, lightweight or unloaded components may not return a model. Resolve components before automation.
- `GetCorresponding`: maps an object in a part document to assembly context. When a part has multiple instances, call it on the intended component instance.
- `IsCylinder` / `CylinderParams`: identify cylindrical faces of shafts, holes and gears. `CylinderParams[6]` is the radius in meters.
- `SetTransformAndSolve2`: drives component position and updates the assembly solver. If unstable, reuse the component's existing `Transform2` and modify `ArrayData`.
- `swmotionstudy.tlb`: strongly typed Motion Study interfaces are in a separate type library; pywin32 requires `pythoncom.LoadTypeLib(...)` + `win32com.client.gencache.EnsureModule(...)`.
- `swFmAEMRotationalMotor`: verified locally as `78` in SW 2024's `swFeatureNameID_e`; use `CreateDefinition(78)` for rotational-motor FeatureData.
- `ISimulationMotorFeatureData.ConstantSpeedMotor(60.0)`: the argument is RPM, not rad/s.
- `swAddMateError_e`: `swAddMateError_NoError=1`; do not treat `AddMate5`'s by-reference `ErrorStatus=1` as failure.

Command for local enum cross-checking:

```powershell
Add-Type -Path 'E:\Solidworks\SOLIDWORKS\SolidWorks.Interop.swconst.dll'
[int][SolidWorks.Interop.swconst.swMateType_e]::swMateGEAR
[int][SolidWorks.Interop.swconst.swMateType_e]::swMateHINGE
[int][SolidWorks.Interop.swconst.swFeatureNameID_e]::swFmAEMRotationalMotor
[int][SolidWorks.Interop.swconst.swAddMateError_e]::swAddMateError_NoError
[enum]::GetValues([SolidWorks.Interop.swconst.swComponentSuppressionState_e])
```

## Minimal verification-script requirements

1. Connect separately to SolidWorks and print `sw.RevisionNumber()` and the current document type.
2. Verify one new API at a time instead of mixing it directly into a large task.
3. Check every COM call for `None`, `False`, error codes and warning codes.
4. Produce an openable `.SLDPRT`, `.SLDASM`, `.SLDDRW` or exported file.
5. Run `sw_review.py` or visually inspect screenshots to verify the actual model, drawing or assembly.

## Retaining verified knowledge

- When an API is needed a second time, prefer wrapping it in `scripts/`.
- Record compatibility problems, error codes, localized-name differences and selection-mark pitfalls in the relevant `references/*.md`.
- Wrappers should hide COM's long argument lists behind stable, readable Python APIs with explicit unit conventions.
- Documentation examples must use code that has actually run; do not publish unverified guesses.
