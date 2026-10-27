# Drawing Review Reference

Drawing review has three layers:

1. Structural evidence: sheet, border, projection, views, scale, dimensions, tables and outputs.
2. Manufacturing evidence: dimension chains, hole/slot specifications/counts/positions, title block, BOM and sheet-metal flat pattern.
3. Visual evidence: inspected BMP/PNG and PDF vector-text collision risks.

Missing evidence in any layer prevents unattended delivery. Confirmed collisions are fail; estimated/PDF text
risks are warning; missing key specifications or flat-pattern evidence are blocked / review_required.

Structured verification:

- Match dimension IDs exactly, then verify view, type, value/text, tolerance and datum. D1 must not match D10.
- Match each hole's specification, quantity and location. Thread requirements need dedicated thread/hole-callout evidence, not matching numbers or a plain-hole diameter.
- Accept only swTableAnnotation_BillOfMaterials with nonempty data rows; requested configuration must match exactly.
- A candidate title-block template does not verify field contents; unreadable fields remain review_required.
- Every requested standard/isometric/section/detail view must appear in the structural evidence.
- Professional annotations must be actual IView center marks, centerlines, datums, GTOL, surface-finish or weld entities. Hole callouts require IDisplayDimension.IsHoleCallout; ordinary notes with matching text are insufficient.
- Traverse annotation center marks through IView.GetFirstCenterMark2 and ICenterMark.GetNext. GetCenterMarks is a legacy fallback and does not alone cover every type.
- Match professionalAnnotations by view, type, count and text. Datum labels are exact: A must not match AB.
