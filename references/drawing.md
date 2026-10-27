# Drawing API Reference

## Creating views

### Three standard views

```python
drawing.Create3rdAngleViews2(partPath)  # Third-angle projection
drawing.CreateFirstAngleViews2(partPath) # First-angle projection
```

### Custom views

```python
view = drawing.CreateDrawViewFromModelView3(
    ModelName,     # str: part/assembly path
    ViewName,      # str: view orientation (table below)
    X, Y, Z        # float: placement coordinates (meters)
)
```

View orientation names:
| Name | Description |
|---|---|
| `*Front` | Front |
| `*Back` | Back |
| `*Top` | Top |
| `*Bottom` | Bottom |
| `*Left` | Left |
| `*Right` | Right |
| `*Isometric` | Isometric |
| `*Trimetric` | Trimetric |
| `*Dimetric` | Dimetric |

### Setting view scale

```python
view.ScaleRatio = (1.0, 2.0)  # Scale 1:2
view.ScaleRatio = (2.0, 1.0)  # Scale 2:1
```

## Dimensions

### Automatic dimensions (Model Items)

```python
drawing.InsertModelAnnotations3(
    InsertType,    # int: 0=entire model
    AnnotationType, # int: 32768=model dimensions marked for drawings
    DuplicateDims, # bool
    AutoArrange,   # bool
    UseDoc,        # bool
    UseView        # bool
)
```

> SW2024/2026 dynamic pywin32 proxies commonly expose `InsertModelAnnotations3` on the drawing's
> `IModelDoc2`, not `IModelDocExtension`. The skill tries the document object first,
> then supports the older Extension proxy. `32` means geometric tolerances; `32768` means model dimensions
> marked for drawings. A `False` return or
> failure to read back dimension entities must not be reported as verified dimension evidence.
>
> This API imports only existing model `DisplayDimension` entities. For rectangles without sketch dimensions
> or parts containing only extrusion parameters, call `sw_part.auto_dimension_sketch()` in sketch edit mode first,
> or create dimensions through explicit parametric modeling. The drawing API cannot invent missing model dimensions.
>
> The capability registry records this path separately as `drawing_dimension_insertion=verified` (SW2024/2026).
> Three consecutive SW2026 SP01.1 runs read back three real views and six real dimension entities.
> Complete drawing delivery remains `drawings_and_bom=pilot` because dimension layout, hole/slot location chains,
> borders, title blocks and BOMs require human visual review.

### SW2026 dimension-text boundary evidence

Reflection against the local `SolidWorks.Interop.sldworks.dll` confirms:

- `IAnnotation.GetPosition()` returns the annotation anchor.
- `IAnnotation.GetTextFormat(index)` / `GetTextFormatCount()` return text formatting.
- `ITextFormat.CharHeight`, `WidthFactor` and `CharSpacingFactor` expose font dimensions.
- `IDisplayDimension.GetText(swDimensionTextParts_e)` reads user text fragments.
- `IAnnotation` has no native dimension-text bounding-box API; do not call or claim `GetBox()` exists.

Therefore `scripts/sw_drawing.py::estimate_dimension_text_box()` produces only conservative estimated bounds:

1. Center on `IAnnotation.GetPosition()`.
2. Estimate unrotated width/height from character count, `CharHeight`, `WidthFactor` and `CharSpacingFactor`.
3. Because the API supplies no dimension-text angle, use the rectangle diagonal to construct a square envelope covering any rotation.
4. Use padding `max(1 mm, 0.4 * CharHeight)`; missing fields receive conservative defaults and reduced confidence.
5. `GetText(0)` may omit the formatted main dimension value in SW2026; conservatively reserve eight monospaced characters when absent.

Reports must retain these fields; estimates must not be presented as native evidence:

```json
{
  "box_source": "estimated",
  "box_confidence": "low | medium | unavailable",
  "box_evidence": {
    "native_bounding_box_available": false,
    "method": "annotation_position_text_format_arbitrary_rotation_envelope",
    "padding_m": 0.001,
    "orientation_assumption": "unknown_angle_conservative_square_envelope"
  }
}
```

