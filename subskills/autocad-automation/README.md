# AutoCAD Automation Subskill

> Headless DXF preview and structural review are available. The AutoCAD 2024 .NET allowlisted backend has repeatedly passed real DWG/PDF/PNG output, reopen, entity/layer/dimension regressions; the runtime marks it `verified` after revalidating the latest three evidence runs. Native ActiveX/COM writes remain gated by live testing and must not be advertised as stable.

This AutoCAD / DWG / DXF subskill belongs to the `solidworks-automation-skill` repository. The parent handles SOLIDWORKS 3D modeling, assemblies, drawings and exports. This subskill handles Python COM automation of Windows desktop AutoCAD: 2D drafting, batch edits, layers/text/dimensions, DWG/DXF/PDF export, line-art vectorization and drawing checks.

## When to use

- Requests for DWG / DXF / AutoCAD drawings.
- Convert raster line art into CAD entities and save DWG/DXF.
- Batch-check layers, entity counts, bounding boxes, text, blocks, external references or output files.
- Draw visibly, step by step in AutoCAD and export native previews for review.
- Supplement a SOLIDWORKS workflow with 2D drawings, machining profiles, laser-cut DXF or drawing cleanup.

## Relationship to the parent skill

- `solidworks-automation`: SOLIDWORKS COM connection, parts/assemblies/drawings, STEP/STL/PDF export and 3D review.
- `autocad-automation`: AutoCAD COM connection, 2D DWG/DXF drafting, layers/dimensions/blocks, native previews and drawing checks.

Use the parent for native SOLIDWORKS parts, assemblies and drawings. Read this subskill when the task explicitly involves AutoCAD, DWG, DXF, 2D CAD, line-art conversion or batch DWG edits.

## Quick commands

Check and regression-test the AutoCAD .NET backend:

```powershell
python subskills\autocad-automation\scripts\acad_dotnet_preflight.py
python subskills\autocad-automation\scripts\acad_dotnet_regression.py --real-cad
```

The regression script starts only its own AutoCAD Core Console and executes only the fixed `CADSTUDIOPROBE` and `CADSTUDIOCREATE` commands. Desktop deployments require a trusted path or signed plug-in package, not an arbitrary-code execution endpoint.

```powershell
python subskills\autocad-automation\scripts\acad_preflight.py --launch
```

```powershell
python subskills\autocad-automation\scripts\acad_draw.py `
  --input C:\temp\plan.json `
  --output C:\temp\result.dwg `
  --new
```

```powershell
python subskills\autocad-automation\scripts\acad_review.py C:\temp\result.dwg `
  --launch `
  --json C:\temp\review.json
```

```powershell
python subskills\autocad-automation\scripts\acad_preview.py `
  --source C:\temp\result.dwg `
  --output C:\temp\preview.png `
  --launch
```

## Line-art conversion rules

Final delivery for ordinary image-to-CAD tracing must contain only vectorized source lines. Remove manually guessed outlines, facial ellipses, logo triangles, wave lines, replacement text and in-drawing review notes from the final DWG/DXF.

Confirm these auxiliary layers have zero entities at final review:

```text
PORTRAIT_OUTLINE, BODY_OUTLINE, JERSEY_OUTLINE,
OUTER_GUIDE, CONSTRUCTION, FACE_FEATURES,
LOGO_GEOMETRY, WATER_SPLASH, JERSEY_STRIPE,
TEXT_LOGO, TEXT_BRAND, REVIEW_NOTES
```

This rule comes from a real demo review: AI-added outlines, ellipses, triangles and colored waves intended to improve recognition became unwanted CAD entities. Ordinary tracing jobs prioritize clean, faithful geometry without extra entities.

## References

- `SKILL.md`: agent entrypoint and complete workflow.
- `references/api-lookup.md`: AutoCAD API verification route.
- `references/engineering-patterns.md`: layers, units, blocks, dimensions and batch-processing lessons.
- `references/troubleshooting.md`: local COM, DXF/BMP export, contaminated line art and review pitfalls.
