---
name: solidworks-automation
description: "Automate verified SOLIDWORKS parts, holes and slots, assemblies, drawings, exports and delivery review. Use capabilities.yaml for support levels and require human review for unverified capabilities."
metadata: { "openclaw": { "homepage": "https://github.com/Luxeville-Group/solidworks-automation-skill", "os": ["win32"], "requires": { "anyBins": ["python", "py"] } } }
---

# SOLIDWORKS Automation

Technical instructions are maintained in English. Respond to Turkish-speaking users in Turkish, retaining English CAD terms and exact API names. Read [the Turkish guide](README.tr.md) for onboarding and [the terminology guide](localization/TERMS.tr-en.md) for consistent wording. Supported presentation languages are Turkish and English; language selection does not change engineering standards or capability levels.

## Quick start

### Environment

- Windows; native SOLIDWORKS operations target SOLIDWORKS 2026 for support and acceptance. Headless open-format writing does not require installed CAD software.
- Python 3.10+; native Windows automation also needs `pywin32` / `comtypes`.
- MCP/tool invocation needs `mcp` / `pydantic`.
- Final drawing review needs `PyMuPDF`, included in `requirements.txt`, to read actual dimension text bounds from the exported PDF.
- GLB/GLTF/OBJ/STL mesh references may also require `trimesh` / `pygltflib` / `numpy` / `Pillow`.
- For OpenClaw, place the skill in `~/.openclaw/skills/solidworks-automation/` or `~/.agents/skills/solidworks-automation/`.

### Preflight

Before SOLIDWORKS automation, run:

```powershell
python SKILL_DIR/scripts/sw_preflight.py
```

Before desktop/CLI execution, also consider:

```powershell
python SKILL_DIR/scripts/cad_studio.py doctor
```

`capabilities.yaml` is the shared source of truth for Skill, MCP, queue and UI capabilities. Levels include `verified`, `pilot`, `reference_only` and `not_implemented`; the last two cannot be delivered unattended. It also routes atomic operations across Python, C# PIA/Add-in, native C++, SWBasic, OCCT and external solvers. Inspect `python scripts/backend_router.py --list` and `references/language-backend-routing.md`.

### Entry points and backends

- CAD Studio and Skill/CLI/MCP are peer entry points sharing Automation Job, NeutralCadDocument, Preview Manifest, Evidence Graph and capability definitions.
- Missing SOLIDWORKS/AutoCAD blocks native formats such as SLDPRT/SLDASM/SLDDRW/DWG. Route eligible open-format jobs to `headless_open_format_writing`.
- `scripts/headless_cad_writer.py` uses an isolated OCCT/OCP process to write real STEP, IGES, BREP, STL, OBJ and GLB files. The 2D backend writes DXF, SVG, PDF and PNG, with geometry and SHA-256 evidence.
- DXF deliveries also produce `preview_scene`. Convert an existing DXF with `python scripts/cad_studio.py preview-dxf --input drawing.dxf --output drawing.scene.json` or MCP `cadstudio_build_dxf_preview_scene`. This reads allowlisted entities and refuses to overwrite existing files.
- OCCT covers boxes, cylinders, Boolean union, cylindrical hole cuts, ruled/restricted smooth Loft, straight/single-arc Sweep, closed-shell Knit and open-surface Thicken. Complex paths, self-intersecting offsets or a missing OCP runtime remain `blocked`. Renaming extensions or creating empty files is not support.
- `delivery-preview` displays actual outputs from the current job. Fixed samples require `demo-showcase` and `isDemo: true`, and cannot be used as delivery evidence.

Dependency handling:

1. If `comtypes` / `win32com` / `pythoncom` is missing, explain the missing libraries and request permission to configure the local Python environment. Use Turkish for Turkish-speaking users, retaining package names.
2. With permission, run `python -m pip install "pywin32>=305" "comtypes>=1.2.0"`. If declined, stop and provide the manual command.
3. Missing SOLIDWORKS installation/COM registration stops native operations. When native formats are unnecessary and `fallbackPolicy=allow_open_formats`, continue with the open-format backend rather than failing the whole job.

Install only dependencies relevant to the task; ordinary part modeling does not require optional mesh conversion packages:

```powershell
# Core SOLIDWORKS COM automation and drawing review
python -m pip install -r SKILL_DIR\requirements.txt

# Only for GLB/GLTF/OBJ/STL inspection, scaling or conversion
python -m pip install -r SKILL_DIR\requirements-mesh.txt
```

