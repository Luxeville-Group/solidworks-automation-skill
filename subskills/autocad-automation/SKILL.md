---
name: autocad-automation
description: "Automate local Windows AutoCAD through Python COM/ActiveX: 2D DWG/DXF drafting, layers/text/dimensions/blocks, exports, batch edits and drawing review. Use AutoLISP/SCR or .NET when COM is insufficient; applies to AutoCAD, DWG/DXF, ObjectARX and CAD tool integration."
metadata: { "os": ["win32"], "requires": { "anyBins": ["python", "py"], "pythonPackages": ["pywin32"] } }
---

# AutoCAD Automation

> This directory is the AutoCAD/DWG subskill of solidworks-automation-skill. The parent handles SOLIDWORKS modeling, assemblies, drawings and 3D exports. This subskill handles 2D DWG/DXF drafting, batch changes, vectorization, previews and drawing checks. Return to the parent for native SOLIDWORKS parts/assemblies.

## Goal

Control local Windows desktop AutoCAD through verified wrappers rather than improvised commands. Python COM/ActiveX is the default route, but native writes require capabilities.yaml approval and local live regression. AutoCAD 2024 Documents/Layers/SelectionSets dynamic proxies are currently unstable, so COM-native DWG drafting is treated as `not_implemented`. Headless DXF reading, previews and structural review are available. The AutoCAD 2024 .NET allowlisted backend has repeatedly passed native DWG save/reopen, PDF/PNG and entity/layer/dimension regressions; complete runtime evidence permits `verified`. Only fixed commands are allowed, not arbitrary code execution.

## When to use

Use this skill for:

- Creating/modifying DWG/DXF: lines, circles, arcs, polylines, rectangles, text, blocks, layers and simple dimensions.
- Batch-opening DWG to inspect layers, entity counts, text, block references, external references or outputs.
- Connecting Codex to local AutoCAD, saving DWG, exporting DXF/PDF and producing review reports.
- Writing AutoLISP, .scr command scripts or C# AutoCAD .NET plug-ins.
- Looking up Autodesk APIs, ADN/GitHub examples, ObjectARX SDK or APS Design Automation patterns.

For rendering-only imagery, BIM/Revit, mechanical STEP-first modeling, CAM toolpaths or engineering certification, use the corresponding CAD/BIM/simulation/manufacturing workflow instead.

## Defaults

- Operating system: Windows.
- AutoCAD: locally installed, preferably started manually once for COM registration.
- Automation entrypoint: `AutoCAD.Application` COM ProgID.
- Visibility: new drawing jobs show/activate AutoCAD and draw incrementally; disable this only for batch work or requested speed.
- Units: assume millimeters unless specified. AutoCAD database coordinates are unitless numbers, so record the intended units in the drawing notes.
- Space: geometry goes to ModelSpace; layouts, title blocks and plotting are separate.
- Coordinates: WCS by default; 2D objects use `Z=0`.
- Outputs: prefer DWG, with requested DXF/PDF exports; use absolute paths.
- File handling: save a copy before modifying an existing DWG unless overwriting is explicitly authorized.

Briefly confirm missing version, units, standards, output paths or overwrite permission. Simple sketches may assume millimeters, ModelSpace and a new DWG, with those assumptions reported.

## Preflight

Run before AutoCAD automation:

```powershell
python subskills\autocad-automation\scripts\acad_preflight.py
```

If automatic AutoCAD startup is authorized:

```powershell
python subskills\autocad-automation\scripts\acad_preflight.py --launch
```

On preflight failure:

- Missing pywin32: explain `python -m pip install pywin32` and install only with authorization.
- Missing AutoCAD COM: check installation, first startup and LT/restricted-environment status.
- AutoCAD running without a document: create a document rather than classifying it as a connection failure.

## Core workflow

