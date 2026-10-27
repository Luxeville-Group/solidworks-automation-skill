# Controlling SolidWorks with OpenClaw

This guide is for agents invoking the skill through OpenClaw. Reuse existing `scripts/` wrappers reliably instead of rewriting COM automation each time.

## Preflight

1. Windows is required.
2. SolidWorks must be installed; preferably launch it manually once to verify COM. If not detected, stop and tell the user to install it manually.
3. `python` or `py` must be executable on PATH.
4. `pywin32` / `comtypes` must be installed. Run the preflight first:

```bash
python {baseDir}/scripts/sw_preflight.py
```

Preflight rules:

- If `comtypes`, `win32com` or `pythoncom` is missing, ask whether the user authorizes installing the missing local Python COM dependencies [Y/N].
- After authorization, run `python -m pip install "pywin32>=305" "comtypes>=1.2.0"`.
- If declined, stop and provide the manual installation command.

5. Install the skill in one of:

```text
~/.openclaw/skills/solidworks-automation/
~/.agents/skills/solidworks-automation/
```

## Recommended execution

1. Establish SolidWorks version, UI language, intermediate/output paths, units and target formats.
2. Run `sw_preflight.py`, then prefer `scripts/sw_connect.py`, `scripts/sw_part.py`, `scripts/sw_assembly.py`, `scripts/sw_drawing.py` and `scripts/sw_export.py`.
3. If model-generated VBA is required, use `scripts/sw_macro_guard.py` for model routing, output validation, retries and template fallback.
4. Divide work into connection, open/new, modeling/assembly, save, export and screenshot/preview review.
5. Check every return value; never assume COM calls succeed.
6. After export/save, check that the actual destination file exists.
7. Export at least one isometric preview after creation/modification; if desktop capture is available, also review the current SolidWorks window.

## Minimal imports

When executing Python in OpenClaw, prefer `{baseDir}` for the skill root:

```python
import sys
sys.path.insert(0, r"{baseDir}/scripts")

from sw_connect import connect_solidworks, mm, deg, new_document, open_document, save_document
from sw_preflight import run_preflight
from sw_part import start_sketch, end_sketch, sketch_rectangle, sketch_circle, extrude_boss, extrude_cut
from sw_export import export_to_step, export_to_stl, export_to_pdf
from sw_review import run_review

run_preflight()
```

## Multimodel VBA safeguards

When GPT, Kimi or Claude generates VBA, do not pass raw model output directly to SolidWorks. Use `sw_macro_guard.py`:

```python
from sw_macro_guard import build_prompt, generate_macro_with_guard, validate_vba_macro

prompt = build_prompt("Draw a 50 mm cylinder", model_name="kimi")
```

Execution conventions:

1. Use concise prompts for GPT models.
2. Kimi, Claude and unknown models receive stronger formatting constraints.
3. Validate with `validate_vba_macro()` before execution, checking `SldWorks`, `ModelDoc2`, `Sub`, `End Sub`.
4. Retry parsing failures `1~2` times with stronger formatting instructions.
5. If retries fail, use local templates selected by keywords such as cube, cylinder, extrusion or sketch.

## Suggested prompts

Examples that directly trigger the skill in OpenClaw:

- Create a 120x80x10 mm mounting plate with a phi6 hole at each corner, save to `C:\\temp\\plate.sldprt` and export STEP.
- Open `C:\\parts\\gearbox.sldasm`, check interference and report the result.
- Export `C:\\parts\\bracket.sldprt` to STL and STEP in `C:\\output\\`.

## Execution notes

- SolidWorks API lengths are meters; convert all millimeter inputs with `mm()` first.
- `start_sketch()` includes localized-plane fallbacks. Prefer `"Front Plane"`, `"Top Plane"` and `"Right Plane"`.
- Before manipulating features, faces or edges, establish entity name/type, then call `SelectByID2`.
- Save large tasks as `.sldprt`, `.sldasm` or `.slddrw` first; export other formats last.

## Self-check checklist

After execution, check at least:

1. `connect_solidworks()` returned a valid `sw` object.
2. New/opened `model` is not `None`.
3. Feature functions such as `extrude_boss()` returned feature objects.
4. Save/export functions reported success.
5. Target files actually exist on disk.
6. `run_review()` exported previews and wrote `*_review_report.json`.
7. Previews match the request without blank output, wrong scale, missing parts, incorrect orientation, overlap or floating components.

## Review example

```python
model.ForceRebuild3(False)
report, report_path = run_review(model, r"C:\temp\review", basename="result")
print(report_path)
print(report["evaluation"])
```

If the preview is wrong, correct and regenerate the script output before reporting completion; saving alone is insufficient.
