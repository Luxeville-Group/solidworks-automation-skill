# SolidWorks threaded-hole test lessons

## Results from 2026-08-29

The earlier `CreateFeature(ThreadFeatureData)` returns of `None` were primarily caused by incomplete creation data, not simply COM instability:

- After `InitializeThreadData()`, `Type` is empty by default; metric internal threads require `Type="Metric Tap"`.
- The Thread Profiles directory must contain `Metric Tap.SLDLFP`. Official documentation permits a profile name without path or extension as `Type`.
- Select the planar circular edge with mark `1`, then set `IThreadFeatureData.Edge`.
- When the planar circular edge is already provided, do not also assign it to `StartEntity`.
- `IThreadFeatureData` has no `LoadReferences(edge)` creation step; do not call it.
- The tap-drill cylinder already determines thread diameter; do not force `DiameterOverride=True` with the nominal major diameter.

The corrected M6×1 right-hand internal thread passed native tests on SolidWorks 2026 SP01.1:

| Scenario | Tap-drill hole | Thread end condition | Result |
|---|---|---|---|
| Blind hole in 16 mm body, 12 mm thread depth | Ø5.0, 13 mm blind depth | `BlindDepth=12 mm` | `real-thread-verified`, review `pass/100` |
| Through hole in 16 mm body | Ø5.0, `Through All` | `Revolutions=16` | `real-thread-verified`, review `pass/100` |

## Official API references

- [Thread Features and ThreadFeatureData Objects](https://help.solidworks.com/2026/English/api/sldworksapiprogguide/Overview/Thread_Features_and_ThreadFeatureData_Objects.htm)
- [IThreadFeatureData.Type](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IThreadFeatureData~Type.html)
- [IThreadFeatureData.Edge](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IThreadFeatureData~Edge.html)
- [swThreadEndCondition_e](https://help.solidworks.com/2026/English/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swThreadEndCondition_e.html)
- [InsertCosmeticThread3](https://help.solidworks.com/2017/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeatureManager~InsertCosmeticThread3.html)
- [swCosmeticEndConditions_e](https://help.solidworks.com/2026/English/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swCosmeticEndConditions_e.html)
- [BlankSketch](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~BlankSketch.html)

## Correct end conditions

Tap-drill cuts, real Thread and CosmeticThread use three different enum groups; do not mix them:

```text
Tap-drill FeatureCut4:
  Blind      = swEndCondBlind (0)
  ThroughAll = swEndCondThroughAll (1)

ThreadFeatureData:
  Blind       = swThreadEndCondition_Blind (0)
  Revolutions = swThreadEndCondition_Revolutions (1)
  UpToSelect  = swThreadEndCondition_UpToSelection (2)

CosmeticThread:
  Blind   = swEndConditionBlind (0)
  Through = swEndConditionThrough (2)
```

A through tap-drill hole must use `FeatureCut4(..., T1=1, ...)`. A blind cut with thickness + 1 mm may appear to pass through, but its feature semantics, later editing and drawing recognition are incorrect.

## Minimum parameter validation

Reject before COM calls:

- NaN/infinity and nonpositive body dimensions, tap-drill diameters, depths or chamfers.
- Tap-drill diameter greater than or equal to nominal diameter.
- Thread depth exceeding blind tap-drill depth, or through-thread depth exceeding plate thickness.
- Hole centers outside the body or insufficient boundary allowance for thread major diameter and mouth chamfer.
- An out-of-table metric pitch without explicit `--tap-drill`. Material, tap type and thread percentage affect tap-drill size; a generic `D-P` estimate is not a confirmed value.

## Feature-persistence evidence

A non-null Thread/CosmeticThread COM object establishes an attempted creation, not final evidence. After `ForceRebuild3(False)`, traverse `FirstFeature/GetNextFeature` and recursively `GetFirstSubFeature/GetNextSubFeature`, producing:

- `thread_attempts`: each API attempt's result and failure reason.
- `thread_evidence`: whether the tap-drill cut, chamfer, real Thread, CosmeticThread and 3D evidence sketch remain in the feature tree.
- `thread_status`: `real-thread-verified` / `cosmetic-thread-verified` / `visible-helix-verified` based on post-rebuild evidence. Block delivery if only custom properties remain.

Official SolidWorks examples identify CosmeticThread as a hole/cut subfeature. Top-level traversal alone can wrongly report a persistent CosmeticThread as missing; current evidence collection includes subfeatures.

## The 3D helix is evidence only

The previous implementation rounded `thread_depth / pitch` to an integer number of turns, changing pitch. For example, 16 mm depth at P=1.25 mm requires 12.8 turns, not 13. The current implementation uses fractional turns and 32 segments per turn, preserving pitch within the hole depth.

SolidWorks displays visible 3D sketch lines through solids, producing dashed lines on outer walls in standard isometric previews. Generate `*_thread_evidence.bmp` first, then hide the evidence sketch with `BlankSketch()` so standard previews show a clean model.

A 3D sketch is not a machinable thread profile; do not describe it as a CAM-ready solid thread.

## Manufacturing details not covered

Blind tap-drill holes currently have flat bottoms; standard drill points, effective full-thread depth, incomplete threads, tap overrun and chip space are not modeled. Tap-drill + Thread provides useful CAD/drawing semantics but does not establish a complete tapping-process design without process-engineering review.

See [threaded-hole-roadmap.md](threaded-hole-roadmap.md) for extension order and acceptance gates.