1. **Classify:** new drawing, existing-DWG edit, batch processing, export, API/plug-in development or troubleshooting.
2. **Confirm constraints:** units, version, target file, formats, overwrite permission, layer/linetype/dimension standards and company template.
3. **Preflight:** verify Python COM and AutoCAD with acad_preflight.py.
4. **Verify APIs:** read references/api-lookup.md before unwrapped APIs, then Autodesk documentation or trusted examples. Verify long signatures, enums and command behavior.
5. **Plan:** specify layers, coordinate datums, objects, dimensions, text, outputs and checks.
6. **Start the application:** connect/start AutoCAD, make it visible and bring it forward where possible before drawing.
7. **Reuse scripts:** simple geometry uses acad_draw.py JSON input; complex logic composes acad_session.py COM wrappers.
8. **Serialize COM:** one script connects, draws, saves, reviews and exits; desktop COM calls must not run concurrently.
9. **Save/export:** create output directories and retain backups/copies of edited originals.
10. **Review:** acad_review.py checks entities, layers, bounding boxes and files; acad_preview.py exports native BMP/PNG for visual review. Window screenshots may supplement this, but occluded screenshots cannot establish success.
    For read-only headless DXF checks, use acad_headless.py first. It does not write DWG; native DWG/PDF still require a supported AutoCAD execution route.
11. **Capture lessons:** record new pitfalls, command/version differences and stable wrappers in troubleshooting references or scripts.

### Mechanical drawings and openings for 3D-printed parts

Requests for manufacturing drawings, GB/T conventions, strict mechanical drafting or 3D-print openings require manufacturing documentation:

1. Prefer the user's/company template. Where GB/T conventions are requested without a template, include A3/A4 sheet, binding margin, lower-right title block, FangSong lettering where applicable and separate thick/thin/center/hidden/dimension/text/opening layers. State that the drawing follows GB/T style and still needs company review.
2. Every cut, hole, slot, interface, water port, screw hole and boss needs both specification and location. Counts/sizes such as `4×Ø3.4`, `7×4×30` or `2×Ø13.5` without datum offsets, center distances, pitch or elevation are incomplete.
3. Use hole/slot tables when features are dense or leaders would cross views. Include location, specification, quantity and positioning; use view dimensions for key datums, center distances and overall dimensions.
4. Leaders cannot replace dimension chains or cross views, centerlines, hole outlines or dimension text. Move/split views or use tables when necessary.
5. Printed enclosure drawings need wall/base thickness, overall dimensions, interface sizes/centers, mounting-hole pitch and water-port/vent positions.
6. Prefer actual dimension entities such as AcDbRotatedDimension; manually drawn lines are not equivalent.
7. Export and visually review missing dimensions, overlapping text, lines crossing geometry, cross-view leaders, unreadable tables and title-block intrusion. Repair before reporting completion.

## Direct drafting from Codex

For simple jobs, generate drawing JSON and run:

```powershell
python subskills\autocad-automation\scripts\acad_draw.py `
  --input C:\temp\plate_plan.json `
  --output C:\temp\plate.dwg `
  --new
```

This entrypoint defaults to visible incremental drawing. Add `--fast` only for batches, slow playback or an explicit speed request:

```powershell
python subskills\autocad-automation\scripts\acad_draw.py `
  --input C:\temp\batch_plan.json `
  --output C:\temp\batch.dwg `
  --new `
  --fast
```

Example JSON:

```json
{
  "units": "mm",
  "live_preview": true,
  "live_zoom_every": 6,
  "layers": [
    {"name": "OUTLINE", "color": 7},
    {"name": "CENTER", "color": 1},
    {"name": "TEXT", "color": 3}
  ],
  "entities": [
    {"type": "rectangle", "origin": [0, 0], "width": 120, "height": 80, "layer": "OUTLINE"},
    {"type": "circle", "center": [20, 20, 0], "radius": 4.5, "layer": "CENTER"},
    {"type": "text", "text": "MOUNTING PLATE", "point": [8, 88, 0], "height": 5, "layer": "TEXT"}
  ]
}
```

For complex jobs, use Python:

```python
import sys
sys.path.insert(0, r"subskills\autocad-automation\scripts")
from acad_session import AutoCADSession