Before converting GLB/GLTF/FBX/BLEND to OBJ/STL, check `trimesh`, `pygltflib` and `PIL` with `importlib.util.find_spec()`. Explain missing dependencies and their purpose before installation or provide manual commands.

### Connect to SOLIDWORKS

```python
import sys; sys.path.insert(0, r"SKILL_DIR/scripts")
from sw_connect import mm
from sw_part import sketch, sketch_circle, extrude_boss
from sw_sketch_quality import fully_define_sketch
from sw_session import SolidWorksSession

with SolidWorksSession(version=2026) as session:
    model = session.new_part()
    with sketch(model, "Front Plane") as sketch_name:
        sketch_circle(model, 0, 0, mm(25))
        fully_define_sketch(model)
    if extrude_boss(model, sketch_name, mm(50)) is None:
        raise RuntimeError("Extrusion failed")
    if not session.save(model, r"C:\temp\cylinder.sldprt"):
        raise RuntimeError("Save failed")
    if not session.export(model, r"C:\temp\cylinder.step"):
        raise RuntimeError("Export failed")
```

Replace `SKILL_DIR` with the actual skill installation path.

Read back sketch constraint states, dimensions and relations before delivery. Bulk Fix constraints cannot replace design parameters. Save and reopen to verify that the intended feature consumes the sketch, key dimensions remain editable and hole positions remain correct. Use `fully_define_sketch()` for basic circles/rectangles. For complex sketches, define design dimensions and relations explicitly, then inspect with `inspect_model_sketches()`; missing evidence requires human review.

Session cleanup is limited to documents registered by this run and empty application instances whose ownership is confirmed. Handle this run's files first when reaching the document budget. Failed execution/rebuild, unknown check results or outstanding human review prevent a completion claim. Remote MCP retrieves PNG/original files through `artifact_refs` and verifies SHA-256; see `mcp-server/README.md`.

## Workflow map

