# Week 1: JS CAD preview research

Research date: 2026-07-31. Data comes from public GitHub REST repository metadata; stars and forks change over time.

| Project | Stars | Forks | License | Suitable uses | This week's conclusion |
|---|---:|---:|---|---|---|
| [three.js](https://github.com/mrdoob/three.js) | 114,133 | 36,455 | MIT | WebGL scenes, GLTF/STL/OBJ loaders, interaction controls | Use as the CAD Studio preview foundation |
| [Online3DViewer](https://github.com/kovacsv/Online3DViewer) | 3,617 | 759 | MIT | Multiformat browser viewer supporting STEP/IGES/STL/OBJ and more | Evaluate format adaptation and UI capabilities later |
| [replicad](https://github.com/sgenoud/replicad) | 661 | 78 | MIT | Browser-based OpenCascade parametric modeling | Reference for future browser parametric experiments; exclude from this week's runtime |
| [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer) | 380 | 65 | MIT | Three.js CAD viewer component | Reference for tree structures, selection, and camera interaction |
| [occt-import-js](https://github.com/kovacsv/occt-import-js) | 278 | 54 | LGPL-2.1 | OpenCascade WASM import of STEP/IGES/BREP | Do not directly incorporate into the MIT main package yet; evaluate process isolation and licensing first |
| [ThatOpen/engine_components](https://github.com/ThatOpen/engine_components) | 691 | 204 | MIT | BIM/IFC components and 3D engine | Not a close fit for mechanical CAD goals; do not introduce yet |

## This week's implementation scope

- Prefer STL, GLB/GLTF, and OBJ for SolidWorks artifact previews. Dynamically import Three.js loaders to avoid blocking initial display.
- DXF uses a read-only browser parsing fallback supporting `LINE`, `CIRCLE`, and `LWPOLYLINE`. Display parsing errors explicitly; do not fake CAD success.
- Real geometry previews for STEP/IGES and DWG still depend on native SolidWorks/AutoCAD PNG or mesh exports; wireframe placeholders are not solid previews.
- Access local paths only through Tauri `convertFileSrc`. Diagnostic packages remain sanitized and exclude CAD files, prompts, and keys.

## Further evaluation

1. Evaluate LGPL integration of `occt-import-js` in an isolated Worker; complete legal and package-size checks before deciding on browser STEP preview support.
2. Compare Online3DViewer with the current Three.js component for large-model load time, memory use, and interaction while moving the window.
3. Add structured DXF layer, dimension, and drawing-frame display; fall back to native AutoCAD BMP/PNG previews for complex entities.
