# CAD Studio User Manual

This manual is for mechanical engineers, students, and designers using CAD Studio for the first time. CAD Studio and Skill/CLI/MCP are peer entry points sharing CAD Core, task protocols, the capability manifest, and evidence system. Users can run Skill/CLI/MCP directly without installing the desktop application. Engineering files and task records are stored locally by default.

## 1. What the software can do

- Plan and create basic parts, enclosures, fixtures, and assemblies from natural language. SW2026 can create open-profile base flanges and export flat-pattern DXF as a pilot; other sheet-metal capabilities require human review or are blocked according to the capability manifest.
- Modify existing SLDPRT, SLDASM, STEP, STL, DWG, DXF, PDF, or reference images.
- Create through holes, blind holes, counterbores, countersinks, threaded holes, obround holes, semicircular slots, and hole patterns.
- Without CAD software, produce `.cadstudio.json`, STL, OBJ, DXF, SVG, PDF, PNG, and review reports. Native SLDPRT/SLDASM/SLDDRW/DWG requires the corresponding CAD software and a verified backend.
- Select CAD software, material, process, and execution stages automatically, while allowing manual choices.
- Orchestrate complete projects through "requirements analysis -> concept -> parts -> assembly -> motion/interference -> drawings -> delivery".
- Use human approval and review gates to prevent unconfirmed control of desktop CAD or delivery of incorrect files.

## 2. System requirements

### 2.1 Application

- Windows 10 22H2 or Windows 11, 64-bit.
- Microsoft Edge WebView2 Runtime. It is usually included with Windows 10/11; the installer prompts if it is missing.
- 8 GB RAM recommended; 16 GB or more for complex assemblies.

### 2.2 AI execution

Install and sign in to at least one of these CLIs:

- Codex CLI
- Claude Code
- Gemini CLI
- OpenCode

CAD Studio does not include model credits or store API keys. The corresponding CLI or CC Switch manages model accounts, plans, proxies, and routing.

For initial installation, see the following table. Install Node.js 20 or later before installing through npm. If global installation is unavailable on a company computer, contact your administrator or use the project's official installer.

| Agent | Official documentation | Common installation method | Verification command |
| --- | --- | --- | --- |
| Codex CLI | <https://developers.openai.com/codex/cli/> | `npm install -g @openai/codex` | `codex --version`, `codex login status` |
| Claude Code | <https://docs.anthropic.com/en/docs/claude-code/setup> | Follow the official Windows installer or PowerShell instructions | `claude --version`, then run `claude` to sign in |
| Gemini CLI | <https://github.com/google-gemini/gemini-cli> | `npm install -g @google/gemini-cli` | `gemini --version`, then run `gemini` to sign in |
| OpenCode | <https://opencode.ai/docs/> | `npm install -g opencode-ai` | `opencode --version`, `opencode auth login` |

Close and reopen CAD Studio after installation. If the verification command works in PowerShell but the application cannot detect the CLI, check that the npm global directory is in the current user's `PATH`. Alternatively, set `CODEX_BIN`, `CLAUDE_BIN`, `GEMINI_BIN`, or `OPENCODE_BIN` in the system environment to the executable's full path.

### 2.3 Real CAD automation

- Python 3.10 or later; 64-bit Python 3.11/3.12 recommended.
- Python dependencies: `pywin32`, `comtypes`.
- Current real-machine baselines are SolidWorks 2024, SolidWorks 2026 SP01.1, and AutoCAD 2024. For SolidWorks 2026, only capabilities explicitly listing 2026 in `capabilities.yaml` are verified. SolidWorks 2025 and other capabilities remain compatibility targets.
- Python, SolidWorks, and AutoCAD should all match the operating system's 64-bit architecture.

Install Python dependencies:

```powershell
python -m pip install "pywin32>=305" "comtypes>=1.2.0"
```

After initial installation or an environment change, run:

```powershell
python scripts\cad_studio.py doctor
```

The output's `remediations` provide official links and installation commands for missing components; desktop Settings and Help show the same recommendations. Missing optional backends block only their corresponding formats, not other available backends.

### 2.4 Open-format backends without CAD software

Without SolidWorks/AutoCAD, the workflow goes beyond requirements gathering and script generation. The headless backend can genuinely write `.cadstudio.json`, STEP, IGES, BREP, STL, OBJ, GLB, DXF, SVG, PDF, and PNG from NeutralCadDocument, with geometry evidence, a Preview Manifest, fallback images, and SHA-256 hashes:

