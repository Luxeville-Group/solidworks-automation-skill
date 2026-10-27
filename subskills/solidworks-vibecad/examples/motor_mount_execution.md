# SolidWorks execution outline

- Part family: `cnc_mount`
- Execution mode: `solidworks_com_serial`
- Unit policy: plan uses mm; SolidWorks API receives meters via sw_connect.mm()

## Steps

1. `close_same_name_documents` -> `sw_session.SolidWorksSession.close` [ready]
2. `new_part` -> `sw_session.SolidWorksSession.new_part` [ready]
3. `base_plate` -> `sw_part.sketch_rectangle + sw_part.extrude_boss` [ready]
4. `outer_fillet_and_chamfer` -> `FeatureFillet / InsertFeatureChamfer with edge.Select2` [ready]
5. `pockets` -> `sw_part.sketch_rectangle or sketch_slot + extrude_cut` [ready]
6. `through_holes` -> `sw_part.sketch_circle + extrude_cut` [ready]
7. `mouth_chamfers` -> `InsertFeatureChamfer with circle edge selection` [ready]
8. `custom_properties` -> `model.Extension.CustomPropertyManager` [ready]
9. `save_export_review` -> `session.save + session.export + sw_review.run_review` [ready]

## Feature gates

- `BasePlate` (base_plate), required=True
- `OuterCornerFillet` (fillet), required=True; fallback: if the fillet solver fails, reduce to R4 or add edges individually.
- `TopEdgeChamfer` (chamfer), required=True; fallback: if the full loop fails, select edge objects in groups and retry.
- `CornerMountingHoles` (through_hole_pattern), required=True
- `CenterShaftClearance` (through_hole), required=True
- `SideLighteningPockets` (pocket_pair), required=False; fallback: if pockets collide with center or mounting holes, shrink or skip them and record the change.
- `HoleMouthChamfers` (chamfer), required=True

## Stop conditions

- SolidWorks preflight fails
- required base geometry feature returns None
- save/export output file missing or zero bytes
- review report marks previews blank
