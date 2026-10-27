# AutoCAD API Verification

## Official source priority

1. Autodesk AutoCAD API overview: ObjectARX, Managed .NET, Visual LISP and ActiveX programming environments.
   - https://aps.autodesk.com/developer/overview/autocad-api
2. AutoCAD Developer and ObjectARX Help: Managed .NET, ActiveX/VBA, DXF Reference, AutoLISP and Core Console.
   - https://help.autodesk.com/view/OARX/2027/ENU/
3. Managed .NET Developer's Guide: C# plug-ins, transactions, document locks, entities, dimensions, layouts and plotting.
   - https://help.autodesk.com/view/OARX/2027/ENU/?guid=GUID-C3F3C736-40CF-44A0-9210-55F6A939B6F2
4. ObjectARX SDK: advanced C++/C# extensions, database structures, graphics systems and native commands.
   - https://aps.autodesk.com/developer/overview/objectarx-autocad-sdk
5. APS Design Automation: cloud DWG batch processing without a desktop.
   - https://aps.autodesk.com/en/docs/design-automation/v3

## GitHub references

- ADN-DevTech `acad-api-skill`: rules for agents generating AutoCAD/Civil 3D/Plant 3D .NET plug-ins.
  - https://github.com/ADN-DevTech/acad-api-skill
- ADN-DevTech `autocad-automation-apps`: AutoLISP, C++ CRX and .NET bundle examples for APS Design Automation.
  - https://github.com/ADN-DevTech/autocad-automation-apps
- `reclosedev/pyautocad`: Python ActiveX wrappers; useful patterns for coordinates, iteration and lightweight API design.
  - https://github.com/reclosedev/pyautocad
- AutoCAD .NET Wizards: Visual Studio AutoCAD .NET project templates.
  - https://github.com/ADN-DevTech/AutoCAD-Net-Wizards

## Verification workflow

1. Choose the route: COM/ActiveX, AutoLISP/SCR, .NET, ObjectARX or APS.
2. Search exact object/method names, such as `ModelSpace AddLine ActiveX AutoCAD` or `DocumentLock AutoCAD .NET`.
3. Read target-version documentation; record signatures, types, units, returns, exceptions and version limits.
4. Prefer Autodesk/ADN official GitHub examples. Adapt third-party patterns after review rather than copying directly.
5. Verify with a minimal runnable script, save outputs and review using `acad_review.py`.
6. When documentation and observed behavior differ, record the local version, language, error code and solution in `troubleshooting.md`.

## Common COM/ActiveX objects

- `AutoCAD.Application`: entrypoint; exposes `Visible`, `Documents` and `ActiveDocument`.
- `Document`: drawing; includes `ModelSpace`, `PaperSpace`, `Layers`, `Blocks`, `SelectionSets`, `SaveAs` and `SendCommand`.
- `ModelSpace`: creates geometry such as lines, circles, polylines, text and dimensions.
- `Layer`: layer colors, linetypes and visibility.
- `AcadEntity`: common entity interface with `Layer`, `Color`; most objects support `GetBoundingBox`.

## Method verification checklist

- Line: `ModelSpace.AddLine(startPoint, endPoint)`
- Circle: `ModelSpace.AddCircle(centerPoint, radius)`
- Lightweight polyline: `ModelSpace.AddLightWeightPolyline(points2d)`
- Text: `ModelSpace.AddText(text, insertionPoint, height)`
- Multiline text: `ModelSpace.AddMText(insertionPoint, width, text)`
- Save: `Document.SaveAs(path)`
- Command: `Document.SendCommand(command)`
- View: `Application.ZoomExtents()`

Behavior can differ across AutoCAD versions, language packs and LT/full editions. Do not promise advanced objects or export formats before live verification.

## .NET plug-in route

Switch to .NET when COM scripts become difficult to maintain, or when transactions, document locks, selection filters, command registration, panels or event handlers are needed:

1. Match the .NET target framework and SDK references to the AutoCAD version.
2. Use `CommandMethod` for command entrypoints.
3. Put database edits in transactions and lock active documents correctly.
4. Load the DLL through `NETLOAD` or a debugging configuration.
5. After the plug-in works, consider packaging a bundle or APS Design Automation activity.

## Source-use rules

- Verify enums, save types, Plot settings and command parameters rather than relying on memory.
- Use forum answers to locate keywords and symptoms, not as the final authority.
- Check licenses before copying GitHub code into a user project.
- Distinguish cloud APS workflows from local AutoCAD COM. Local COM scripts are not automatically runnable in CI.
