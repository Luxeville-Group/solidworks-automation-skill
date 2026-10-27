# Capability Routing for Complex Mechanical Models

## Probe before execution

Before a complex mechanical task, run:

```powershell
python scripts\sw_capability_probe.py --output capability_report.json
```

The report distinguishes:

- `type_library_present`: the installed software includes interface definitions.
- `implementation_status`: this skill has a wrapper validated by real regression tests.
- `ready_for_unattended_use`: unattended execution is permitted.

A type library does not prove license availability or verified automation. Never report `reference_only`, `not_implemented` or unsupported `pilot` operations as completed.

## Current capability levels

| Domain | Current level | Execution rule |
|---|---|---|
| Parametric parts, holes/slots, fillets/chamfers | Verified | Real COM allowed; parameter JSON and review report required |
| Assemblies, concentric/distance/gear mates | Verified | Check degrees of freedom and the mate feature tree |
| Motion Study rotational motors | Verified | After calculation, use `collect_motion_study_summary()` to check stale results |
| Drawings | Pilot | Human review of borders, views, dimension chains and GB/T format required |
| Configurations, design tables | Reference only | Regress a minimal sample before using customer models |
| Sheet metal | Pilot (SW2026 open-profile base flange) | Read back native SheetMetal/BaseFlange/FlatPattern and manufacturing parameters; verify reopen and DXF |
| Weldments | Pilot (SW2026 planar HSS frame) | Read back WeldmentFeature/WeldMemberFeat, body counts, lengths, quantities, angles, provenance properties and reopen evidence |
| Complex surfaces, molds | Pilot | `create-ocp-loft/create-ocp-surface` writes and reopens limited ruled/smooth Loft, Sweep/Knit/Thicken; G1/G2 and curvature radius use discrete samples only; complex paths and molds remain gated |
| Routing | Pilot | Run only `routing-preflight` or `check-routing`; native writes must be blocked without add-in/license evidence |
| Simulation/FEA | Pilot | `run-fea` handles limited linear/nonlinear statics and final-step contact penetration/pressure/slip; `run-fea-convergence` runs 3-8 linear or nonlinear mesh levels. Plasticity, contact and convergence all require engineering review |

## Complex parts

1. Divide the model into base bodies, primary functional features, interfaces, manufacturing features and appearance features.
2. Prefer stable references, fully constrained sketches and named features; do not rely on `Edge1`, screen coordinates or accidental selection order.
3. For complex surfaces, specify continuity targets (G0/G1/G2), parting/draft, thickness and manufacturing method.
4. For sheet metal, record thickness, material, inside bend radius, K-factor/bend table, bend direction and flat-pattern DXF.
5. For weldments, record profile standard, cut lengths, miters, welds, cut list and machining allowances.
6. For configurations/design tables, verify that every configuration rebuilds, has reasonable mass properties and produces collision-free output names.

## Complex assemblies and motion

1. Establish a degree-of-freedom budget: list each moving part's expected six DOFs, then remove them through individual mates.
2. Use a concentric mate plus axial location for rotating parts, without locking rotation; use slot/distance/limit mates for linear parts.
3. Contact, friction, springs, damping, gravity and collision are outside the currently verified rotational-motor scope.
4. Motion deliveries must include study type, duration, motor count, external-force count, feature count, result existence and `results_out_of_date`.
5. Playable animation does not prove a correct mechanism; also check interference, travel limits, speed/acceleration, driving force/torque and mate reactions.
6. Motion Analysis depends on add-ins and licensing. When unavailable, explicitly downgrade to Animation/Basic Motion instead of fabricating analysis results.

## Gates for new capabilities

1. Verify interfaces, signatures, enums and versions in the local `.tlb` or official SolidWorks API documentation.
2. Create a minimal regression sample; do not experiment directly on a user's complex assembly.
3. Wrap it in a narrow `scripts/sw_*.py` interface and check every COM return value explicitly.
4. Add static tests and real SolidWorks regression scripts.
5. Generate machine-readable acceptance evidence and multiple preview views.
6. Document failure modes in `references/troubleshooting.md` before marking the capability Pilot; mark it Verified only after repeated real regression passes.
