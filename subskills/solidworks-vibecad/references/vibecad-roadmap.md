# VibeCAD engineering roadmap

## Direction

The aim is to make repeated mechanical-design work reusable through:

```text
Domain knowledge + parameter schemas + prompt templates + stable API wrappers + automated review.
```

The LLM interprets intent and fills parameters; SolidWorks API executes deterministically; the knowledge base supports engineering checks; the review chain detects false success.

## Phase 1: Complete planning workflow

Completed:

- CNC mounting-base example brief.
- Parametric design-plan JSON.
- Initial manufacturing-rule knowledge base.
- LLM planner prompt template.
- SolidWorks execution outline.
- JSON and Python syntax validation.

Possible additions:

- More part families: connector blocks, L-brackets, shafts and sheet-metal enclosures.
- More standard-component rules: bearings, couplings, motor flanges, countersunk screws and locating pins.
- Stricter schemas: dimension ranges, hole spacing, edge clearances and process constraints.

## Phase 2: Native SolidWorks executor

Prioritize the `cnc_mount` executor:

1. Run `sw_preflight.py`.
2. Read `design_plan.json`.
3. Create a part with `SolidWorksSession()`.
4. Create the planned base plate, holes, pockets, fillets and chamfers.
5. Save `SLDPRT` and export `STEP`.
6. Call `sw_review.run_review()`.
7. Read the review report and retry with bounded fallback if it fails.

Key principles:

- Check the return values of all SolidWorks API calls with long parameter lists.
- Convert all mm values to meters through `sw_connect.mm()`.
- Prefer object-based `edge.Select2()` for fillet/chamfer edge selection.
- For threaded holes, first ensure correct tap-drill geometry, mouth chamfer and properties.

## Phase 3: Expand the knowledge base

Prioritize these frequent rules:

- M3/M4/M5/M6/M8/M10 coarse/fine threads and tap-drill diameters.
- Recommended clearance-hole, counterbore and countersink dimensions.
- CNC minimum wall thickness, minimum fillet radii and chamfer defaults.
- Sheet-metal bend radius, K-factor and flat-pattern allowance.
- Bearing housing bores, tolerance fits and retaining-ring grooves.
- Motor mounting-hole spacing and flange standards.

## Phase 4: Interactive entry points

Possible interfaces:

- CLI: generate a plan and model from one brief.
- MCP: let Codex/Claude call SolidWorks tools.
- Local web UI: enter requirements, adjust parameters and preview review results.
- Template library: save successful cases as reusable design templates.

## Metrics

- Percentage reduction in repeated modeling time.
- First-attempt modeling success rate.
- Automated-review pass rate.
- Number of manual edits.
- Template reuse count.
- Whether failure causes feed back into the knowledge base.
