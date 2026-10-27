---
name: solidworks-fillet-chamfer-cnc
description: SolidWorks CNC fillet and chamfer automation subskill. Use for parameter preflight, semantic edge selection, multipoint variable-radius, face/full-round/setback and G2 fillets, distance-distance and angle chamfers, hole-mouth chamfers, CNC-friendly pockets, bounded fallback and rebuild evidence for mounting bases, connector blocks, brackets and counterbored plates.
---

# SolidWorks Fillet Chamfer CNC

## Determine the task mode first

For models with many fillets/chamfers, the main risks are topology changes, incorrect edge selection and unmanufacturable parameters, not merely API arguments.

- For new CNC mounting bases or parameter validation, run the template with `--dry-run` first; connect to SolidWorks only after the plan passes.
- For existing parts, first read the existing-model edge-selection section in [detailed lessons](references/cnc-fillet-chamfer-lessons.md); do not apply the template's fixed expected edge counts.
- For variable-radius, face, full-round or setback fillets, first run this subskill's advanced capability probe. Keep status `pilot` when the SolidWorks version or topology differs from a verified sample; do not claim stability across versions.
- Multipoint variable-radius, surface combinations and distance-distance chamfers have independent native SW2026 SP1.1 evidence, but require reruns on different versions/topologies. Hold-line fillets have been retested through Python, C# PIA, SWBasic and in-process unmanaged C++; the failure boundary is the local SW2026 SP1.1 `ISetHoldLines` call, not a Python-only limitation. This build must remain `pilot/blocked`; falling back to an ordinary face fillet is not success.

## Template entry point

Start with preflight without COM:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\create_cnc_mount_template.py `
  --dry-run `
  --set base_corner_radius=6 `
  --set chamfer_angle_deg=30 `
  --output-dir C:\CADAutomationWorkbench\cnc_mount
```

Confirm that `validation.errors` is empty in `*_plan.json` and that semantic targets and `expected_edge_count` match the design. Then remove `--dry-run` to execute native modeling. Prefer JSON for large parameter sets:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\create_cnc_mount_template.py `
  --params-json subskills\solidworks-fillet-chamfer-cnc\examples\cnc_mount_precision_params.json `
  --failure-policy strict `
  --output-dir C:\CADAutomationWorkbench\cnc_mount
```

`strict` accepts only requested dimensions; `progressive` tries 100%/75%/50%. If fallback changes a dimension, report the actual value in the delivery summary; do not claim an exact match to the original request.

## Mandatory gates

1. Run the parent skill's `scripts/sw_preflight.py` before native modeling; `--dry-run` does not require SolidWorks.
2. Parameter checks must cover finite numbers, fillet/chamfer limits, hole/slot collisions, minimum edge walls, feature clearances, counterbore/pocket bottom walls and safe output basenames.
3. New templates follow base body → vertical-corner fillets → outline chamfers → holes/slots/pockets → hole-mouth chamfers. For existing models, choose the order from dependencies.
4. Use geometric signatures and expected counts as edge-selection evidence. Stop on count mismatch; do not widen coordinate tolerances or guess using `Edge1` or screen clicks.
5. Read each fillet/chamfer back from the feature tree after rebuild. A non-null COM return does not establish persistence.
6. Save SLDPRT, export STEP, run `sw_review.run_review()`, and manually inspect isometric and top previews.

## Advanced fillet entry point

First inspect the local type library read-only, without starting SolidWorks:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\verify_advanced_fillets.py `
  --output-dir C:\CADAutomationWorkbench\advanced_fillet_probe
```

Run the current six independently verified native regressions:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\verify_advanced_fillets.py `
  --verify-solidworks `
  --modes variable face surface_combo full_round setback width_width_chamfer `
  --output-dir C:\CADAutomationWorkbench\advanced_fillet_verified
