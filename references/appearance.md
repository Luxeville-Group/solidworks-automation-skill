# Appearance and Material Reference

## Core rule

Pass SolidWorks' nine-element material array to COM as `SAFEARRAY(double)`. Do not assign a plain Python
`list` directly to `MaterialPropertyValues`: pywin32 dynamic dispatch may marshal it incorrectly,
placing RGB in positions 2, 5 and 8 and leaving the model almost entirely green.

Stable wrappers are in `scripts/sw_appearance.py`:

- `material_variant()`: wraps the nine-element array as `VT_ARRAY | VT_R8`.
- `set_document_appearance()`: writes and reads back document-level RGB.
- `set_feature_appearance()`: writes and reads back feature-level RGB.
- `set_component_appearance()`: writes and reads back assembly-component RGB.
- `apply_component_palette()`: applies colors in bulk with a per-component audit.
- `verify_appearance()`: compares expected RGB with COM readback.

## Recommended usage

```python
from sw_appearance import (
    apply_component_palette,
    set_document_appearance,
    set_feature_appearance,
    verify_appearance,
)

set_document_appearance(model, "iron_red")
set_feature_appearance(feature, "armor_gold")
assert verify_appearance(model, "iron_red")["ok"]

reports = apply_component_palette([
    (body_component, "aqua_blue"),
    (glass_component, "glass_tint"),
    (rear_light_component, "signal_red"),
    (rim_component, "silver"),
])
assert all(item["ok"] for item in reports)
```

## Preset colors

| Name | Description |
|---|---|
| `iron_red` | Dark red armor |
| `armor_gold` | Gold armor |
| `dark_gunmetal` | Dark metal/joints |
| `arc_blue` | Blue luminous parts |
| `silver` | Silver metal |
| `black` | Black |
| `white` | White |
| `aqua_blue` | Aqua-blue body color |
| `glass_tint` | Dark glass |
| `signal_red` | Tail-light/warning red |
| `light_cyan` | Light-blue luminous parts |
| `tire_black` | Tire black |
| `graphite` | Graphite gray |

## Verified API signatures

Reflection results from the local SolidWorks 2024 SP3.1 `SolidWorks.Interop.sldworks.dll`:

```text
IModelDoc2.MaterialPropertyValues = Object
IModelDocExtension.SetMaterialPropertyValues(Object, Int32, Object) -> void
IFeature.SetMaterialPropertyValues(Object) -> bool
IFeature.SetMaterialPropertyValues2(Object, Int32, Object) -> void
IComponent2.SetMaterialPropertyValues2(Object, Int32, Object) -> void
IComponent2.GetMaterialPropertyValues2(Int32, Object) -> Object
```

Configuration options: `swThisConfiguration=1`, `swAllConfiguration=2`,
`swSpecifyConfiguration=3`. For setters returning `void`, no COM exception means the call completed;
do not judge success with `bool(method(...))`. Final acceptance requires `verify_appearance()` readback.

## Multicolor assembly workflow

1. Set and save the base document-level appearance in each source part.
2. Apply component-level color overrides after insertion as needed.
3. Read back the first three RGB values after every write; stop immediately on mismatch.
4. Call `assembly.ClearSelection2(True)` before saving.
5. Clear selection and redraw before previews so green selection highlighting does not cover the actual appearance.
6. Inspect at least one color isometric view and one orthographic view showing lights/wheels where applicable.

## Stability guidance

- Coloring multiple features in one part can depend on SolidWorks version, display state and feature merging.
- For models with strict color requirements, prefer separate parts with document-level appearances.
- For complex projects, deliver assemblies whose component structure expresses colors, materials and replaceable modules.
- A setter that throws no exception does not prove the color is correct; read back RGB.
- Clear selected components/faces/edges before screenshots: green selection highlighting can mislead visual review.
- After generation, export previews with `sw_review.py` and verify visible colors and hierarchy.
