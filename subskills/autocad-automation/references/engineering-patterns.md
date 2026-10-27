# AutoCAD Engineering Practices

## Plan before drawing

- Write a one-page brief: units, scale, origin, layers, linetypes, text height, dimension style, output path and acceptance criteria.
- For mechanical/building/electrical drawings, confirm standards and company templates. Without a template, use neutral layers and do not claim compliance.
- ModelSpace uses real dimensions at 1:1; Layout handles borders, viewports and print scale.
- Choose the origin for later positioning: often bottom-left or center for parts, project datum for layouts.

## Layers and objects

- Create layers first; distinguish at least `OUTLINE`, `CENTER`, `HIDDEN`, `DIM`, `TEXT` and `CONSTRUCTION`.
- Put temporary construction lines on `CONSTRUCTION`; remove or freeze them as required before completion.
- Use blocks for repeated components, stable block names and uppercase English attribute names to avoid locale problems.
- Explicitly check external references, fonts, linetypes and plot styles during batch delivery.

## Dimensions and annotations

- Derive dimensions, text and lineweights from the drawing standard. Without one, add necessary notes without presenting the result as a final construction drawing.
- Dimension styles may depend on templates; confirm `DIMSTYLE` before creating dimensions through COM.
- Choose text height for the print scale; fixed heights in model space may become unreadable when printed.
- Establish datums first, then overall dimensions, positions and hole/slot specifications. A specification is not a locating dimension.
- Holes and slots need specification, position and quantity: display holes need diameter and datum offsets; screw holes need diameter and pitch; connector openings need width/height and center elevation; water ports need diameter, lateral position and both center heights.
- Prefer hole/slot schedules for dense features. Each entry must refer back to view datums; counts or “see drawing” alone are insufficient.
- Leaders provide short notes, not key dimensions. Keep them clear of other views, holes, centerlines, dimension text and title blocks.

## GB/T mechanical drawing conventions

When Chinese national/GB/T conventions or strict compliance with those conventions are requested, check at least:

- Sheet/frame: commonly A3 landscape `420×297`, a `25` binding margin, other margins `5`, and a bottom-right title block commonly `180` wide.
- Fonts/text: GB/T Chinese lettering commonly uses FangSong; keep technical notes, title blocks, view names and feature tables consistent with the selected standard.
- Layers/linetypes: distinguish thick/thin continuous, center, hidden, dimensions, text, frame and cutting/section lines. Center/hidden lines must not become ordinary solid lines.
- Dimensions: use real AutoCAD entities such as `AcDbRotatedDimension`, not loose lines and text assembled to resemble dimensions.
- Openings in printed enclosures: dimension the overall form, wall/base thickness, display/connector/water openings, vents and screw holes/bosses.
- Layout review: dimensions, text and tables must avoid the title block and main views. Move views or split tables when space is insufficient.

Examples of unacceptable results:

- `4× screw boss Ø8, pilot Ø2.6` without boss center spacing and edge distances is insufficient for manufacturing.
- `7×4×30 grille` without group center, first-slot position or pitch cannot be located.
- `2× water-port through-hole Ø13.5` without lateral positions and both center elevations cannot locate the holes.
- A long leader crossing centerlines, hole outlines or other views looks like construction-line contamination; replace it with dimensions or a feature table.

## Automation coding

- Centralize dimensional parameters at the script top or in a JSON brief.
- Check returned objects after COM calls and file existence/size after save/export.
- Prefer the object model; use `SendCommand` for missing object-model functionality, existing commands or legacy compatibility.
- `SendCommand` may be asynchronous: wait, save and review, rather than treating submission as completion.
- SelectionSet names persist in drawings; delete an existing same-name set before creating one.
- Record failed files and stages so one bad drawing does not abort an entire batch.

## Review approach

Minimum checks:

- Files exist and have plausible sizes.
- Entity counts/types match the brief.
- Layers contain the intended objects.
- Overall bounding-box scale matches expected dimensions.
- The main geometry is visible after AutoCAD `ZoomExtents`.

Higher-risk checks:

- Missing text, block attributes, external references, linetypes or fonts.
- Consistency of DXF/PDF with DWG.
- Correct frame scale, printer, CTB/STB, page orientation and margins.
- Whether batch edits overwrote user originals.

## Practical judgment

- Make drafting automation reproducible before polishing its appearance.
- DWG is a rich database, not a picture; screenshots alone do not verify attributes, layers or block references.
- Prefer .NET for complex plug-ins rather than hundreds of business-logic lines inside `SendCommand`.
- Version upgrades affect .NET targets, ObjectARX SDK and plug-in loading; live-test each major version.
- AutoCAD LT, educational/network licensing and noninteractive sessions may constrain automation; verify the environment when failures occur.
