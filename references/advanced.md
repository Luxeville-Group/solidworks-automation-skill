# Advanced Features Reference

## Contents

- [Custom properties](#custom-properties)
- [Design tables and configurations](#design-tables-and-configurations)
- [Sheet metal](#sheet-metal)
- [Weldments](#weldments)
- [Surface modeling](#surface-modeling)
- [Simulation/FEA](#simulationfea)

---

## Custom properties

```python
# Get the property manager.
# Empty string = file-level properties; configuration name = configuration-specific properties.
props = model.Extension.CustomPropertyManager("")

# Read a property.
val = ""
resolved = ""
was_resolved = False
is_linked = False
result = props.Get6("Description", False, val, resolved, was_resolved, is_linked)
# resolved contains the evaluated value.

# Write/update a property.
# Types: 30=text, 2=number, 11=Yes/No, 64=date.
props.Add3("Description", 30, "Main shaft Rev A", 1)  # 1=overwrite
props.Add3("Material", 30, "Steel 1045", 1)
props.Add3("Weight", 2, "2.5", 1)
props.Add3("PartNumber", 30, "PN-001-001", 1)

# Delete a property.
props.Delete2("OldProperty")

# Get all property names.
count = props.Count
names = props.GetNames()
```

## Design tables and configurations

### Configuration management

```python
from sw_document_data import (
    activate_configuration,
    create_configuration,
    inspect_configurations,
    update_dimension_mm,
)

# Create and activate using the official AddConfiguration3; reuse an existing name idempotently by default.
created = create_configuration(
    model,
    "Machining",
    comment="CNC operating condition",
    alternate_name="MACHINED",
)

# Use official ShowConfiguration2; verify the active configuration name rather than the COM return value alone.
activated = activate_configuration(model, "Machining")

# Use explicit VT_ARRAY|VT_BSTR for the target configuration; lengths are converted to the API's internal meters.
dimension = update_dimension_mm(
    model,
    "D1@Boss-Extrude1",
    50.0,
    configuration_mode="specific",
    configuration_names=["Machining"],
)

evidence = inspect_configurations(model)
```

Configuration creation, switching, configuration-level dimensions/properties and save/reopen readback have been validated on SW2026. `AddConfiguration3`
automatically activates the new configuration, so a repeated `ShowConfiguration2` call may return `False`. The executor records the raw
return value but uses `ConfigurationManager.ActiveConfiguration.Name` readback and rebuild results as success evidence.
Design tables, derived configurations, display states and large suppression matrices remain outside the validated `pilot` scope.

### Design tables

```python
# Insert a design table from Excel.
design_table = model.InsertFamilyTableOpen(excelFilePath)

# Close after editing.
model.CloseFamilyTable()

# Update the design table.
model.InsertFamilyTableEdit()
```

## Sheet metal

### Basic operations

```python
from sw_sheet_metal import BaseFlangeSpec, create_base_flange

# Create and exit an open or closed sketch before using the modern FeatureData API.
feature = create_base_flange(
    model,
    sketch_name,
    BaseFlangeSpec(
        thickness=0.002,
        bend_radius=0.0025,
        depth=0.100,
        k_factor=0.42,
    ),
)
```

This wrapper uses `CreateDefinition(swFmBaseFlange)`, `IBaseFlangeFeatureData.Initialize`
and `CreateFeature` rather than guessing deprecated long-argument interfaces. SW2026 SP01.1 validation covers an open U-shaped profile,
two real bends and save/reopen; edge flanges, miter flanges and lofted bends remain subject to `pilot` gates.

### Flat-pattern export

```python
from sw_export import export_flat_pattern_dxf

# Save the part first; the default option mask is flat-pattern geometry (1) + bend lines (4).
export_flat_pattern_dxf(model, dxfPath, include_bend_lines=True)
```

The fifth argument of `ExportToDWG2` is an alignment array of 12 doubles; the eighth argument is
the sheet-metal option mask. Do not mistake multiple Boolean arguments for outline/bend-line/sketch/hidden-edge flags.

### Sheet-metal parameters

```python
# Get sheet-metal feature data.
feat = model.FeatureByName("Sheet-Metal1")
sheet_metal_data = feat.GetDefinition()
thickness = sheet_metal_data.Thickness    # Sheet thickness
bend_radius = sheet_metal_data.BendRadius # Bend radius
```

## Weldments

### Cut list

```python
from sw_weldment import (
    create_structural_member,
    ensure_cut_list,
    export_cut_list_csv,
    set_cut_list_properties,
    weldment_evidence,
)

member = create_structural_member(
    model,
    profile_path,
    [sketch_segments],
    apply_corner_treatment=True,
)
ensure_cut_list(model)
set_cut_list_properties(model, {"PROFILE_DESIGNATION": "HSS1x1x16ga"})
evidence = weldment_evidence(model)
export_cut_list_csv(evidence, csv_path)
```

In SW2026, Python IDispatch may expose `InsertWeldmentCutList2` as a pseudo-property with value
`None`. The wrapper invokes it with `DISPATCH_METHOD` using DISPID 174,
confirmed by the local type library. The rectangular-frame regression groups bodies by their longest bounding-box dimension and creates two
actual `CutListFolder` entries instead of incorrectly merging members of different lengths.

### Structural members

```python
from sw_weldment import create_weldment_profile

# Complete and exit the closed profile sketch in the profile document; profile/BOM provenance properties may be added.
profile = create_weldment_profile(
    profile_model,
    profile_sketch,
    profile_path,
    properties={"DESCRIPTION": "HSS1x1x16ga", "MATERIAL": "steel_a500b"},
)
```

`create_structural_member()` uses `CreateStructuralMemberGroup` and the latest
`InsertStructuralWeldment5`, marshaling both path segments and groups as `VT_ARRAY | VT_DISPATCH`
SAFEARRAYs. Callers need not guess long argument lists or depend on the current selection set.

## Surface modeling

```python
# Extruded surface
feature_mgr.InsertExtrudedSurface(depth, flip, dir, t1, t2, d1, d2)

# Revolved surface
feature_mgr.InsertRevolvedRefSurface(...)

# Lofted surface
feature_mgr.InsertLoftRefSurface2(...)

# Swept surface
feature_mgr.InsertSweepRefSurface(...)

# Planar region
feature_mgr.InsertPlanarRefSurface()

# Trim surface
feature_mgr.InsertTrimSurface2(...)

# Knit surfaces
feature_mgr.InsertSewRefSurface(True, False, 0.001)

# Thicken a surface into a solid
feature_mgr.InsertThickenSheet(thickness, False, True)
```

## Simulation/FEA

> Requires the SolidWorks Simulation add-in.

```python
# Get the Simulation add-in.
cos_works = sw.GetAddInObject("SldWorks.Simulation")
if not cos_works:
    print("Simulation add-in is not installed or activated")

study_mgr = cos_works.StudyManager

# Create a static study.
study = study_mgr.CreateStudy(
    model,
    "StaticStudy1",
    0  # 0=Static, 1=Frequency, 2=Buckling, 3=Thermal, 5=Fatigue
)

# Add material through SolidBody.
# Add restraints (Fixed, Roller/Slider, Prescribed).
# Add loads (Force, Pressure, Gravity, Torque).

# Run the analysis.
study.RunAnalysis()

# Get results.
results = study.Results
# Stress, displacement, factor of safety, etc.
```

### Study types

| Value | Type | Description |
|---|---|---|
| 0 | Static | Static analysis |
| 1 | Frequency | Frequency analysis |
| 2 | Buckling | Buckling analysis |
| 3 | Thermal | Thermal analysis |
| 4 | Drop Test | Drop test |
| 5 | Fatigue | Fatigue analysis |
| 6 | Nonlinear | Nonlinear analysis |
