# CAD Studio Weekly Delivery Plan

Commit each week only to capabilities that can be built, tested, and rolled back. Features without real CAD review remain `pilot`, `reference_only`, or `not_implemented`.

| Stage | Goal | Acceptance criteria |
|---|---|---|
| Week 1 | Local installation discovery, reliability diagnostics, STL/GLB/OBJ/DXF preview foundation | Correctly identify both CAD applications; pass Python/Rust/frontend tests, nonblank preview pixel checks, and narrow-window screenshots |
| Week 2 | Separate project/conversation/task/file/review modules and reduce `App.tsx` size | Project switching P95 < 150 ms; migration counts match; deleting projects does not delete CAD deliverables |
| Week 3 | SolidWorks parameter changes, batch export, properties/BOM, Pack and Go | Real golden-workflow regression; artifact ledger rejects old files |
| Week 4 | Drawing views/hole callouts, AutoCAD layer/dimension/frame checks, DXF layer preview | Pass headless DXF checks; AutoCAD 2024 ActiveX native drawing regression is currently `blocked` and must not be reported as passed |
| Week 5 | Assembly checks, configuration-family pilot, deliverable version comparison and regeneration | Complete evidence for capability gates, error codes, retries, and human review |
| Week 6 | 20 stability regressions, Windows self-hosted CI, installer regression, v0.4 release | No duplicate CAD instances or leftover Workers; golden-workflow first-run success rate reaches 90% |

## Week 1 results

- Detected local `E:\Solidworks\SOLIDWORKS\SLDWORKS.exe` and `D:\AutoCAD 2024\acad.exe`; unified discovery includes public desktop shortcuts and COM registration.
- `cad-studio doctor` reports product, version, source, and path; exported diagnostic packages retain only filenames from paths.
- Three.js loads STL, GLB/GLTF, and OBJ on demand; read-only DXF supports `LINE`, `CIRCLE`, and `LWPOLYLINE`.
- STEP/IGES and DWG are not parsed directly in the browser yet; SolidWorks/AutoCAD still exports native previews. Placeholders are not presented as real geometry.

## Week 2 results

- `App.tsx` decreased from 3968 to approximately 3479 lines. Projects, tasks, conversations, review, and delivery files moved into separate component/domain modules so subsequent CAD workflows do not keep accumulating in one file.
- The upper-left project entry supports search, archive/restore, duplication, renaming, and deletion with a second confirmation. Duplication copies only project metadata and directory references, not tasks, conversations, or CAD deliverables.
- The task sidebar supports bulk removal of terminal tasks; queued, running, and approval-pending tasks cannot be bulk deleted.
- SQLite retains the old `app_state` snapshot and adds entity indexes for projects, conversations, messages, and tasks. First launch migrates automatically; `app_store_migration_status` reports whether source and index counts match.
- Project switching passed Playwright acceptance at 1440×900 / 900×700 without console errors. Measured `performance.measure("cad-studio.project-switch")` was approximately 18 ms, below the 150 ms target.
- Verification: frontend build passed, 15 Rust tests passed, 118 Python tests passed. Real SolidWorks/AutoCAD artifact capabilities remain subject to the capability manifest and human review gates.

## Additional Week 3 results

- SolidWorks 2024 parts, dimension changes, property readback, assemblies, BOM, and batch export passed real regression.
- Early SW2024 Pack and Go regression enumerated only the top-level assembly. The wrapper therefore retains dependency auditing and fallback gates and prohibits labeling incomplete packages as successful deliveries.

## SolidWorks 2026 SP01.1 upgrade regression results

- Local installation discovery and COM type libraries now support `E:\SolidWroks2026\SOLIDWORKS\SLDWORKS.exe`, identifying revision `34.1.1`, `sldworks.tlb`, Motion, and Routing libraries.
- Drawing regression produced three real views and six real dimension entities in three consecutive runs; SLDPRT, SLDDRW, PDF, and nonblank previews all came from the current task.
- Final Pack and Go code passed natively in three consecutive runs. Each produced one SLDASM and two SLDPRT files, with `document_count=3`, status codes `[0,0,0]`, `missing_dependencies=[]`, and no staging fallback.
- The `comtypes` fallback preferentially attaches to the active instance and exits only instances explicitly created by the current run. The final two runs and cleanup run left no `SLDWORKS.exe` process.
- Overall `pack_and_go` remains `pilot`: complex external references, Toolbox, configurations, suppressed components, and associated drawings lack a repeated regression matrix.