Even when no estimated boundaries collide, `review_drawing_layout()` still returns
`review_required / DRAWING_LAYOUT_ESTIMATED_EVIDENCE_REQUIRES_VISUAL_REVIEW`.
Overlapping estimates produce `DRAWING_LAYOUT_ESTIMATED_COLLISION_RISK`; findings must have
`evidence_source=estimated` and `confirmed_collision=false`. Only native boundary evidence can use
`DRAWING_LAYOUT_COLLISION_DETECTED` to indicate a confirmed collision.
A nonempty BMP/PDF establishes a usable preview, not absence of overlapping dimensions; final visual review remains required.

A stronger non-COM approach exports PDF through SolidWorks' official interface, then uses
`sw_review.inspect_pdf_text_layout()` to read real vector-text span bounds. This can
detect actual overlap between extractable text spans more reliably than character-width estimates, without OCR. It still cannot
prove absence of collisions with dimension lines, geometry or outlined fonts. Intentional title-block overlays, such as a sheet label
plus page number, may also intersect, so results flag overlap risk rather than automatically declaring a visual defect.
Install PyMuPDF if missing:

```powershell
python -m pip install -r requirements-pdf.txt
```

If installed in a custom directory, point `CADSTUDIO_PYMUPDF_PATH` to that directory.

Drawing boundary evidence therefore ranks as PDF vector-text bounds > conservative COM anchor/font estimates > OCR.
Retain a final PDF/BMP visual review before delivery.

### Adding dimensions manually

```python
# Select two entities first.
drawing.Extension.SelectByID2("Edge1@View1", "EDGE", 0, 0, 0, False, 0, None, 0)
drawing.Extension.SelectByID2("Edge2@View1", "EDGE", 0, 0, 0, True, 0, None, 0)
# Add a dimension.
drawing.AddDimension2(x, y, 0)  # Dimension placement
```

## Notes and annotations

```python
# Add a note.
note = drawing.InsertNote(text)

# Add a surface-finish symbol.
drawing.InsertSurfaceFinishSymbol3(...)

# Add a weld symbol.
drawing.InsertWeldSymbol(...)

# Add a datum symbol.
drawing.InsertDatumTag2(...)
```

## BOM tables

```python
bom = drawing.InsertBomTable4(
    TemplateName,  # str: BOM template path (.sldbomtbt)
    X, Y,          # float: position
    BomType,       # int: 1=top-level, 2=parts-only, 3=indented
    Configuration, # str: configuration name
    TableAnchor,   # str: anchor name
    Hidden         # bool: include hidden components
)
```

## Sheet operations

```python
# Get the current sheet.
sheet = drawing.GetCurrentSheet()

# Get all sheet names.
names = drawing.GetSheetNames()

# Activate a sheet.
drawing.ActivateSheet(sheetName)

# Add a new sheet.
drawing.NewSheet4(
    Name,        # str: sheet name
    PaperSize,   # int: paper size (5=A4, 6=A3, 7=A2, 8=A1, 9=A0)
    TemplateIn,  # int: 12=custom
    Scale1,      # float: scale numerator
    Scale2,      # float: scale denominator
    FirstAngle,  # bool: first-angle projection
    Template,    # str: sheet-format path
    W, H,        # float: width and height
    PropertySheet, # str
    Zone_LeftMargin, Zone_RightMargin, Zone_TopMargin, Zone_BottomMargin,
    Zone_Col, Zone_Row  # int: zones
)

# Set sheet format.
sheet.SetTemplateName(formatPath)  # .slddrt path
```

## Exporting PDF

```python
sw = model.GetSldWorksObject()
pdf_data = sw.GetExportFileData(1)  # swExportPDFData
sheet_names = drawing.GetSheetNames()
pdf_data.SetSheets(0, sheet_names)  # 0=specified sheets

errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
model.Extension.SaveAs("output.pdf", 0, 1, pdf_data, errors, warnings)
```