| Need | Implementation | Reference |
|---|---|---|
| Preflight and dependencies | `scripts/sw_preflight.py` | `references/troubleshooting.md` |
| Open-format writing without CAD | `scripts/headless_cad_writer.py`, `scripts/cad_studio.py write-open-format` | `capabilities.yaml`, shared CAD Core Schema |
| Capability/type-library probe | `scripts/sw_capability_probe.py` | `references/complex-mechanical-routing.md` |
| Python/C#/C++/SWBasic/OCCT routing | `scripts/backend_router.py` | `references/language-backend-routing.md`, `capabilities.yaml` |
| In-process C# Add-in, events and UI | `scripts/sw_addin_host.ps1`, `scripts/sw_addin_host.py` | `references/solidworks-addin-host.md` |
| Multi-model macro guard | `scripts/sw_macro_guard.py` | `references/openclaw.md` |
| Session API | `scripts/sw_session.py` | — |
| Connection/document management | `scripts/sw_connect.py` | — |
| Appearance/materials | `scripts/sw_appearance.py` | `references/appearance.md` |
| Parts, sketches and features | `scripts/sw_part.py` | `references/part-modeling.md` |
| Standard external spur-gear solids | `scripts/sw_gear.py` | `references/gears.md` |
| Blind/counterbored/countersunk holes, obround slots and position checks | `scripts/sw_hole_features.py`, `scripts/sw_review.py` | `references/complex-hole-features.md`, `references/review.md` |
| Natural language to parametric plan / VibeCAD | `subskills/solidworks-vibecad/scripts/plan_from_brief.py` | `subskills/solidworks-vibecad/SKILL.md`, its README |
| CNC parts with many fillets/chamfers | `subskills/solidworks-fillet-chamfer-cnc/scripts/create_cnc_mount_template.py`; advanced fillets: `verify_advanced_fillets.py` | That subskill's SKILL and `references/cnc-fillet-chamfer-lessons.md` |
| Screw/threaded holes and tap-drill holes | `subskills/solidworks-threaded-holes/scripts/create_threaded_hole_template.py` | That subskill's SKILL and `references/threaded-hole-lessons.md` |
| AutoCAD DWG/DXF, line-art conversion and batch edits | `subskills/autocad-automation/scripts/acad_draw.py`, `acad_review.py` | That subskill's SKILL and troubleshooting reference |
| Assemblies, gears, hinges and draggable mates | `scripts/sw_assembly.py` | `references/assembly.md` |
| Motion Study, rotary motors and results audit | `scripts/sw_motion.py` | `references/motion-study.md`, `references/complex-mechanical-routing.md` |
| Engineering drawings | `scripts/sw_drawing.py` | `references/drawing.md` |
| Exports | `scripts/sw_export.py` | `references/export.md` |
| Configurations, dimensions and custom properties | `scripts/sw_document_data.py` | `references/advanced.md` |
| Assembly BOM CSV and Pack and Go | `scripts/sw_delivery.py` | `references/export.md` |
| High-fidelity OBJ/STL mesh reference import | `scripts/sw_import_mesh_reference.py` | `references/mesh-reference-import.md` |
| Result review | `scripts/sw_review.py` | `references/review.md` |
| Semantic entity references | `scripts/sw_entity_reference.py` | Progressively replaces Face1/Edge1 and screen coordinates |
| DFM manufacturing risk review | `scripts/dfm_review.py`, `scripts/dfm_profiles.py`, `scripts/cad_studio.py check-dfm` | Supplier profiles, B-Rep evidence; declarative machining, sheet-metal, laser, printing and molding rules |
| Neutral Routing review/preflight | `scripts/routing_review.py`, `check-routing`, `routing-preflight` | Endpoints, segments, lengths, bend radii, collisions/clearance, supports and BOM; native writes require add-in/license evidence |
| FEA preflight, inputs and restricted solving | `scripts/fea_analysis.py`, `scripts/fea_convergence.py`; `fea-preflight/prepare-fea/run-fea/run-fea-convergence` | CalculiX 2.23 linear/nonlinear static, plasticity, surface contact, final-step COPEN/CPRESS/CSLIP and mesh convergence; engineering review remains required |
| Complex surfaces and molds | `scripts/advanced_geometry.py`, `scripts/advanced_geometry_ocp.py`, `scripts/advanced_surface_ocp.py`; `review-advanced-geometry/create-ocp-loft/create-ocp-surface` | Ruled/smooth Loft and restricted Sweep/Knit/Thicken can write/reopen B-Rep; G1/G2 and curvature radii are sampled evidence only |
| Local MCP server/protocol validation | `mcp-server/server.py`, `scripts/validate_mcp.py` | `mcp-server/README.md`, `references/mcp-server.md` |
| Unwrapped API lookup | — | `references/api-lookup.md` |
| OpenClaw | — | `references/openclaw.md` |
| Sheet metal, weldments, simulation and properties | — | `references/advanced.md` |
| Enterprise/project knowledge, local-first and cloud RAG | `apps/desktop/cad_workbench/knowledge_retrieval.py` | `references/enterprise-agent-rag.md` |
| Codex/Claude/Gemini/OpenCode provider adapters | `apps/desktop/cad_workbench/agent_providers.py` | `references/agent-provider-architecture.md` |
| Cross-domain engineering DAG | `apps/desktop/cad_workbench/engineering_orchestrator.py` | `references/complex-mechanical-routing.md` |
| Troubleshooting | — | `references/troubleshooting.md` |

Pack and Go passed three native regressions on a basic two-part assembly in SW2026 SP01.1: `SavePackAndGo()` wrote the assembly and both parts with status 0 and no staging fallback. Some versions' `GetDocumentNames()` enumerate only the top-level file before saving. Perform native save and audit actual dependencies; do not add native assembly parts through `AddExternalDocuments`. If dependencies remain missing, `scripts/sw_delivery.py::pack_and_go()` defaults to a `pilot` staging package using `GetDependencies2`, a manifest and SHA-256. Use `fallback_policy="blocked"` for strict native semantics. External references, Toolbox, configurations and drawings still require human review, so the overall capability remains `pilot`.

## OpenClaw collaboration

1. Confirm SOLIDWORKS version/UI language, input/output paths and target operation: modeling, assembly, drawing or export.
2. Reuse `{baseDir}/scripts` instead of rewriting COM connection logic.
3. Run short Python scripts through OpenClaw's exec/shell capability:

```python
import sys
sys.path.insert(0, r"{baseDir}/scripts")
from sw_connect import connect_solidworks, mm, deg, new_document
```

4. Check for `None` returns, successful saves/exports and actual output files.
5. Export at least an isometric preview after creating/modifying a model; add front/top/right views when needed. Visually inspect screenshots/BMPs against the requested geometry.
6. Read `references/openclaw.md` for more workflow examples and troubleshooting.

## Execution procedure