## Additional Week 4 results

- DXF structural review schema 2.0 covers entity types, layers, bounding boxes, real DIMENSION entities, hole centers/diameters, frame candidates, and title-block candidates; rendered PNGs must contain nonblank pixels.
- AutoCAD 2024 COM version detection succeeded, but dynamic proxies for `Documents.Count`, `Documents.Add`, `Layers`, and `SelectionSets.Add` remain unstable. Native DWG drawing is `not_implemented` in `capabilities.yaml`, retaining interactive troubleshooting only; headless DXF is `pilot`.

## Week 5 results

- Assembly interference checks return structured `pass/warn/blocked` reports with counts, entries, and human review gates.
- Configuration-readback pilot returns the configuration list, active configuration, and limitations; batch design-table modification is not enabled.
- Deliverables use SHA-256 snapshots to compare added/removed/changed/unchanged files; regeneration preserves old artifacts, prohibits overwriting, and requires review.

## Week 6 results

- Added `scripts/stability_regression.py` to verify connection, cancellation, and exit-only-owned-instance constraints across 20 simulated lifecycles.
- Added `scripts/release_check.py` to check UI/Tauri/Cargo version consistency, unique capability IDs, and required files before release.
- Added `.github/workflows/windows-cad-regression.yml` for real regression only on Windows self-hosted machines with SolidWorks/AutoCAD preinstalled. Public GitHub runners never fabricate CAD pass results.

## Next four-week expansion results

- Drawing structural review returns sheets, views, real dimensions, tables, frame templates, and human-review fields. BOM adds traceability across models, drawings, and review reports.
- Automation Job 2.0 supports `drawingEvidence`, `bomEvidence`, `reviewFindings`, and `artifactRelations`; the worker maps domain evidence to `blocked`, `failed`, or `review_required` correctly.
- Delivery groups models, drawings, BOM, previews, and review reports; older Job 1.0 records remain readable through their original fields.
- AutoCAD backend states remain independent: headless DXF `pilot`, allowlisted scripts `pilot`, COM currently `blocked`. .NET SDK 8 is installed in the current user's directory, and the AutoCAD 2024 allowlisted plugin passed `NETLOAD`, real DWG save-and-reopen, PDF/PNG, and real-machine entity/layer/dimension review, promoting .NET to `pilot`.
- .NET regression permits only fixed `CADSTUDIOPROBE/CADSTUDIOCREATE` commands, with no arbitrary AutoLISP, SCR, or C# execution. AutoCAD 2025–2026 and desktop signed-plugin deployment require further verification.
- Added combined regression `tests/cad_studio_weekly_regression.py` and real SolidWorks drawing regression `tests/solidworks_week4_drawing_regression.py`; real CAD runs require explicit `--real-cad` or self-hosted CI.

## Next phase 1 results: versioned retries and delivery gates

- Before rerunning terminal tasks, save a read-only `runHistory` snapshot, keeping the latest 20 runs. Previous artifacts, errors, drawing/BOM evidence, and review records remain visible without recursively copying history.
- `retryPolicy` records the previous run ID, restart point, execution of only the failed stage and successors, preservation of old artifacts, and overwrite prohibition. The worker reuses the preceding engineering DAG; execution prompts also enforce versioned output.
- Delivery centrally derives `ready/review_required/blocked/failed/incomplete` from current artifacts, domain evidence, human review, and blocking reasons. File existence or a sidebar "Completed" status alone no longer means deliverable.
- Delivery adds current valid artifact counts, version history, SHA-256 change summaries, artifact traceability, and AutoCAD backend diagnostics. Model/drawing/BOM groups share one preview to avoid rendering duplicate large previews in narrow windows.
- `ai_team/delivery-gate-e2e.cjs` verifies review-pending state at 1440×900 and approved state at 760×900 in real Chromium, with no horizontal overflow or duplicate previews, and shows "This run is deliverable" only after human approval.

## Weeks 7–8 results: dual headless geometry backends

- `scripts/headless_occt_service.py` calls OCP in an independent subprocess, genuinely writes STEP, IGES, BREP, STL, OBJ, and GLB, and reads back validity, volume, bounding boxes, and topology statistics. Golden examples currently cover boxes, cylinders, Boolean unions, and cylindrical hole cuts.
- `scripts/headless_cad_writer.py` retains `.cadstudio.json`, versioned output, SHA-256, and the `producedThisRun` ledger. Missing OCP or unsupported features return `pilot/blocked`; partial meshes must not masquerade as complete solids.
- Seven OCP/open-format and versioned non-overwrite regressions passed; complex surfaces, sheet metal, weldments, and parametric features remain unimplemented.