```powershell
python scripts\cad_studio.py write-open-format `
  --input .\part.cadstudio.json `
  --out-dir .\output `
  --formats cadstudio step iges brep stl obj glb dxf svg pdf png
```

Generate a browser preview scene separately from an existing DXF:

```powershell
python scripts\cad_studio.py preview-dxf `
  --input .\drawing.dxf `
  --output .\output\drawing.scene.json
```

The conversion reads only LINE, CIRCLE, ARC, LWPOLYLINE, POLYLINE, TEXT, MTEXT, and DIMENSION. Input limits are 50 MB / 200000 entities. Unsupported entities are recorded as limitations; the converter does not execute scripts or overwrite an existing scene file.

OCCT supports boxes, cylinders, Boolean unions, cylindrical hole cuts, and a restricted closed ruled Loft through a separate entry point. It reads back solid validity, volume, bounding boxes, and topology counts. Smooth Loft and other complex features still return `blocked`. Native SLDPRT/SLDASM/SLDDRW/DWG must return `blocked` when vendor software or a licensed SDK is unavailable; changing extensions must never fake these outputs.

Before the first execution, run:

```powershell
python scripts/cad_studio.py doctor
```

The repository root's `capabilities.yaml` defines capability limits. Configuration families, SW2026 open-profile sheet metal, and HSS rectangular weldment frames are controlled `pilot` capabilities; design tables and complex sheet metal/weldments are not marked as complete deliverables. Weldments require readback of `WeldmentFeature`, `WeldMemberFeat`, and each `CutListFolder`'s body count, length, quantity, and angles, followed by save-and-reopen review. Simulation/FEA can use CalculiX for restricted linear static tasks, and complex surfaces can use OCP for restricted closed ruled Loft. These pilots must not be presented as complete engineering deliverables without result evidence, mesh convergence, or geometry-quality proof.

The CLI can also run these controlled gates independently:

```powershell
python scripts\cad_studio.py check-dfm --input .\part.cadstudio.json --output .\output\dfm.json --profile .\supplier-profile.json
python scripts\cad_studio.py routing-preflight
python scripts\cad_studio.py check-routing --input .\route.json --output .\output\routing_report.json
python scripts\cad_studio.py fea-preflight --solver auto
python scripts\cad_studio.py prepare-fea --input .\fea.json --out-dir .\output\fea
python scripts\cad_studio.py run-fea --input .\fea.json --out-dir .\output\fea --timeout 120
python scripts\cad_studio.py review-advanced-geometry --input .\surface-plan.json --output .\output\surface_report.json
python scripts\cad_studio.py create-ocp-loft --input .\loft.json --out-dir .\output\loft
```

Drawing and BOM tasks additionally return views, real dimensions, BOM rows, model/drawing relationships, and review findings. Automatic model-dimension insertion with readback of real dimension entities has been verified separately on SW2024 and SW2026 SP01.1. The SW2026 regression read three real views and six real dimension entities in three consecutive runs. Complete drawings remain `pilot`: file existence does not mean delivery is complete. Sheet size, view layout, dimension chains, hole tables, title blocks, and BOM still require human review.

The AutoCAD backend comprises headless DXF checks, an allowlisted command bridge, COM, and .NET. The local AutoCAD 2024 COM proxy remains unstable. The independent .NET backend repeatedly passed allowlisted real-machine regressions through the local Managed API: it creates and reopens real DWG, produces PDF/PNG, and reads back entities, layers, and real dimensions. Preflight rechecks the latest three reports and artifact hashes, returning `verified` when complete and automatically downgrading damaged evidence. This does not establish support for arbitrary DWG operations or plugin code. Run:

```powershell
python subskills\autocad-automation\scripts\acad_dotnet_preflight.py
python subskills\autocad-automation\scripts\acad_dotnet_regression.py
python subskills\autocad-automation\scripts\acad_dotnet_regression.py --real-cad
```

Use `--install-sdk` only with explicit authorization. It installs the .NET SDK from Microsoft's official source and does not download proprietary Autodesk DLLs. If `dotnet.exe` on PATH has only a runtime, the checker continues searching the current user's directory for an actual SDK. Loading unsigned plugins in desktop AutoCAD still requires a trusted path or signed plugin package. Real-machine regression reads the original `SECURELOAD/FILEDIA/BACKGROUNDPLOT` values, temporarily adjusts them only in an exclusive Core Console, and restores them before exiting.

## 3. Installation and launch

### Installer build

1. For an upstream release, download `CAD-Studio-<version>-Setup-x64.exe` from its GitHub Releases. This localized fork has no published binary release; upstream binaries do not contain this localization.
2. Double-click the installer and follow its instructions.
3. Launch CAD Studio from the Start menu.

The executable is named `cad-studio.exe`; everyday use does not require navigating to the installation directory.

### Portable build

1. For an upstream release, download `CAD-Studio-<version>-Windows-x64-Portable.zip`; it is not a localized fork release.
2. Extract the entire archive into a writable directory.
3. Run `CAD Studio.exe` in that directory.
4. Do not move only the executable; adjacent `skill` resources are part of the local executor.

Windows SmartScreen may report "Unknown publisher" because the open-source build lacks a commercial code-signing certificate. Verify the SHA-256 on the release page before choosing to run it.

### Automatic updates

The upstream CAD Studio Windows build silently checks GitHub Releases once at startup. An update notice appears at the bottom right when a new version is available; Settings shows the version, release notes, and download progress. The localized fork has no published update channel yet.

1. Clicking "Download and install" downloads the update and verifies its Tauri updater signature.
2. After successful verification, the Windows installer takes over and closes the current window.
3. If checking or installation fails, "Open download page" opens GitHub Releases for a manual download; verify the file against `SHA256SUMS.txt`.

The updater signature verifies release origin and integrity. It differs from commercial Windows code signing, so SmartScreen may still show "Unknown publisher". The software does not install updates without user confirmation.

## 4. First use

1. Open Help at the top and inspect the environment status.
2. Open Settings and select an Agent installed on this machine.
3. If using CC Switch, click "Read CC Switch status". The software reads the current user's CC Switch SQLite/JSON configuration and returns only route names, models, endpoints, and managed status, never keys.
4. Click "Choose output folder" and create a separate project directory.
5. For real CAD operations, install Python dependencies and start SolidWorks or AutoCAD.
6. Click "Start local executor". Once its running status and PID appear, submit a task.

## 5. Create your first model

### Model from scratch

1. Click "New task" on the left or "Modeling" at the top.
2. Select a template such as General Part, Assembly, or Enclosure.
3. Enter complete requirements in the goal field, for example:

```text
Create a 120 x 80 x 8 mm mounting plate in 6061 aluminum.
Place one 6.6 mm diameter through hole at each corner, with centers 10 mm from both adjacent edges.
Create a 20 mm diameter, 4 mm deep counterbore at the center of the top face.
Chamfer the perimeter 1 x 45 degrees.
Output SLDPRT, STEP, a PDF engineering drawing, and PNGs from four views in the current output directory.
```

4. Leave "AI selects automatically" when software, material, or process is unspecified.
5. Keep "Real holes/cuts" enabled for hole and slot tasks.
6. Enable "Local CAD automation" when CAD operations are needed.
7. Review the execution plan on the right and click "Execute with current AI".
8. When a risky capability requests approval, verify the reason before approving.

### Modify an existing file

1. Click Import at the top.
2. Select a CAD file, drawing, or reference image.
3. Explain what to retain and what to modify in the dialog.
4. Explicitly request a new file to avoid overwriting the original project.

## 6. Complete engineering projects

When assembly, motion, drawings, and delivery are needed together, they need not be split into unrelated tasks. Describe the final goal directly; the software creates a staged engineering plan:

1. Extract requirements and constraints.
2. Route to CAD software and skills.
3. Model parts and critical features.
4. Define assembly relationships and check interference.
5. Perform Motion Study or motion verification.
6. Produce GB/T engineering drawings, BOM, and tolerances.
7. Export formats, record artifacts, and perform human review.

Follow-up requests can describe local changes such as "Change M6 to M8; leave other dimensions unchanged." The system restores the previous plan and reruns only the affected stage and its downstream stages.

Failed, blocked, canceled, or review-pending tasks can be partially regenerated from Delivery. Before clearing current run fields, the software saves the previous status, artifact ledger, drawing/BOM evidence, review gates, and errors as a read-only version snapshot. By default, it retains metadata for the latest 20 runs. The rerun policy starts at the failed stage and continues through its successors, requiring new artifacts to use a new version directory or filename. Historical snapshots store paths, sizes, hashes, and review evidence, not copies of CAD file contents, and do not delete previous deliverables.

When critical dimensions, tolerances, loads, material strength, or safety-related parameters are missing, the AI must ask or mark the result as a concept; it must not assume the result is a manufacturing-ready final design.

## 7. Pages

- Left task list: Historical tasks for the current project. Titles come from user goals; "Codex execution" in older versions is a historical internal title and does not mean Codex is mandatory.
- Overview: Create tasks, import references, and inspect the environment.
- Modeling: Templates for parts, assemblies, jigs, sheet metal, enclosures, reverse engineering, and more.
- Features: Holes, slots, threads, interface openings, and patterns.
- Drawings: GB/T drawings, tolerances, BOM, and format conversion.
- Review: Verify native opening, dimensions, features, artifacts, and risks.
- Delivery: Classify results as "Deliverable / Human review required / Blocked / Incomplete evidence"; show current artifacts, historical versions, artifact relationships, and backend diagnostics. STL, GLB/GLTF, and OBJ support rotation and zoom; DXF and images support read-only preview. "This run is deliverable" appears only after machine evidence is complete and human review gates are satisfied.
- Settings: AI, CC Switch, local executor, output, and knowledge base.
- Help: First-use steps and environment status.

## 8. Agent and CC Switch

"Agent" and "model routing" are separate layers:

- The Agent CLI determines whether Codex, Claude Code, Gemini CLI, or OpenCode executes the task.
- CC Switch routing determines the model provider, endpoint, and model used by that CLI.

Selecting Claude Code switches the execution button, Executor, and route list to Claude; synchronizing CC Switch no longer automatically switches back to Codex.

CC Switch is optional. Without it, CAD Studio uses the selected CLI's local sign-in state and configuration directly.

## 9. Approval and review

The following actions require human approval:

- Control a SolidWorks / AutoCAD desktop session.
- Access files outside the project directory.
- Use external networks or cloud knowledge bases.
- Use a full-access sandbox, delete files, or push to Git.

After task completion, check at least:

- Files open natively in the target CAD software.
- Critical dimensions, tolerances, datums, and hole locations are correct.
- Holes and slots are actual geometric features, not merely sketches or annotations.
- Assembly mates, interference, and motion directions are correct.
- Current output files exist with the correct timestamps and versions.

A task can be marked as passed only after review notes are entered and all checklist items are complete.

## 10. Storage and privacy

- Default output: the current user's `Documents/CADAutomationWorkbench`.
- Queue and settings: `com.wzyn.cadstudio` in the current user's application data directory.
- Wallpapers, project paths, task events, and artifact ledgers remain local.
- API keys are not written to CAD Studio settings or task files.
- Engineering context may leave the machine only when cloud RAG is explicitly enabled or the selected AI CLI itself accesses the network.

Do not upload queue directories, logs, or task JSON containing company secrets directly to public issues.

## 11. Frequently asked questions

### "Agent Provider not detected"

Confirm the CLI's `--version` command works in PowerShell, then restart CAD Studio. Advanced users can specify executables with `CODEX_BIN`, `CLAUDE_BIN`, `GEMINI_BIN`, and `OPENCODE_BIN`.

### "Python not installed"

Install 64-bit Python 3 and select "Add Python to PATH" in the installer. Restart the application before starting the local executor.

### "SolidWorks / AutoCAD not detected"

Confirm the software is installed correctly; start SolidWorks manually once before automation. CAD Studio checks COM registration, public desktop shortcuts, standard directories, and common installation locations on `D:`/`E:`. "Installed but not running" does not mean installation failed; start the software manually and check again.

### CC Switch does not show all models

Upgrade to a recent CC Switch release and confirm the configuration was saved. CAD Studio supports `~/.cc-switch/cc-switch.db` and the older `config.json`.

### A task remains pending approval

Open task details to inspect the approval reason. The local executor continues only after the user explicitly approves.

### Why are there so many tasks on the left?

The left side shows task history, not a feature menu. Click a task to inspect status and results. History is stored in the local queue directory; deleting application data clears it, so back up required deliverables first.

## 12. Help and feedback

When submitting a GitHub issue, provide:

- CAD Studio version and installation method.
- Windows, Python, SolidWorks/AutoCAD, and Agent CLI versions.
- Reproduction steps and sanitized error messages.
- Whether CC Switch is used and the route type; never submit API keys.

Project: <https://github.com/Luxeville-Group/solidworks-automation-skill>
