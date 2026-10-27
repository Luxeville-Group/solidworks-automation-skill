# SolidWorks Engineering Drawing

Engineering-drawing generation and manufacturing-delivery review. The root solidworks-automation, VibeCAD,
hole/CNC subskills or engineering orchestrator can call it on demand; other modeling subskills do not need reverse dependencies.

## Live example

<p align="center">
  <!-- The upstream demonstration includes unsupported-language UI; the verified workflow is described below. -->
</p>

In SOLIDWORKS 2026 SP01.1, the example reads NIST's public-domain Additive Manufacturing Test Artifact Ver3B, checks its bounding box and produces a GB/T first-angle A1 drawing. Delivery includes:

- Native SLDPRT and SLDDRW.
- Three orthographic views, an isometric view and A-A section.
- Ten required dimensions plus hole-position/datum requirements.
- PDF, BMP preview, drawing_evidence.json and drawing_review_report.json.
- Seventy targeted drawing tests passed; extracted PDF text bounds in the experimental output had zero overlaps.

This demonstrates code-driven SOLIDWORKS → native drawing → structured evidence, not unattended manufacturing release. Border, dimension chain, hole schedule and manufacturing semantics still require an engineer's visual review.

## Inputs

Describe these through schemas/drawing_spec.schema.json:

- Source .sldprt / .sldasm / sheet-metal model.
- GB/T or ISO standard, sheet size and projection.
- Views, scale, sections and details.
- Required dimensions and hole/slot specifications, quantities and positions.
- Title block, technical requirements, BOM and deliverables.

## Outputs

- `.slddrw`
- PDF
- BMP/PNG previews.
- `drawing_evidence.json`
- `drawing_review_report.json`
- Markdown review summary.

## Compatibility entrypoints

Legacy callers can still use root paths:

```python
from scripts.sw_drawing import plan_standard_view_layout
```

## Cross-version native matrix

```powershell
$env:CAD_STUDIO_VISIBLE='false'
python tests/solidworks_drawing_version_matrix.py --years 2024 2025 2026
```

The matrix serializes exact version ProgIDs and writes per-version drawing reports plus aggregate JSON. Unregistered versions are unavailable; pass requires the read-back year to match the requested year.

New code should prefer this subskill's scripts through the root COM/session API.

## Status

Currently pilot. Delivery must associate each COM dimension position with actual vector text bounds in the SOLIDWORKS-exported PDF.
Complete, collision-free associations permit pass. Missing PDF/PyMuPDF, incomplete matching or overlaps prevent release.