## Weeks 9–12 results: headless 2D output

- DXF output now includes `OUTLINE/HOLES/CENTER/DIMENSION/FRAME/TITLE/TEXT` layers, real linear/diameter DIMENSION entities, hole centerlines, and optional A4/A3/A2/A1 GB/T-style frames and title-block fields.
- SVG, PDF, and PNG render from the same DXF through ezdxf/matplotlib by default; missing dependencies use an explicitly labeled simplified fallback. DWG is not written.
- Ten 2D output, DXF review, and PreviewScene regressions passed. Frame layout, localized fonts, and final manufacturability still require visual review by an engineer; the capability remains `pilot`.

## Weeks 13–16 results: first JS preview version

- `ModelViewport` supports on-demand Three.js loading of GLB/GLTF/STL/OBJ, standard views, orthographic/perspective cameras, selection, on-demand rendering, and resource disposal. Unavailable WebGL or decoding failure switches to the Manifest's PNG fallback.
- `DxfViewport` parses DXF/PreviewScene in a Worker and supports layer visibility, entity selection, dimensions/text, and Evidence references; `.scene.json` is included in frontend format routing.
- Real Chromium E2E covers desktop, 760px narrow, and 390px mobile windows, checking Canvas pixels, absence of horizontal overflow, source labels, and fallback images. An independent 20 MB/30 FPS benchmark is not complete, so that target is not claimed.

## Weeks 17–20 results: DXF inspection and demonstration boundaries

- Added `scripts/dxf_preview_scene.py` for read-only allowlisted parsing of LINE/CIRCLE/ARC/LWPOLYLINE/POLYLINE/TEXT/MTEXT/DIMENSION, capped at 50 MB and 200,000 entities. Unsupported entities generate warnings only; scripts are not executed.
- Added CLI `cad-studio preview-dxf` and MCP `cadstudio_build_dxf_preview_scene`. Output must be a new `.scene.json`; overwriting is rejected.
- Help adds seven fixed demonstrations (mounting plate, perforated bracket, CPU enclosure, small assembly, GB/T frame, sample FEA contour plot, and sample Routing path). All carry `demo-showcase/isDemo` and are excluded from delivery decisions.
- E2E verifies backend Scene JSON, the raw DXF Worker, seven demonstrations, and WebGL PNG fallback. FEA contour plots and Routing paths are educational demonstrations; real solving/native Routing requires the new gates and returns `blocked` when dependencies are unmet.

## Week 21 additions: DFM, Routing, FEA, and advanced geometry gates

- DFM adds supplier profiles, unit normalization, B-Rep evidence binding, and anti-fabrication checks; passing rules still yields `review_required`.
- Routing adds neutral endpoint/segment/length/bend-radius/collision-clearance/support-spacing/Routing-BOM review. SW2026 can discover the Routing type library, but native writing remains `blocked` without add-in or license evidence.
- FEA adds the FEA 1.0 Schema, CalculiX/Elmer preflight, and allowlisted CalculiX inputs. CalculiX 2.23 genuinely solved a restricted linear-static specimen and parsed displacement, stress, and convergence evidence.
- Advanced surfaces/molds add structured gates. OCP 7.9.3.1.1 genuinely generated and reopened STEP/BREP for a restricted closed ruled Loft; smooth Loft, continuity, and molds remain incomplete.
- CLI/MCP add allowlisted entry points `check-routing`, `routing-preflight`, `fea-preflight`, `prepare-fea`, `run-fea`, `review-advanced-geometry`, and `create-ocp-loft`, included in protocol verification.

## Weeks 1–20 audit conclusions

- Scope with real code and automated evidence: project/delivery gates, open-format geometry, basic 2D drawing structures, Preview Manifest/Scene, desktop and Skill/CLI/MCP entry points, browser preview fallback, DFM profile/B-Rep evidence, neutral Routing review, restricted CalculiX linear-static solving, and restricted OCP closed ruled Loft.
- Scope still needing real CAD self-hosted machines or human review: final visual quality of SolidWorks drawings/BOM, native AutoCAD DWG, smooth/continuous advanced surfaces, FEA mesh convergence and safety review, native SOLIDWORKS Routing writing, and the 20 MB/30 FPS performance target.
- Capabilities that have not passed these regressions are not displayed as complete or accepted as current-run artifacts by delivery gates.