```

Claim support for the environment only when the report marks the capability `verified` and the corresponding SLDPRT, STEP, reopen evidence and review report all exist. Minimal cases verified on SolidWorks 2026 SP1.1 are:

- Single-edge endpoint variable radius R2→R5, with feature type read back as `VarFillet`.
- Three intermediate control points at 25%/50%/75% on one edge, read back as R3/R6/R4; interpret `GetControlPointRadiusAtIndex` positions as percentages `25/50/75`.
- R4 face fillet between two adjacent face sets, `ISimpleFilletFeatureData2.Type=2`.
- R3 G2 face fillet between a plane and cylinder, with `CurvatureContinuous=true` after reopening.
- Full-round with one face in each of three sets, `ISimpleFilletFeatureData2.Type=3`.
- R3 three-edge corner with 1 mm setback per edge; read back one setback vertex.
- C2/C4 distance-distance chamfer, `IChamferFeatureData2.Type=2`, distances read back as `2/4 mm` at sides `0/1`.

Wrap setback distances explicitly as `VT_ARRAY | VT_R8`. An ordinary Python `tuple` may produce no COM exception while `FeatureFillet` returns `None`; do not reinterpret that result as an ordinary fillet.

Hold-line mode uses a projected split line, face-set marks `2/4`, hold-line mark `8` and requires `GetHoldLineCount=1`. Official `ISetHoldLines` supports only in-process unmanaged C++, so scripts include an MSVC x64 DLL and SWBasic main-thread dispatcher; C# PIA and Python paths remain for comparison. On local SW2026 SP1.1 / Revision 34.1.1, ordinary Python arrays read back zero and explicit SAFEARRAY causes a server fault. C#, SWBasic and native C++ also failed to produce persistent hold lines, with native calls faulting at `ISetHoldLines`. The default therefore returns structured `blocked/known_server_fault` without executing the dangerous call.

Use `--unsafe-native-hold-line` only to retest another service pack in an isolated SolidWorks instance you own. This option may terminate the instance and must not be used in a session containing unsaved documents. Success still requires `GetHoldLineCount=1` both after creation and after reopening.

## Open-source complex-case regression

The MIT-licensed CadQuery `parametric-bracket-library/l_gusset` regression contains two perpendicular mounting plates, a triangular gusset and six mounting holes; its SW2026 import baseline is `1 solid / 18 faces / 49 edges`. Create a variable-radius fillet with four control points at 20/40/60/80% and a C0.8/C1.4 distance-distance chamfer on the same complex body:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\verify_open_source_bracket.py `
  --source C:\CADAutomationWorkbench\sources\l_gusset.step `
  --source-commit 5b285130bff480cda282499e83604b295dd0aa4d `
  --version 2026 `
  --output-dir C:\CADAutomationWorkbench\opensource_l_gusset
```

Mark `verified` only after the pinned commit, SHA-256 of the CadQuery 2.8.0 output, complexity gates, all four point positions/radii, both unequal chamfer distances, final topology, rebuild, SLDPRT, STEP, reopen and four-view review pass. Generate the input STEP using CadQuery 2.8.0 as described in that repository's README; the script does not execute unpinned network downloads at runtime.

The existing FreeCAD-library complex corner bracket remains a second independent chamfer regression:

The complex-model regression uses FreeCAD-library `2020_corner_bracket-Corner.step` pinned by commit, SHA-256 and CC BY 3.0 attribution; it does not use a mutable main-branch URL:

```powershell
python subskills\solidworks-fillet-chamfer-cnc\scripts\verify_open_source_complex_case.py `
  --version 2026 `
  --output-dir C:\CADAutomationWorkbench\opensource_corner_bracket
```

The script selects the unique 24.041631 mm diagonal edge from the manifest's endpoint/length signature and applies a real C0.2/C0.4 distance-distance chamfer. Mark the case `verified` only if the download hash, exact source `1 solid / 40 faces / 98 edges`, chamfer FeatureData, final `41 faces / 101 edges / 66 vertices` preserved after reopen, SLDPRT/STEP and four-view review all pass. A cached file may be reused offline, but its SHA-256 must still be recalculated.

## CNC geometry defaults

- Use `rounded_slot` for weight-reduction pockets by default rather than delivering unmachinable zero-radius internal corners. Use `rectangle` only when a later corner-finishing process is explicitly required, and keep the DFM warning.
- Check locating holes, the center slot and weight-reduction pockets with 2D envelopes derived from the same parameter source. Template v2 places locating holes along Y by default to avoid intersection with the center slot.
- Constant-radius fillets and angle chamfers are the general stable paths. Multipoint variable-radius, face/full-round/setback, plane-cylinder G2 and distance-distance chamfers have minimal native SolidWorks 2026 SP1.1 regressions, but require capability-script reruns on other topology/versions. Record API, SolidWorks version, input topology, rebuild results and preview evidence before raising the capability level for complex transitions.

See [CNC fillet/chamfer lessons](references/cnc-fillet-chamfer-lessons.md) for selection signatures, failure semantics, existing-model strategy and extension plans.

## Verification requirements

Produce the following after every completed task:

- `*.SLDPRT`
- `*.step`
- `*_parameters.json`
- `*_review_report.json`
- `*_isometric.bmp` or a converted PNG.

At minimum, review:

- Whether `evaluation.status` is `pass` or an explainable `warn`.
- Whether `expected_outputs_exist` is `True`.
- Whether `previews_not_blank` is `True`.
- Whether `validation.errors` is empty.
- Whether `treatment_evidence` records requested/actual values, every attempt and selected-edge signatures.
- Whether `feature_evidence.missing_names` is empty.
- Whether the feature tree contains the expected `Fillet` / `Chamfer` / `Cut` features.