1. Route atomic operations with `backend_router.py`, considering `preferredBackend`, `requiredOutputs`, `nativeFormatRequired` and `fallbackPolicy`. Prefer Automation-equivalent interfaces; use native C++ only for explicitly required unmanaged `I*` pointer semantics. Event subscriptions, PropertyManagerPage, TaskPane and persistent UI use `solidworks_addin_ui_events`, preferably C# Add-in. Check HKLM registration, 64-bit TLB registration and `host-status.json`; `LoadAddIn=0` alone is insufficient. SW2026 PMP handlers must be public, COM-visible and expose an `IDispatch` class interface.
2. Native formats require `sw_preflight.py`. Request authorization for missing dependency installation; missing SOLIDWORKS blocks the native stage.
3. For eligible open-format jobs run `python scripts/cad_studio.py write-open-format --input model.cadstudio.json --out-dir output`.
4. For DFM screening run `python scripts/cad_studio.py check-dfm --input model.cadstudio.json --output output/dfm_report.json --process machining`. Supplier `--profile supplier.json` and `--brep-evidence brep.json` are supported. Missing material, thickness, K-factor, kerf, molding space or required B-Rep evidence returns `blocked`. Passing rules still require human review.
5. Prefer `SolidWorksSession()` for connect/open/new/save/export; compose lower-level `sw_connect.py` and `sw_part.py` functions when needed.
6. For natural-language requests, incomplete parameters or knowledge/template-driven planning, read `subskills/solidworks-vibecad/SKILL.md` and produce `design_plan.json` plus an execution outline.
7. For CNC mounts, connector blocks and brackets with many fillets/chamfers, read `subskills/solidworks-fillet-chamfer-cnc/SKILL.md`. Use base body → outer fillets/chamfers → holes/slot cuts → hole-mouth chamfers → review.
8. For screw/threaded/tapped holes and M3/M4/M5/M6/M8 blind/through holes, read `subskills/solidworks-threaded-holes/SKILL.md`. Use parameter/position checks → tap-drill hole → actual Metric Tap Thread → CosmeticThread/evidence helix fallback → mouth chamfer → rebuilt feature evidence → properties/review. Hole Wizard, external, imperial/pipe threads and modification of existing holes remain pilot.

**Gear routing gate:** For a gear solid, first read `references/gears.md`; a Gear Mate does not create gear geometry. Use `scripts/sw_gear.py` only for standard external spur gears with known module, tooth count, pressure angle, face width and bore. Manufacturing parameters must be supplied; explicit defaults are acceptable only for a visual demo. Helical, bevel, internal, rack, worm, profile-shifted or production tooth modification/backlash requirements need a dedicated route or human review. Gear coupling/transmission/mating requests use `sw_assembly.add_gear_mate_by_cylinders()`.

9. For blind/through/counterbored/countersunk holes, obround slots and hole patterns, read `references/complex-hole-features.md` and prefer `scripts/sw_hole_features.py`. Cross-check creation parameters with `collect_geometry_measurements()`, `validate_hole_positions()` and section views.
10. For part/assembly/GB/T drawings, dimension chains, hole tables, BOMs, title blocks and drawing review, read `subskills/solidworks-engineering-drawing/SKILL.md`; it consumes root model/hole/property evidence. AutoCAD DWG/DXF, line-art conversion, batch edits and native previews use `subskills/autocad-automation/SKILL.md`. Manufacturing drawings for mechanical/3D-printed parts must specify every hole, slot, interface, port and screw boss with size, quantity and position; use tables for crowded views, not long leaders in place of dimensions.
11. For faithful product appearance/1:1 reproduction, read `references/mesh-reference-import.md`. Prefer public mesh/blueprint references over repeatedly refining a low-fidelity draft; import OBJ/STL through `scripts/sw_import_mesh_reference.py`.
12. Guard model-generated VBA with `sw_macro_guard.py` for model routing, validation, retries and local fallback templates.
13. Save/export through `session.export()` or `sw_export.py`.
14. Export previews and review with `sw_review.py`; use a desktop screenshot when available for visual verification.
15. Sheet metal, weldments, complex surfaces, molds, Routing, Simulation/FEA, complex Motion and configuration families require `sw_capability_probe.py` and `references/complex-mechanical-routing.md`. Use the corresponding Routing/FEA/advanced-geometry commands above. Successful FEA or advanced-surface solving still yields `review_required`.
16. For enterprise/project mechanical knowledge read `references/enterprise-agent-rag.md`. Default to local knowledge; cloud RAG needs explicit enablement, `external_network` declaration and human approval.
17. Requests spanning more than two engineering domains among parts, holes/fillets, mates, Motion, drawing/BOM and multi-format delivery use `apps/desktop/cad_workbench/engineering_orchestrator.py` to produce a stage DAG. Serialize dependent CAD writes; save independent stage artifacts and acceptance evidence. Local changes replan affected stages and successors, not the entire project in one giant prompt.

