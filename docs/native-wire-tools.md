# Native round-section paths and mechanical imports (pilot)

These tools use local SOLIDWORKS PIA and do not execute caller-supplied code. Every operation requires the saved target document's full path and the PID selected by the host MCP; the host operation lock serializes execution. They do not start another SOLIDWORKS instance. The native subprocess prefers a PID-named ROT entry. For 2026 instances registering only the standard active object, the fallback must still verify the same PID and reject other instances.

- `solidworks_inspect_native_geometry`: Read body names, volumes, bounding boxes, and component transforms.
- `solidworks_build_round_sweeps`: Create native round-section sweeps in an empty, saved part. Paths are two-point lines or 3–6-point Bezier curves; validated JSON numbers are converted to equations, and arbitrary expressions are rejected. Independent rectangular extrusions are supported. Start with `dry_run=true`. Millimeter units are required; measured path lengths, rectangular bounding boxes, and rebuilds are checked. The operation does not save automatically.
- `solidworks_import_step_part`: Import into a new multibody SLDPRT; restore global import settings, reject overwrite, and return every body for review. The original target document is not saved.
- `solidworks_replace_component_preserving_transform`: Support only a unique fixed instance; preserve its transform and other component references without saving.
- `solidworks_exclude_reviewed_bodies`: Create a DeleteBody feature using reviewed exact body names, preserving original import history without saving.

## Specification

```json
{"sweeps":[{"name":"Wire1","control_points_mm":[[0,0,0],[0,3,0],[3,5,0],[5,5,0]],"diameter_mm":0.9,"color":[1,0,0]}],"boxes":[]}
```

Failure can leave unsaved partial features, which require review rather than blind retries. Existing features are not overwritten or deleted. Models supply geometry only; they do not establish harness manufacturing suitability, crimp compatibility, insulation performance, pull-out force, or a native SOLIDWORKS Routing license.

The result's `save_requested` indicates whether this operation requested a save. Inspection, dry runs, sweeps, replacement, and body exclusion do not return `saved=false` as though a save had failed. A successfully saved STEP import returns `save_requested=true, saved=true`. Actual save failures remain execution errors, and human review remains required.

MCP and the native subprocess exchange JSON over UTF-8 standard input, with a 1 MiB request limit. Sixty-four high-precision paths and localized file paths therefore avoid the Windows command-line length limit. The `-InputBase64` call remains compatible for short requests.

Validation: Input-rejection tests do not start CAD; real SOLIDWORKS versions and operation evidence must be recorded separately. This capability is pilot and requires geometric and visual review before release.
## Real-machine validation

Original author's record (SOLIDWORKS 2026 SP4.1 / Python 3.10): Sweeps and extrusions of 38 independent bodies, multibody STEP import, selected body exclusion, fixed-component replacement, and save-and-reopen were verified. Path lengths, box extents, and component transforms were read back; exported bodies passed an auxiliary B-Rep check. Eight input tests passed; installed integration regressions for target documents/processes passed 42 tests and 23 subtests. Other SOLIDWORKS versions were not tested. The capability remains pilot.

Maintainer review (2026-10-17, SOLIDWORKS 2026 SP01.1, Revision 34.1.1 / Python 3.12): Registered MCP tools, PowerShell, and local PIA completed straight/Bezier sweeps, rectangular extrusion, multibody STEP import, body exclusion, fixed-component replacement, and save-and-reopen. Straight length: 10 mm; measured Bezier length: 17.216903638 mm; theoretical sampled length: 17.216903179 mm; box volume: 500 mm³. Operations that did not request saving were confirmed not to modify disk files, and all three global import options were restored. Tests closed only their own documents and processes.

After installing test dependencies and confirming no user CAD instances are running, run the real-machine regression manually. The second argument must be a nonexistent output directory. The script starts its own 2026 instance, creates isolated test models, and writes JSON reports and BMP previews. It is excluded from automatic `pytest` collection and does not start CAD in normal CI.

```powershell
python tests/manual_native_wire_2026.py "E:\path\solidworks-automation-skill" "E:\cad-tests\native-wire-new-run"
```

Body RGB values are returned with review results and read back immediately after creation. AP203 exports do not contain color. Previews may use verified body RGB values, but must record the color source and must not claim AP203 contains appearance data.

Real-machine body-color readback uses 8-bit quantization (for example, input 0.70 reads back as 178/255), so color acceptance permits one 8-bit step. This does not relax geometric dimension checks.
