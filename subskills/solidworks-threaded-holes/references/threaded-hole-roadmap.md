# SolidWorks threaded-hole roadmap

This roadmap distinguishes useful extensions from stable supported features. Do not add a `verified` capability claim until its acceptance gates pass.

## P0: Core correctness (completed)

- Replace through tap-drill holes with true `Through All` cuts.
- Validate finite/positive values, depth chains, hole boundaries and tap-drill diameter below nominal diameter.
- Enable real internal-thread ThreadFeatureData using `Metric Tap` and selection mark `1`.
- Support tolerance properties, right/left hand and out-of-table ISO metric sizes with explicit user-supplied tap-drill diameters.
- Read back the feature tree after rebuild, separating API attempts from final evidence.
- Preserve actual pitch in the 3D helix and separate evidence previews from clean delivery previews.

## P1: Native hole semantics and existing parts (highest priority)

### 1. Hole Wizard5 / WizardHoleFeatureData2

Goal: when standard hole callouts, hole tables or database-driven thread sizes are required, prefer native Hole Wizard tapped holes over a tap-drill + Thread combination.

Implementation needed:

- Wrap `HoleWizard5` and `IWizardHoleFeatureData2`, explicitly specifying ISO/DIN/GB/ANSI standard, fastener type, size, hole depth, tapping depth, tap-drill diameter and tolerance class.
- Probe local Hole Wizard/Toolbox database paths and available sizes; do not guess enum values or size strings.
- Read back `ThreadDepth`, `TapDrillDiameter`, `ThreadClass` and hole-position points from saved feature data.
- Extend the SW2024/SW2026 version and UI-language test matrix; add Turkish UI coverage for this fork.

Acceptance: at least three consecutive successes each for blind and through holes; standard, size, tap-drill diameter, thread depth and position remain readable after reopening SLDPRT; drawing callouts match the model.

### 2. Existing-part modification and multiple hole positions

Goal: extend the template from new rectangular samples to semantic entity selection and multiple-hole creation in existing SLDPRT files.

Implementation needed:

- Use `sw_entity_reference.py` to select faces by normal, bounds, coordinate system and persistent reference, rather than front/top/right planes plus fixed offsets.
- Support explicit position lists, rectangular/circular patterns, groups of different hole sizes and separate evidence for each hole.
- Detect intersections, edge clearances, thin walls and existing-feature conflicts before modifying; partial failures must not leave a half-completed model.

Acceptance: cover planar, side, inclined and multibody parts; cross-check every hole's position, axis, diameter and depth using both B-Rep and the feature tree.

## P2: Thread-standard data

Goal: replace the small inline coarse-thread dictionary with versioned data tables.

- ISO metric coarse/fine threads, with separate tap-drill sizes for cutting and forming taps.
- UNC/UNF/UNEF, NPT/NPTF and BSPP/BSPT; do not reuse `Metric Tap` profiles for imperial or pipe threads.
- Tolerance class, hand, multistart threads, material/thread percentage and tap-drill selection sources.
- Record standard edition, source, units, scope and a manual-confirmation flag for every entry.

Acceptance: schema validation, boundary tests, unit-conversion tests and sample comparisons against authoritative tables all pass.

## P3: Manufacturing realism

- Standard blind-hole drill-point angles, distinguishing full cylindrical depth from total depth to the drill tip.
- Effective full-thread depth, tap lead, incomplete threads, bottom relief and chip allowance.
- Determine mouth chamfers from nominal diameter, standard and requested process instead of generalizing one M6 example.
- Optional explicit thread-profile sweeps only for 3D printing, rendering or explicit customer requirements; require separate performance, self-intersection, file-size and STEP-reopen gates.

Acceptance: parameter evidence agrees with B-Rep depth measurements; flat-bottom holes are not represented as drilled-hole geometry; record every manufacturing assumption in the delivery report.

## P4: Drawing, PMI and CAM evidence

- Generate and read back thread-hole callouts following applicable GB/ISO conventions, including size, tolerance, depth, count and locating dimensions.
- Integrate with `solidworks-engineering-drawing` hole/hole-slot tables; model properties, drawing text and B-Rep evidence must agree.
- Probe STEP AP242/PMI and CAM feature recognition separately; a thread solid in ordinary STEP does not establish automatic recognition of a tapping operation.

Acceptance: callout content is readable as structured data, and keywords/dimensions are checked in actual PDF/drawing deliverables; a successful API call does not establish readability.