### Manufacturing drawing baseline

1. A readable illustration is not manufacturing evidence. Holes, slots, interfaces, assembly holes and printed enclosures require overall dimensions, wall/base thickness, feature sizes and positions.
2. When GB/T or Chinese national drawing conventions are explicitly requested, preserve that standard: correct sheet/frame/title block, FangSong lettering where required, line classes, center/hidden lines, real dimensions and technical requirements. Turkish/English localization does not silently convert GB/T to ISO.
3. Leaders provide local explanations; they cannot replace dimension chains or cross views/holes/center lines/dimension text/title blocks.
4. Dense holes/slots require tables with location, specification, quantity and positioning information.
5. Inspect previews before delivery and repair missing dimensions, overlaps or line collisions before reporting completion.

### Mesh references

For vehicles, motorcycles, appliances or other products where close resemblance is requested:

1. Obtain public 3D/multi-view references and record source, author, license and download date. Do not claim official Class-A or scan-grade quality.
2. Convert GLB/GLTF/FBX/BLEND to OBJ/STL first; prefer OBJ to preserve materials and use STL as a material-free fallback.
3. Check bounding-box axes and scale, then scale to known nominal dimensions.
4. Check optional `requirements-mesh.txt` dependencies before Python conversion/scaling and explain missing packages.
5. Use `sw_import_mesh_reference.py` and `LoadFile4(path, "r", create_empty_dispatch_variant(), errors)`; do not substitute `OpenDoc6()` or pass `None` to `LoadFile4()`.
6. Review four views and identifying details; a nonblank preview alone does not establish resemblance.
7. Editable engineering structure requires reverse reconstruction into parts; imported meshes are not parametric solids.

### Multicolor appearance

For bodies, glass, lamps, tires, wheels and other multicolor components:

1. Read `references/appearance.md` and use `sw_appearance.py`; ordinary Python lists are not valid COM material arrays.
2. Set document color on source parts, then component overrides where needed.
3. Read back RGB using `verify_appearance()` or `apply_component_palette()`; setter success alone is insufficient.
4. Call `model.ClearSelection2(True)` before saves/screenshots; `sw_review.save_preview()` already does this.
5. Visually confirm at least three intended colors where applicable; a nonblank preview is not a color check.
6. Run `tests/solidworks_appearance_regression.py` before regenerating a model with appearance problems.

### MCP server

For MCP/tool integration with Codex/Claude Desktop or reusable tools:

1. Read `mcp-server/README.md`.
2. For requested automatic multi-client configuration, the upstream registrar is `powershell -ExecutionPolicy Bypass -File mcp-server/register_all_ai_mcp.ps1 -InstallDependencies`; it attempts Codex, Claude Code/Desktop, Cursor and Windsurf and requires Node.js. For Codex-only registration, use the documented dedicated registrar.
3. Local stdio server: `python mcp-server/server.py`.
4. Use `cadstudio_write_open_format` for eligible headless jobs. DFM/Routing/FEA/advanced geometry use the matching `cadstudio_*` tools listed in the MCP README; native operations use allowlisted `solidworks_*` tools.
5. New tools should reuse verified `scripts/sw_*.py` wrappers, not expose arbitrary Python/VBA execution.
6. Serialize SOLIDWORKS COM operations; the server's global lock reduces desktop-session conflicts.
7. `examples/08_mini_fan_motion_assembly.py` demonstrates modeling, assembly, mates and Motion Study; it does not promise perfect cosmetic fillets/chamfers.

### Moving assemblies

For draggable motion, hinges, gear coupling or real mechanical mates:

1. Read the motion-assembly workflow in `references/assembly.md`; explicit Motion Study/motor requests also require `references/motion-study.md`.
2. Reuse `resolve_component()`, `get_assembly_entity()`, `find_largest_cylinder_face()`, `add_mate5_checked()`, `add_concentric_mate_by_cylinders()` and `add_gear_mate_by_cylinders()`.
3. Rotating parts use concentric mates with `lock_rotation=False`; avoid fully fixing shafts/gears/covers with three plane mates.
4. Use actual Gear Mate features for transmission, not scripted animation presented as mechanical mating.
5. Verify real `MateConcentric`, `MateGearDim`, etc. under MateGroup using `collect_mate_feature_summary()` or feature-tree traversal.
6. For actual studies use `sw_motion.create_motion_study()`, `add_constant_speed_rotary_motor_by_cylinders()` and `calculate_and_play()`.
7. After calculation, use `sw_motion.validate_motion_studies()` or `solidworks_validate_motion_study` to check type, duration, motor count, results and `results_out_of_date=False`. A timeline, animation or `Calculate=True` alone is insufficient.
8. Additional scripted pose/Mate Controller animation is permitted for demonstrations, but distinguish it from interactive freedom; final draggable behavior must be verified in SOLIDWORKS.

