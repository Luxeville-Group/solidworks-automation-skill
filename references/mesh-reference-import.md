# Importing High-Fidelity Mesh Reference Models

For requests to reproduce the original appearance or a 1:1 version of cars, consumer electronics or sculptures, first distinguish editable engineering solids from high-fidelity visual references. For appearance, prefer public 3D models or multiview blueprints rather than repeatedly refining a low-fidelity collection of hand-built prisms.

## Appropriate uses

- Explicit resemblance to a real product, such as an original Xiaomi SU7 or a 1:1 reconstruction from public images.
- Presentation, proportion checking, appearance reference or a starting point for reverse reconstruction.
- Mesh/DCC inputs such as `.glb`, `.gltf`, `.obj`, `.stl`, `.fbx`, `.blend`.

Inappropriate uses:

- Parametrically editable mechanical features, manufacturing-ready Class-A surfaces or sheet metal.
- Internal structure, assembly constraints, dimensional tolerances or process features: remodel or reverse-engineer separate parts instead of describing a triangle mesh as an engineering solid.

## Selecting a route

1. Obtain reliable input: user-provided files first, then publicly downloadable models, then reconstruction from front/side/top/rear blueprints.
2. Record provenance and licensing: URL, author, license and download date. Noncommercial status does not waive attribution or share-alike terms.
3. Preserve originals: keep source GLB/FBX/OBJ and converted OBJ/STL together and write `manifest.json`.
4. Normalize scale and coordinates: inspect the bounding box, then scale to real nominal dimensions. A common vehicle convention is X=width, Y=height, Z=length.
5. Prefer OBJ when materials matter: it is more likely to retain materials, glass transparency, lights and interiors. STL is robust but usually loses materials.
6. Visually inspect four views after SolidWorks import. A rule-based pass establishes file/nonblank evidence, not resemblance to the requested object.

## GLB/FBX/BLEND conversion

SolidWorks support for GLB/FBX/BLEND is inconsistent; convert first:

- With Blender: import and export OBJ/STL, retaining the texture directory.
- With Python: read GLB through `trimesh` and export OBJ/STL; prefer OBJ to preserve materials.
- Do not directly convert high-polygon meshes to STEP. The many triangular B-Rep faces can hang SolidWorks `LoadFile4` or disconnect RPC.

### Optional Python dependencies

Mesh conversion is not a core dependency for ordinary SolidWorks modeling. Check these before GLB/GLTF/OBJ/STL inspection, scaling or texture export:

| Library | Purpose |
|---|---|
| `trimesh` | Read GLB/GLTF/OBJ/STL, compute bounding boxes, export OBJ/STL/PLY |
| `pygltflib` | Detailed GLTF/GLB metadata and resource parsing |
| `numpy` | Scale transformations and coordinate axes |
| `Pillow` | Texture image I/O and preview support |

Check:

```powershell
python - <<'PY'
import importlib.util
for name in ["trimesh", "pygltflib", "numpy", "PIL"]:
    print(name, "OK" if importlib.util.find_spec(name) else "MISSING")
PY
```

If missing, explain the required installation:

```powershell
python -m pip install -r SKILL_DIR\requirements-mesh.txt
```

Opening existing OBJ/STL files in SolidWorks may not require these libraries. GLB/FBX/BLEND conversion or scaling to real dimensions usually does.

Scale-processing example:

```python
import numpy as np
import trimesh

scene = trimesh.load(r"E:\source\SU7.glb", force="scene")
mesh = scene.dump(concatenate=True)

# Source axes: X=width, Y=height, Z=length; target dimensions in meters.
target_extents = np.array([1.963, 1.455, 4.997])
scale = target_extents / scene.extents
center_xz = np.array([
    (scene.bounds[0][0] + scene.bounds[1][0]) / 2,
    0,
    (scene.bounds[0][2] + scene.bounds[1][2]) / 2,
])

vertices = mesh.vertices.copy()
vertices[:, 0] = (vertices[:, 0] - center_xz[0]) * scale[0]
vertices[:, 1] = (vertices[:, 1] - scene.bounds[0][1]) * scale[1]
vertices[:, 2] = (vertices[:, 2] - center_xz[2]) * scale[2]
mesh.vertices = vertices

mesh.export(r"E:\work\reference_scaled_m.obj")
mesh.export(r"E:\work\reference_scaled_m.stl")
```

## Stable SolidWorks import

Prefer:

```powershell
python scripts\sw_import_mesh_reference.py `
  E:\work\reference_scaled_m.obj `
  E:\work\reference_obj.SLDPRT `
  --units m `
  --model-type graphics `
  --review-dir E:\work\review_obj
```

Key details:

- Do not open OBJ/STL as ordinary parts with `OpenDoc6()`; some SW2024 environments return `errors=2097152`.
- For OBJ/STL `LoadFile4()`, do not pass `None` as the third argument; it can cause a type mismatch.
- Stable call: `LoadFile4(path, "r", create_empty_dispatch_variant(), errors)`.
- STEP/STP/IGES/IGS still use the foreign-CAD route in `sw_connect.open_document()`: `GetImportFileData()` + `LoadFile4(..., "r", import_data, errors)`.
- Import high-polygon appearance models as `graphics` by default; use `surface` or `solid` only for an explicit solid-repair attempt.

## Review criteria

After import, check at least:

1. Output `.SLDPRT` exists with a reasonable size.
2. `run_review()` exports `isometric/front/top/right` views.
3. The isometric view shows the main appearance and orthographic proportions match the target.
4. Key identifying details are present, such as a car's roofline, lights, wheels, side windows and bumpers.
5. Selection highlighting has not contaminated colors/materials; call `ClearSelection2(True)` before capture.
6. Explain the model type: a mesh reference is not an official parametric surface. Manufacturing requires subsequent part-by-part reverse reconstruction.

## SU7 case lessons

- Failed approach: scripting stacked prisms/capsules for a body and repeatedly adding lights, wheels and glass. For an original-SU7 request, this starting shape remained off target despite refinements.
- Better approach: obtain a public SU7 mesh, preserve source/license, convert to OBJ/STL, scale to `4997 × 1963 × 1455 mm`, then import into SolidWorks.
- API pitfall: an `OpenDoc6()` failure on OBJ/STL does not prove corrupt input; `LoadFile4()` also fails with `None`. Pass an empty Dispatch variant.
- Materials: OBJ is more likely than STL to preserve glass, tail lights, interior and wheel materials. STL is a material-free fallback.
- Review: an automatic pass does not establish SU7 resemblance. Open previews and inspect identifying features, proportions and displaced parts.
