# File Export Reference

## Supported export formats

| Format | Extensions | ExportData required | Description |
|---|---|---|---|
| STEP | `.step` `.stp` | No | General 3D exchange |
| IGES | `.igs` `.iges` | No | Legacy exchange |
| STL | `.stl` | No | 3D printing/mesh |
| Parasolid | `.x_t` `.x_b` | No | High-fidelity kernel format |
| PDF | `.pdf` | Yes (IExportPdfData) | Drawing export |
| DXF/DWG | `.dxf` `.dwg` | No | 2D drawings/flat patterns |
| 3D PDF | `.pdf` | Yes | PDF with embedded 3D |
| eDrawings | `.eprt` `.easm` `.edrw` | No | Lightweight viewing |

## SaveAs error codes

| Value | Name | Description |
|---|---|---|
| 0 | swGenericSaveError | General error |
| 1 | swReadOnlySaveError | Read-only file |
| 2 | swFileNameEmpty | Empty filename |
| 3 | swFileNameContainsAtSign | Filename contains @ |
| 5 | swFileSaveFormatNotAvailable | Format unavailable |
| 6 | swFileSaveAsDoNotOverwrite | Existing file must not be overwritten |
| 9 | swFileSaveAsInvalidFileExtension | Invalid extension |

## SaveAs warning codes

| Value | Name | Description |
|---|---|---|
| 1 | swFileSaveWarning_RebuildError | Rebuild error |
| 2 | swFileSaveWarning_NeedsRebuild | Rebuild required |
| 4 | swFileSaveWarning_ViewsNeedUpdate | Views need updating |

## STL export quality

```python
# Set STL output quality.
# swUserPreferenceIntegerValue_e.swExportStlUnits = 78
model.SetUserPreferenceIntegerValue(78, 0)  # 0=Fine, 1=Coarse

# Set custom deviation and angle.
# swSTLDeviation
model.SetUserPreferenceDoubleValue(0x00000F, 0.005)  # Deviation (meters)
# swSTLAngleTolerance
model.SetUserPreferenceDoubleValue(0x000010, 0.174)  # Angular tolerance (radians, approximately 10 degrees)
```

## Batch conversion example

```python
import os
from sw_connect import open_document

def batch_convert(sw, input_dir, output_dir, input_ext=".sldprt", output_ext=".step"):
    """Convert all files in a directory."""
    os.makedirs(output_dir, exist_ok=True)

    for filename in os.listdir(input_dir):
        if filename.lower().endswith(input_ext):
            input_path = os.path.join(input_dir, filename)
            base = os.path.splitext(filename)[0]
            output_path = os.path.join(output_dir, base + output_ext)

            # Open; STEP/STP/IGES/IGS automatically use LoadFile4(..., "r", ...).
            errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            model = open_document(sw, input_path, silent=True)

            if model:
                # Export.
                model.Extension.SaveAs(output_path, 0, 1, None, errors, warnings)
                sw.CloseDoc(model.GetTitle())
                print(f"Converted: {filename} -> {base + output_ext}")
```

## Auditable batch export

`scripts/sw_export.py::batch_export_formats()` supports multiple inputs and output formats, recording for each output:

- SolidWorks API return value;
- File existence and byte count;
- Whether the file signature changed during this run;
- Whether the source document was already open by the user.

By default, existing files are not overwritten and user-opened SolidWorks documents are not closed. If equal source basenames produce a target-name collision, stop rather than letting the last write replace an earlier result.

## Pack and Go

`scripts/sw_delivery.py::pack_and_go()` uses native SolidWorks `IModelDocExtension.GetPackAndGo()`, `IPackAndGo.SetSaveToName()` and `IModelDocExtension.SavePackAndGo()`. Signatures were cross-checked against local SolidWorks 2024/2026 Interop, type libraries and official API Help.

Compatibility: official documentation and Interop expose zero-argument `GetPackAndGo()` returning `IPackAndGo`, but local SW2024/2026 pywin32 runtime objects can report a required/nonoptional argument. The wrapper first tries the official pywin32 call, then falls back to early-bound `comtypes`, retaining the original error context. `comtypes` attaches to an active instance first; only an instance confirmed as created by this fallback may be exited.

Safety boundaries:

1. The current document must already be saved to disk.
2. Reject a nonempty destination directory by default; proceed only with explicit `overwrite=True`.
3. Pre-save `GetDocumentNames()` enumeration is not final success evidence. Run `SavePackAndGo()`, then audit actual new files and `GetDependencies2`. `AddExternalDocuments` is for supplementary external files, not missing native assembly parts.
4. Return per-file size, SHA-256 and `produced_this_run`. Nonzero status codes, no actual new files or missing staging sources must not be marked successful.
5. In three consecutive local SW2026 SP01.1 regressions, pre-save enumeration and actual files both contained one `.SLDASM` and two `.SLDPRT`: `document_count=3`, all status codes zero, `missing_dependencies=[]`, with no staging fallback.
6. If other versions or complex assemblies still lack dependencies after native saving, default `fallback_policy=stage_dependencies` uses `GetDependencies2` to create a staged package with `backend=solidworks-native+staged_dependencies`, `status=pilot` and `cadstudio-pack-manifest.json`. Use `fallback_policy=blocked` for strict native semantics.
7. In either mode, external references, Toolbox, configurations, suppressed components and associated drawings require human spot checks.

Missing dependencies in strict mode return stable gate fields: `status=blocked`, `stage=review`,
`error_code=SW_PACK_AND_GO_DEPENDENCY_ENUMERATION_INCOMPLETE`. Default staging returns
`status=pilot`, `error_code=SW_PACK_AND_GO_NATIVE_ENUMERATION_INCOMPLETE`: the package may proceed to delivery but is not native Pack and Go and requires human review.

Before every batch-export format, activate the source document and read back `ActiveDoc.GetPathName()`. SW2024
exporters such as STL may use the active document even when `IModelDoc2.Extension.SaveAs()` on another document reports success.
Stop on path mismatch to avoid exporting an assembly component in place of the intended part STL.

## Coordinates when splitting and reassembling STEP

When splitting a complex STEP/Compound into separate STEP files for stable SolidWorks import, do not assume each imported part
uses its local origin. Some exporters preserve the original absolute solid coordinates; in that case
`AddComponent5(..., x=0, y=0, z=0)` may place every part's bounding-box center at the assembly origin, overlapping all components.

The manifest should preserve:

- `label`: stable component name.
- `step`: individual STEP path.
- `color_hex`: expected color.
- `bbox.center_mm` / `bbox.center_m`: global bounding-box center before export.
- `bbox.size_mm`: dimensions for post-import scale checks.

Insert each component at `bbox.center_m`; before saving, inspect the total assembly envelope, key component transforms and four views.

```python
center = item["bbox"]["center_m"]
component = add_component(
    assembly,
    item["native_path"],
    x=center[0],
    y=center[1],
    z=center[2],
    sw=session.sw,
)
```

Key checks:

1. Overall vehicle, frame or enclosure dimensions should approximate the original STEP.
2. Do not check component count alone: count and color readback can pass even when everything overlaps at the origin.
3. Combine `run_review()` results with visual PNG/BMP inspection.