## GPT / Kimi / Claude macro generation

Use `scripts/sw_macro_guard.py` for model-generated VBA:

1. GPT uses the concise prompt; Kimi/Claude/unknown models use strict VBA-only output constraints.
2. Failed/unparseable output can fall back to built-in templates matching request keywords such as cube, cylinder, extrusion and sketch.
3. Check `SldWorks`, `ModelDoc2`, `Sub` and `End Sub` before execution; retry invalid output.
4. Recommended timeout is 30 seconds per request, with 1–2 parsing retries and stronger formatting instructions.

```python
from sw_macro_guard import build_prompt, fallback_macro_for_request, validate_vba_macro
prompt = build_prompt("Create a 50 mm cylinder", model_name="claude")
macro = fallback_macro_for_request("Create a 50 mm cylinder")
result = validate_vba_macro(macro)
assert result.ok, result.issues
```

## Unwrapped APIs

1. Read `references/api-lookup.md`, then official SOLIDWORKS API documentation or the local SDK to verify signatures, parameter meanings, enums, returns and version differences.
2. Verify rather than guess long COM signatures, VARIANT/by-ref arguments, enums, selection marks and SaveAs interfaces.
3. Keep a minimal runnable script and check each return for `None` / `False`.
4. Actually execute the implementation, save/export the target and generate previews/review with `sw_review.py`.
5. Record new pitfalls, error codes and compatible/stable wrappers in the appropriate reference; move reusable logic into `scripts/`.

## Result review

After CAD generation, modification, import or export, unless explicitly waived by the user:

1. Check COM returns, feature objects, save/export results and output sizes.
2. Refresh with `model.ForceRebuild3(False)` and `model.ViewZoomtofit2()`.
3. Use `scripts/sw_review.py::run_review()` for isometric/front/top/right previews and `*_review_report.json`.
4. Inspect `evaluation.status`, `evaluation.issues`, `checks` and images for body existence, proportions/orientation, missing parts, overlap/floating parts, correct names and output paths.
5. Repair and regenerate before reporting problems as solved; a successful save alone is insufficient.

```python
from sw_review import run_review
model.ForceRebuild3(False)
report, report_path = run_review(
    model, r"C:\temp\review", basename="car",
    expected_outputs=[r"C:\temp\car.sldprt", r"C:\temp\car.step"],
)
print(report_path)
print(report["evaluation"])
```

## Important API details

- **Units:** SOLIDWORKS API lengths are meters. `mm(50)` produces 0.05 m; `deg(90)` converts degrees to radians.
- **Version:** `SldWorks.Application` attaches automatically; verify the actual version and capability support rather than assuming universal compatibility.
- **Selection:** Prefer object-level `Select2()` when COM objects are available. Planes can use `SelectByID2("PLANE")`; sketch selection must not depend only on `SelectByID2("SKETCH")`.
- **Sketches:** `with sketch(model, "Front Plane") as sketch_name:` handles entry/exit and caches object references for localized SW2024 selection compatibility.
- **Components:** Prefer `sw_assembly.add_component()`; when localized SW2024 `AddComponent4` returns None, its fallback uses AddComponent5, silent part opening and assembly reactivation.
- **Appearance:** Use separate parts for strong multicolor requirements. Marshal material arrays as `SAFEARRAY(double)` and verify RGB.
- **VARIANT:** Wrap by-ref integers with `VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)`.
- **Plane names:** `start_sketch()` recognizes English Front/Top/Right Plane names and legacy localized aliases. Compatibility aliases are data, not supported presentation languages.
- **Sketch coordinates:** Local to the sketch plane, in meters.
- **Moving assemblies:** Resolve components before selecting mate entities; `GetCorresponding()` maps part geometry into assembly context. Concentric mates do not lock rotation by default.
- **Motion Study:** Load `swmotionstudy.tlb`. In pywin32, CreateMotionStudy/Activate/Calculate may appear as properties; use `sw_motion.motion_member()`.
