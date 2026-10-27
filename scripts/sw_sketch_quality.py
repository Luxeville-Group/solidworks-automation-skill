"""@brief Sketch-quality adapter: read constraints, dimensions, and Fix relations; API return values alone are not acceptance."""
try:
    from .sw_connect import create_empty_dispatch_variant, get_com_member
except ImportError:
    from sw_connect import create_empty_dispatch_variant, get_com_member


def inspect_sketch(sketch):
    """@brief Read editability evidence; remain blocked when unavailable.
    @param sketch ISketch object.
    @return Constraint state and counts of driving dimensions, relations, and fixed relations.
    """
    record = {"status": "blocked", "constrained_status": None, "dimension_count": None,
              "relation_count": None, "fix_count": None, "dimension_names": [], "errors": []}
    try:
        record["constrained_status"] = int(get_com_member(sketch, "GetConstrainedStatus"))
        relations = list(get_com_member(get_com_member(sketch, "RelationManager"), "GetRelations", 0) or [])
        record["relation_count"] = len(relations)
        record["fix_count"] = sum(int(get_com_member(item, "GetRelationType")) in {17, 70, 74} for item in relations)
        names = set()
        for relation in relations:
            dimension = get_com_member(relation, "GetDisplayDimension")
            if dimension is not None:
                names.add(str(get_com_member(dimension, "GetNameForSelection")))
        record["dimension_names"] = sorted(names)
        record["dimension_count"] = len(names)
        record["status"] = "pass" if record["constrained_status"] == 3 and names and record["fix_count"] == 0 else "review_required"
    except Exception as error:
        record["errors"].append(str(error))
    return record


def fully_define_sketch(model):
    """@brief Fully define a sketch using the origin as dimension datum; never replace design parameters with Fix.
    @param model IModelDoc2 in sketch edit mode.
    @return Actual readback evidence; raise without explicit passing evidence.
    """
    active = get_com_member(model.SketchManager, "ActiveSketch")
    if active is None:
        raise ValueError("Fully Define işlemi Sketch düzenleme modunda çalıştırılmalı")
    model.ClearSelection2(True)
    try:
        # Origin feature names vary by UI locale; enumerate actual names before constructing the official point reference.
        origins = ["Origin", "Orijin", "\u539f\u70b9"]
        feature = get_com_member(model, "FirstFeature", default=None)
        while feature is not None:
            if str(get_com_member(feature, "GetTypeName2")) == "OriginProfileFeature":
                origins.insert(0, str(get_com_member(feature, "Name")))
                break
            feature = get_com_member(feature, "GetNextFeature")
        selected = False
        for origin in dict.fromkeys(origins):
            for point_name in ("Point1", "Nokta1", "\u70b91"):
                selected = model.Extension.SelectByID2(point_name + "@" + origin, "EXTSKETCHPOINT", 0, 0, 0, False, 6,
                    create_empty_dispatch_variant(), 0)
                if selected:
                    break
            if selected:
                break
        if not selected:
            raise RuntimeError("Origin yatay/dikey ölçü datumu olarak seçilemedi")
        # 1023 is the verified combination of ten relations, excluding Fix. Return codes are undefined, so read back evidence.
        returned = model.SketchManager.FullyDefineSketch(True, True, 1023, True,
            1, create_empty_dispatch_variant(), 1, create_empty_dispatch_variant(), 1, 1)
        record = inspect_sketch(active)
        record["api_return"] = returned
        if record["status"] != "pass":
            raise RuntimeError(f"Sketch Fully Defined ve düzenlenebilirlik kabulünden geçemedi: {record}")
        return record
    finally:
        model.ClearSelection2(True)


def inspect_model_sketches(model):
    """@brief Reuse feature traversal to inspect all modeling sketches in the saved model."""
    try:
        from .sw_assembly import iter_feature_tree
    except ImportError:
        from sw_assembly import iter_feature_tree
    records = []
    seen = set()
    for feature, _depth in iter_feature_tree(model):
        if str(get_com_member(feature, "GetTypeName2")) not in {"ProfileFeature", "3DProfileFeature"}:
            continue
        name = str(get_com_member(feature, "Name"))
        if name in seen:
            continue
        seen.add(name)
        record = inspect_sketch(get_com_member(feature, "GetSpecificFeature2"))
        record["name"] = name
        try:
            owner = get_com_member(feature, "GetOwnerFeature")
            children = list(get_com_member(feature, "GetChildren") or [])
            consumers = [owner] if owner is not None else children
            record["consumed_by"] = [str(get_com_member(item, "Name")) for item in consumers
                if str(get_com_member(item, "GetTypeName2")) not in {"ProfileFeature", "3DProfileFeature", "RefAxis", "RefPlane", "RefPoint"}]
            record["dangling"] = not bool(record["consumed_by"])
        except Exception as error:
            record["dangling"] = None
            record["errors"].append(str(error))
        if record["dangling"] is not False:
            record["status"] = "review_required"
        records.append(record)
    return {"status": "pass" if records and all(item["status"] == "pass" for item in records) else "review_required", "sketches": records}
