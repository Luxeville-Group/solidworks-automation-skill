# Motion Study and Rotational Motor Automation

This reference records Motion Study automation tested with SolidWorks 2024 SP3.1, Python 3.13 and pywin32. It creates actual studies and motor features instead of substituting scripted animation for mechanical degrees of freedom.

## Appropriate uses

- Requests to create a motion study, add a motor or produce constant 60 RPM rotation.
- Assemblies already contain real mates, with rotational freedom retained by concentric mates.
- A calculable, playable animation must exist in the SolidWorks study timeline.

Outside this route:

- For a simple angle-change demonstration, `sw_assembly.apply_component_transform_x()` can generate frames.
- For complex contact, friction, collisions or mechanical results, verify Motion / Simulation add-ins and licenses, then validate the specific scenario.

## Recommended workflow

1. Generate and save the parts.
2. Create an assembly and insert components.
3. Resolve components and select assembly-context entities using `GetCorresponding()`.
4. Apply a concentric mate to the rotating part with `lock_rotation=False`.
5. Use one planar coincident/distance mate for axial location; do not fully lock the rotating part with three planes.
6. Fix stationary components and leave rotating components floating.
7. Create a study using `sw_motion.create_motion_study()`.
8. Add a constant-speed rotational motor with `add_constant_speed_rotary_motor_by_cylinders()`.
9. Calculate and play with `calculate_and_play()`.
10. Call `validate_motion_studies()`; only `validation.status == "pass"` may proceed to delivery.

## Minimal example

```python
import sys
sys.path.insert(0, r"C:\Users\you\.codex\skills\solidworks-automation\scripts")

from sw_connect import mm
from sw_motion import (
    create_motion_study,
    add_constant_speed_rotary_motor_by_cylinders,
    calculate_and_play,
    validate_motion_studies,
)

# Preconditions: asm is an assembly; stand_comp is a stationary shaft/bracket; impeller_comp is the impeller.
# The impeller is concentrically mated to the shaft without locking rotation.
study = create_motion_study(
    asm,
    name="Impeller_60RPM_Loop",
    duration=4.0,
)

motor = add_constant_speed_rotary_motor_by_cylinders(
    study,
    shaft_component=stand_comp,
    rotor_component=impeller_comp,
    shaft_radius=(mm(4.5), mm(5.5)),
    rotor_radius=(mm(10.5), mm(11.5)),
    rpm=60.0,
    name="ImpellerMotor_60RPM",
)

ok = calculate_and_play(study)
audit = validate_motion_studies(
    asm,
    study_name="Impeller_60RPM_Loop",
    minimum_duration_seconds=4.0,
    minimum_motor_count=1,
    require_results=True,
)
print(ok, audit["validation"])
```

## Result acceptance gates

`validate_motion_studies()` checks all of:

- The target study exists and is readable.
- `swmotionstudy.tlb` is loaded.
- Study duration meets the requirement.
- Motor count meets the requirement.
- Optional `StudyType` matches the task.
- `GetResults()` returns a result object.
- `results_out_of_date` is explicitly `False`.

A timeline, motor icon, playable animation or `Calculate=True` alone cannot replace this evidence. Any failed check must block delivery through the Reviewer Gate and request recalculation or DOF repair.

## Type libraries and dynamic COM pitfalls

Motion Study's `IMotionStudyManager` resides in `swmotionstudy.tlb`, not the main `SolidWorks.Interop.sldworks.dll` library. Without generated pywin32 wrappers, dynamic objects can behave unexpectedly:

- `model.Extension.GetMotionStudyManager` appears as a property, not a method.
- `motion_mgr.CreateMotionStudy` can be a property whose read creates a study; calling `CreateMotionStudy()` then reports member not found.
- `study.Activate`, `study.Calculate`, `study.Play` can be Boolean properties rather than methods.
- `study.SetDuration()`, `study.CreateDefinition()`, `study.CreateFeature()` generally remain methods.

Prefer `sw_motion.motion_member()` and `sw_motion.ensure_motion_type_library()` for stable access.

```python
from sw_motion import ensure_motion_type_library, motion_member

ensure_motion_type_library()
motion_mgr = motion_member(asm.Extension, "GetMotionStudyManager")
study = motion_member(motion_mgr, "CreateMotionStudy")
motion_member(study, "SetDuration", 4.0)
calculated = motion_member(study, "Calculate")
```

## Key rotational-motor APIs

Create a rotational motor with `MotionStudy.CreateDefinition(swFmAEMRotationalMotor)`:

```python
SW_FM_AEM_ROTATIONAL_MOTOR = 78
motor_data = study.CreateDefinition(SW_FM_AEM_ROTATIONAL_MOTOR)
motor_data.DirectionReference = shaft_axis_face
motor_data.ConstantSpeedMotor(60.0)  # RPM
motor_data.RelativeComponent = stand_comp
motor_data.Location = rotor_face
motor_data.LoadReferences = (rotor_face,)
motor_feature = study.CreateFeature(motor_data)
```

Observed behavior:

- An assembly-context cylindrical face on the stationary shaft is the most stable `DirectionReference`.
- `LoadReferences` accepts tuple/list; some environments require `VARIANT(VT_ARRAY | VT_VARIANT, [...])` or `VT_DISPATCH`.
- `ConstantSpeedMotor(60.0)` is RPM; do not convert to rad/s.
- If `CreateFeature()` returns `None`, verify both direction and load references are assembly-context entities.

## Relationship to mate DOFs

A Motion Motor can drive only a component retaining rotational freedom. Common failures:

- The impeller was fixed with `FixComponent()`.
- The concentric mate used `lock_rotation=True`.
- Additional coincident plane mates locked axial rotation.
- A part-context face was selected instead of an assembly-context face from `component.GetCorresponding()`.

Recommended constraints:

- Fix stationary bases, columns and guards.
- Rotating components use only a concentric mate plus one axial locating mate and remain floating.
- Concentric mate: `lock_rotation=False`.

## Session cleanup and duplicate document titles

Repeated debugging can leave duplicate-title documents in SolidWorks and cause:

```text
OpenDoc6 errors=65536
swFileWithSameTitleAlreadyOpen
AddComponent4 returns None
```

Stable approach:

1. Before a batch, confirm whether existing documents may be closed; unattended workflows may use `sw.CloseAllDocuments(True)`.
2. After saving each part, close it with `sw.CloseDoc(title)` and later insert it by path.
3. `OpenDoc6` error `65536` usually means the same title is already open; do not immediately label the file corrupt.

## Test record

Environment:

- SolidWorks Premium 2024 SP3.1
- Python 3.13
- pywin32 dynamic COM

Completed case:

- Four-part desktop mini cooling fan: base, center column, bladed impeller and circular front guard.
- Assembly mates: base/column concentric + coincident; impeller/shaft concentric without rotation lock + axial coincident; front guard concentric + angular location.
- Fixed state: base, column and guard fixed; impeller floating.
- Motion Study: `Impeller_60RPM_Loop`, motor `ImpellerMotor_60RPM`, `Calculate=True`.

`examples/08_mini_fan_motion_assembly.py` is a repeatable baseline. It validates automatic modeling, assembly, real mates, Motion Study and review exports. Fillets/chamfers are not success criteria; blades use stable rectangles instead of complex curved surfaces.
