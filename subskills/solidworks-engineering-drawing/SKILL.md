---
name: solidworks-engineering-drawing
description: "Generate SOLIDWORKS engineering drawings and review manufacturing deliveries: GB/T first-angle part/assembly drawings, dimension chains, hole tables, BOM, PDF/BMP evidence and sheet-metal capability gates."
metadata: { "openclaw": { "os": ["win32"], "requires": { "anyBins": ["python", "py"] } } }
---

# SOLIDWORKS Drawing Generation and Review

This subskill covers 2D engineering drawings. It depends on the root solidworks-automation skill for COM
sessions, models, exports and general geometry evidence; it owns DrawingSpec v1, drawing workflows and manufacturing-delivery review.

## When to invoke

- Generate part or assembly drawings.
- Create GB/T borders, first-angle layouts, dimension chains, hole tables, BOM or title blocks.
- Review view overlaps, dimension/PDF text, title-block intrusion and delivery evidence.
- Review sheet-metal flat-pattern evidence.

## Defaults

- standard=GB_T defaults to projection=first_angle.
- DrawingSpec preflight blocks GB/T with third-angle projection.
- Every hole, slot and interface needs specification, quantity and location.
- Delivery requires PDF export and one-to-one associations between COM dimension positions and final PDF vector text boxes. Missing PDF/parser, incomplete matching or text collisions block release or require review.
- This subskill neither implements reinforcement learning nor exposes arbitrary Python/VBA execution.

## Workflow

1. Read and validate schemas/drawing_spec.schema.json.
2. Run root SOLIDWORKS preflight and capability probing.
3. Choose the border/template, create sheets and read back sheet size/projection.
4. Create supported views, dimensions, hole tables and BOMs; read back real entities. DrawingSpec fields must not be silently ignored.
5. Save .slddrw and export PDF plus BMP/PNG.
6. Run drawing_review.py to produce machine evidence and human-review gates.

## Capability boundaries

- Part/assembly drawings remain pilot while cross-version native regressions continue. Passing PDF text bounds, view boundaries, dimension chains, hole-table and BOM evidence permits pass; missing native COM text boxes alone do not automatically downgrade a result.
- The generic MCP generator currently supports front/top/right views with empty configuration, explicit fitting scale, model-dimension import, notes and template BOMs. Isometric/section/detail views, specified-ID dimensions, hole callouts/tables, business title-block fields and sheet-metal options must return DRAWING_SPEC_CAPABILITY_UNSUPPORTED before editing; dedicated scripts handle them.
- Review verifies dimension ID/view/type/value, hole specification/count/position, real BOM type/rows/configuration and title-block field read-back. Template candidates, arbitrary tables and fuzzy substring matches cannot establish a pass.
- professionalAnnotations can request center marks/lines, hole callouts, datums, GD&T, surface finish and weld symbols. Only dedicated SOLIDWORKS entity read-back counts; ordinary Note text cannot substitute.
- Generic centerMarks creation requires id, standard view, expected total and targets (holes/fillets/slots), verified through GetFirstCenterMark2/GetNext. SW2026 native testing found insertion must follow the new drawing's first save: before that, API True may have no readable entity and the wrapper retains failure. Other professional annotations remain capability-blocked.
- Run `python tests/solidworks_drawing_version_matrix.py --years 2024 2025 2026` for exact registered ProgIDs, verifying actual years. Missing versions are unavailable; default-ProgID results cannot substitute.
- Continue sheet-metal drawings only with reliable local flat-pattern evidence; otherwise return blocked rather than unattended completion.
- Full GD&T semantic solving is outside this version; checks establish presence and traceability only.

## Root dependencies

Reuse scripts/sw_connect.py, scripts/sw_session.py, scripts/sw_export.py,
scripts/sw_review.py, scripts/sw_document_data.py and scripts/sw_capability_probe.py.