session = AutoCADSession(create_if_missing=True, visible=True).connect()
session.new_document()
session.activate_window()
session.create_layer("OUTLINE", color=7)
session.add_rectangle((0, 0), width=120, height=80, layer="OUTLINE")
session.live_update(step_delay_s=0.15, zoom=True)
session.save_as(r"C:\temp\plate.dwg")
```

## Choosing a technical route

| Need | Preferred route | Notes |
|---|---|---|
| Quick drafting, edits and batch checks | Python COM/ActiveX | Default route, callable from Codex shell; subject to capability gates |
| Existing AutoCAD commands/workflows | SendCommand / .scr / AutoLISP | Commands may be asynchronous; save and review |
| Many database transactions, selection filters, plug-in menus | AutoCAD .NET | C# plug-ins with transactions/document locks per the official guide |
| High-performance native extensions, deep database/graphics work | ObjectARX C++ | Higher cost and strong version coupling; justify the need |
| Cloud DWG batches | APS Design Automation | Suitable for headless production/CI; requires Autodesk APS credentials |

## Engineering rules

- Create layers before entities, use ACI colors and avoid putting everything on layer 0.
- Declare units and scale; ModelSpace is 1:1 and Layout/Plot determines print scale.
- Put coordinates, dimensions, text heights and diameters in named parameters rather than scattered literals.
- Readable geometry is not necessarily manufacturable. Holes/slots need verifiable datums and complete positioning; use tables when views are crowded.
- Ordinary image-to-CAD tracing follows source lines. Do not guess large arcs, polylines, ellipses, triangles, colored waves or replacement text for portraits, faces, logos, clothing or splashes.
- Before final save/preview/scoring, remove or hide construction/enhancement layers such as BODY_OUTLINE, JERSEY_OUTLINE, PORTRAIT_OUTLINE, OUTER_GUIDE, CONSTRUCTION, FACE_FEATURES, LOGO_GEOMETRY, WATER_SPLASH, JERSEY_STRIPE, TEXT_LOGO and TEXT_BRAND. Verify invisibility and zero remaining entities where removal is required.
- Retain manual enhancements only when explicitly requested. Explain that they are added geometry, place them on separate layers and make hiding them straightforward.
- Put review notes, scores and generation parameters in JSON/Markdown, not visible final ModelSpace text unless requested.
- Check COM objects and saved/exported file existence and size.
- Prefer object-model methods; use SendCommand as a fallback with `_.COMMAND` syntax to reduce locale dependence.
- If live drawing is requested, show AutoCAD and draw incrementally.
- Remove a stale same-name SelectionSet before creating one.
- Isolate each batch DWG in try/finally and record filename, error and failed stage.
- Open originals read-only or save copies by default; explicit authorization is required to overwrite.
- MCP exposes allowlisted drawing/export/review tools rather than arbitrary Python/VBA/AutoLISP execution.

## GitHub and official documentation

Preferred sources:

- Autodesk AutoCAD API overview, ActiveX/VBA, Managed .NET, ObjectARX and APS documentation.
- ADN-DevTech / Autodesk Platform Services GitHub examples.
- Established projects such as pyautocad for coordinate/iteration/COM patterns, with license review before copying.
- Forums/blogs/Stack Overflow as troubleshooting leads; verify key APIs against official documentation.

Resolve conflicts using target-version official documentation and local observed results.

## Progressive references

Read only the references relevant to the task:

- references/api-lookup.md: official sources, examples and API verification.
- references/engineering-patterns.md: drafting, layers, units, blocks, dimensions and batch practices.
- references/troubleshooting.md: COM sessions, SendCommand, saves/exports and version issues.

## Acceptance and reporting

The final response after AutoCAD operations includes:

- Assumptions: units, version, template and new versus edited drawing.
- Absolute paths for DWG/DXF/PDF/JSON reports and BMP/PNG previews.
- Actual checks: preflight, entities, layers, bounds, save/export and native-preview review. For traced images, confirm absence of extra outlines, internal helper geometry, colored decoration and embedded review text. For window screenshots, state whether they were unobscured.
- Outstanding human checks: borders, printer, company standard, lineweights, fonts, scale and professional drawing review.
