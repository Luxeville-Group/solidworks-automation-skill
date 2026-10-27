# AutoCAD Automation Troubleshooting

## Python dependencies

Symptom: `ModuleNotFoundError: No module named 'win32com'`.

Resolution:

```powershell
python -m pip install pywin32
python -m pywin32_postinstall -install
```

With multiple Python installations, install using the same interpreter that runs the scripts.

## AutoCAD COM unavailable

Symptom: `Invalid class string`, `Operation unavailable` or failed `AutoCAD.Application` creation.

Resolution:

1. Confirm Windows desktop AutoCAD is installed.
2. Start AutoCAD manually once to complete COM registration and first-run setup.
3. Check for a noninteractive service session, a remote session without a GUI or restricted permissions.
4. With multiple versions, try default `AutoCAD.Application` first; inspect the registry for a version-specific ProgID when necessary.

## AutoCAD is open without an active document

Symptom: connection succeeds but `ActiveDocument` fails.

Resolution: create a drawing with `Documents.Add()` or explicitly open the target DWG.

## Layers / ModelSpace fail after document creation

Symptom: accessing `Layers` on the `Documents.Add()` result raises `AttributeError: Add.Layers`.

Resolution: in AutoCAD 2024 with pywin32 dynamic proxies, the returned object may not be a stable `AcadDocument` proxy. Rebind after `Documents.Add()`:

```python
app.Documents.Add()
doc = app.ActiveDocument
```

`scripts/acad_session.py::new_document()` implements this approach.

## SendCommand has no effect

Common causes:

- Missing final newline.
- Asynchronous execution followed by a save before the command completes.
- Localized command names.
- A command waiting for user input.

Recommendations:

- Prefer the COM object model.
- Prefix commands with `_.`, for example `_.ZOOM _E`.
- Supply every parameter and newline explicitly.
- Wait after submission and verify with `acad_review.py`.

## Save failures or overwrite risks

Resolution:

- Use absolute output paths.
- Create the destination directory before saving.
- Save a copy before modifying an existing DWG.
- Close other programs holding the file open.
- Record save failures and stop derivative exports.

## DXF export failure

Symptom: `Document.SaveAs("xxx.dxf")` fails or returns an unreadable COM error.

Resolution: do not infer DXF solely from the SaveAs extension. Use `Document.Export(fileBase, "DXF", selectionSet)`. ActiveX Export requires a SelectionSet even for the whole drawing; a temporary empty set can be used. `scripts/acad_session.py::export_dxf()` wraps this workflow.

## Unexpected outlines, ellipses, triangles or colored lines in traced artwork

Symptoms:

- The user points out unexplained shapes around or within the traced image.
- Large arcs/polylines surround a portrait, ellipses cross the face, triangles appear around logos or colored waves appear at splashes.
- Review finds non-source layers such as `PORTRAIT_OUTLINE`, `BODY_OUTLINE`, `JERSEY_OUTLINE`, `FACE_FEATURES`, `LOGO_GEOMETRY`, `WATER_SPLASH`, `JERSEY_STRIPE`, `TEXT_LOGO`, `TEXT_BRAND` and `REVIEW_NOTES`.

Causes:

- The script manually added outlines, facial details, logos, splashes or replacement text to increase resemblance.
- CAD users interpret those additions as actual drawing objects or erroneous construction lines.
- Embedded review notes and scores also contaminate final ModelSpace.

Resolution:

1. Ordinary image-to-CAD delivery contains only vectorized source lines, such as `TRACE_DARK` and `TRACE_LIGHT`.
2. Remove or disable manually enhanced/construction layers; verbal explanations alone are insufficient.
3. Put review notes, scores and generation parameters in JSON/Markdown reports, not final ModelSpace.
4. Include disallowed layers in the review and require zero entity counts:

```python
aux_layers = [
    "PORTRAIT_OUTLINE", "BODY_OUTLINE", "JERSEY_OUTLINE",
    "OUTER_GUIDE", "CONSTRUCTION", "FACE_FEATURES",
    "LOGO_GEOMETRY", "WATER_SPLASH", "JERSEY_STRIPE",
    "TEXT_LOGO", "TEXT_BRAND", "REVIEW_NOTES",
]
assert all(layer_counts.get(name, 0) == 0 for name in aux_layers)
```

5. Explicitly requested enhancement/reconstruction belongs on separate layers; explain that these are manually enhanced layers that can be hidden.

Lessons:

- Recognizability does not authorize guessed geometry. Tracing prioritizes clean, faithful results without extra entities.
- Colored helper layers, waves, replacement text and construction geometry can reduce trust even when a numerical score improves.
- Final review must also check for absence of extra helper layers, embedded review text and non-source decoration.

## Transient COM rejection or unreadable errors

Symptoms:

- `pywintypes.com_error: (-2147418111, ...)` during batch line/layer creation, possibly with unreadable text.
- Intermittent failures in `Layers.Item()`, `Layers.Add()` or `ModelSpace.AddLine()` that disappear on retry.

