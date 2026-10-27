# Drawing API Verification Checklist

Query official documentation or local Interop before implementing these APIs:

- `SetupSheet6`、`NewSheet4`
- `CreateFirstAngleViews2`、`Create3rdAngleViews2`
- `CreateDrawViewFromModelView3`
- `InsertModelAnnotations3/4`
- `InsertBomTable4`
- `CreateSectionViewAt5`、`CreateDetailViewAt4`
- `InsertDatumTag2`、`InsertSurfaceFinishSymbol3`、`InsertWeldSymbol`

Keep a minimal validation script; check returned objects, save/export and read-back results.
