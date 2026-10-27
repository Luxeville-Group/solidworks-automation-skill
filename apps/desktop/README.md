# CAD Automation Delivery Workbench desktop prototype

This is the first local desktop prototype of `solidworks-automation-skill`.

The current version demonstrates the user workflow:

```text
Create project -> Enter parameters -> Save JSON -> Run mock -> Generate review report and delivery directory
```

Real SolidWorks / AutoCAD automation is intended to use the same execution pipeline in later versions. This legacy prototype generates mock files; the React/Tauri application is described in [the workbench README](../workbench-ui/README.md).

The interface uses Turkish labels with English CAD terminology. See `DESIGN.md` for the visual rules: an engineering-paper background, charcoal navigation, a single copper accent, and clear P0 review feedback.

## Install dependencies

```powershell
python -m pip install -r apps/desktop/requirements.txt
```

## Start

```powershell
python apps/desktop/run.py
```

Alternatively, use the PowerShell launcher:

```powershell
powershell -ExecutionPolicy Bypass -File apps/desktop/start_desktop.ps1
```

## Package an executable

```powershell
powershell -ExecutionPolicy Bypass -File apps/desktop/build_exe.ps1
```

The resulting executable is located at:

```text
apps/desktop/dist/CADAutomationWorkbench/CADAutomationWorkbench.exe
```

## Current capabilities

- Create local project directories.
- Open existing projects and restore their parameters.
- Enter parameters for a 3D-printed enclosure.
- Edit structured tables for holes, interface cutouts, and screw bosses.
- Run a separate parameter-completeness check.
- Write `project.json` and `parameters.json`.
- Generate mock models, drawings, review reports, `manifest.json`, and delivery notes.
- Display P0 rule-check results.
- Navigate directly between workflow steps or open the output directory and skill repository.

## Current limitations

- No SolidWorks COM or AutoCAD COM calls are made by this prototype.
- Generated CAD files are mock placeholders and cannot be used for manufacturing.
- P0 checks currently cover parameter completeness and file structure; actual model and drawing review still needs to be connected.