Causes:

- Desktop AutoCAD COM is a single-threaded, interactive automation target and may be busy drawing, regenerating, opening or exporting.
- Concurrent access to one instance worsens this instability.

Resolution:

1. Serialize AutoCAD COM operations; do not run review, preview and drawing concurrently.
2. Use bounded retries/backoff for frequent calls, especially layers, AddLine, SelectionSets, Export and SaveAs.
3. Wait 1–2 seconds after opening/creating a document, then rebind `app.ActiveDocument`.
4. When creating many entities, call Regen/live_update every few hundred entities without refreshing excessively.

Example:

```python
for attempt in range(12):
    try:
        ent = model.AddLine(p0, p1)
        break
    except Exception:
        if attempt == 11:
            raise
        time.sleep(0.08 + attempt * 0.04)
```

## ModelSpace cannot be enumerated directly

Symptom: `for entity in session.model` raises `TypeError: This object does not support enumeration`.

Cause: some AutoCAD/pywin32 dynamic proxies do not expose Python iteration but still support Count and Item(index).

Resolution: use Count/Item(i) in the review script:

```python
ms = doc.ModelSpace
for i in range(int(ms.Count)):
    entity = ms.Item(i)
```

## SaveAs cannot overwrite an open DWG

Symptom: generation succeeds but SaveAs(target) reports a document-save error; the target already exists or is open in AutoCAD.

Resolution:

1. Do not force-overwrite an old file the user has open.
2. Use a new versioned/semantic filename, such as `_approved` or `_trace_only`.
3. Confirm saved file existence/size before DXF or preview export.

## SelectionSets or Export proxy errors

Symptoms:

- `doc.SelectionSets.Add(name)` raises `AttributeError: <unknown>.Add`.
- `doc.Export(...)` raises `AttributeError: Open.Export` or another misbound-proxy error.
- DXF/BMP export fails independently after DWG was saved.

Cause:

- AutoCAD is busy, the active-document proxy is misbound, or dynamic COM binding has not stabilized after opening a read-only drawing.

Resolution:

1. Serialize operations; do not run acad_review.py and acad_preview.py simultaneously.
2. Wait after opening the source, then reacquire `app.ActiveDocument`.
3. Remove stale same-name SelectionSets before creation and retry failures.
4. If BMP export fails while DWG/DXF and entity checks pass, clearly report native preview export failure and the completed evidence; never fabricate a screenshot.

## Occluded or black window screenshots

Symptom: an OS screenshot succeeds but captures another foreground window or a small black image.

Resolution:

1. Window screenshots establish current desktop visibility, not drawing correctness.
2. Prefer native `scripts/acad_preview.py` export via `Document.Export(..., "BMP", selectionSet)`.
3. Run Regen and ZoomExtents first; inspect the exported image for border, views, text, dimensions and overlaps.
4. If an OS screenshot is still needed, first ensure AutoCAD is unobscured. Occluded screenshots cannot establish a pass.

## Drawing progress is invisible

Symptom: the DWG is generated but the user cannot see AutoCAD open or the step-by-step drawing.

Resolution:

1. Use the default acad_draw.py mode without `--fast`.
2. Ensure `live_preview` remains `true`, its default.
3. Use `AutoCADSession.activate_window()` to bring AutoCAD forward where possible, then `live_update()` after each step.
4. Other windows may still steal focus; use the native AutoCAD preview for final review.

## SelectionSet name conflict

Symptom: selection-set creation reports that the name already exists.

Resolution: enumerate doc.SelectionSets, delete the same-name set, then create it.

## Bounding-box read failure

Some empty/proxy/other objects do not support GetBoundingBox. Skip them and record errors without failing the entire review.

## Unstable PDF / Plot output

PDF output depends on the printer, PC3, PageSetup, CTB/STB and background plotting configuration:

- Prefer an existing template's PageSetup.
- Disable background plotting or wait for Plot completion.
- Check the output PDF size.
- Before important delivery, visually inspect the PDF border, orientation, scale and lineweights.

## An exited job instance is still reported as running

Symptom: drawings, DWG/DXF and previews exist and acad.exe is gone, but the regression report says the job-owned AutoCAD instance did not exit in time.

Cause: Quit and TerminateProcess may return before Windows finishes asynchronous process teardown. A single check or short wait can mistake propagation delay for a surviving process.

Resolution:

1. Record only a PID started by DispatchEx and resolved from the AutoCAD window handle. Never Quit or terminate a pre-existing user instance.
2. Request Quit and wait for that exact PID. On timeout, terminate only the recorded job PID, wait again and recheck.
3. Preserve owned_process_id, quit_requested, forced_termination_used, process_exit_confirmed and cleanup errors; command-line exception handling must not replace original cleanup evidence.
4. If still failing, inspect `Get-Process acad -ErrorAction SilentlyContinue` and the recorded PID. Never terminate all user AutoCAD instances by process name.
