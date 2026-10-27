"""COM-free contract and review tests for the drawing subskill."""
from __future__ import annotations

from pathlib import Path

from scripts.drawing_spec import validate_drawing_spec
from scripts.sw_drawing import add_note, generate_drawing_from_spec, plan_standard_view_layout, validate_generic_drawing_generation
from scripts.sw_drawing_review import review_drawing_artifacts


def _spec(**overrides):
    payload = {
        "schemaVersion": "1.0",
        "sourceModel": "C:/cad/plate.sldprt",
        "documentType": "part",
        "standard": "GB_T",
        "projection": "first_angle",
        "paperSize": "A3",
        "modelSizeMm": [120, 80, 12],
        "views": {"front": {}, "top": {}, "right": {}},
        "outputs": {"slddrw": True, "pdf": True, "report": True},
    }
    payload.update(overrides)
    return payload


def test_gbt_drawing_spec_defaults_are_explicit_and_valid():
    result = validate_drawing_spec(_spec())

    assert result["status"] == "pass"
    assert result["capability"] == "solidworks-engineering-drawing"


def test_existing_model_dimension_switch_is_supported_by_schema():
    """Preserve the insertModelDimensions field already exposed by the drawing workflow."""
    result = validate_drawing_spec(_spec(insertModelDimensions=True))

    assert result["status"] == "pass"


def test_gbt_third_angle_is_blocked():
    result = validate_drawing_spec(_spec(projection="third_angle"))

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_GBT_PROJECTION_CONFLICT" for item in result["issues"])


def test_hole_requirement_requires_count_and_each_location():
    result = validate_drawing_spec(_spec(holeRequirements=[{
        "id": "H1",
        "specification": "M6 THRU",
        "count": 4,
        "locationsMm": [[-20, -10], [20, -10]],
    }]))

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_HOLE_REQUIREMENT_INCOMPLETE" for item in result["issues"])


def test_sheet_metal_without_flat_pattern_evidence_is_pilot():
    result = validate_drawing_spec(_spec(documentType="sheet_metal"))

    assert result["status"] == "pilot"
    assert any(item["code"] == "DRAWING_SHEET_METAL_FLAT_PATTERN_EVIDENCE_MISSING" for item in result["issues"])


def test_assembly_bom_requires_a_real_template(tmp_path: Path):
    result = validate_drawing_spec(_spec(documentType="assembly", bom={"required": True, "templatePath": str(tmp_path / "missing.sldbomtbt")}))

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_BOM_TEMPLATE_MISSING" for item in result["issues"])


def test_drawing_spec_rejects_schema_shape_errors_and_unknown_fields():
    """Formal JSON Schema failures must not bypass partial hand-written business checks."""
    result = validate_drawing_spec(_spec(unexpected=True, modelSizeMm=[120, "bad", 12]))

    assert result["status"] == "blocked"
    assert sum(item["code"] == "DRAWING_SPEC_SCHEMA_INVALID" for item in result["issues"]) >= 2


def test_model_size_is_a_schema_required_field():
    """Reject missing layout dimensions at the formal Schema layer before COM execution."""
    payload = _spec()
    payload.pop("modelSizeMm")

    result = validate_drawing_spec(payload)

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_SPEC_SCHEMA_INVALID" for item in result["issues"])


def test_first_angle_layout_places_top_below_and_right_left():
    layout = plan_standard_view_layout((0.12, 0.08, 0.012), paper_size="A3", projection="first_angle")
    by_name = {item["name"]: item for item in layout["views"]}

    assert layout["projection"] == "first_angle"
    assert by_name["*Top"]["center"][1] < by_name["*Front"]["center"][1]
    assert by_name["*Right"]["center"][0] < by_name["*Front"]["center"][0]


def test_requested_scale_is_applied_only_when_it_fits_sheet():
    """Apply explicit scale to the actual layout and reject layouts exceeding the workspace early."""
    accepted = plan_standard_view_layout((0.12, 0.08, 0.012), paper_size="A3", requested_scale="1:1")
    rejected = plan_standard_view_layout((0.12, 0.08, 0.012), paper_size="A3", requested_scale="10:1")

    assert accepted["status"] == "pass"
    assert accepted["scale"] == 1.0
    assert accepted["scale_ratio"] == [1, 1]
    assert rejected["status"] == "blocked"
    assert rejected["error_code"] == "DRAWING_SCALE_DOES_NOT_FIT"


def test_generic_generator_blocks_unsupported_spec_before_com_mutation():
    """The generic generator must not silently ignore sections, details, or specified dimensions."""
    class MustNotBeTouched:
        def __getattr__(self, name):
            raise AssertionError(f"Capability preflight must prevent COM access: {name}")

    payload = _spec(
        views={"front": {}, "top": {}, "right": {}, "sections": [{"id": "A-A"}], "details": [{"id": "F"}]},
        requiredDimensions=[{"id": "D1", "kind": "overall", "view": "Front"}],
        holeRequirements=[{"id": "H1", "specification": "Ø8", "count": 1, "locationsMm": [[10, 10, 0]]}],
        titleBlock={"required": True, "format": "GB_T", "drawingNumber": "DWG-001"},
        professionalAnnotations={
            "centerMarks": [{"id": "CM1", "view": "Front", "count": 2, "targets": ["holes"]}],
            "datums": [{"id": "DAT-A", "view": "Front", "text": "A"}],
        },
    )

    result = generate_drawing_from_spec(MustNotBeTouched(), payload, payload["sourceModel"])

    assert result["status"] == "blocked"
    assert result["stage"] == "capability_preflight"
    assert {item["code"] for item in result["issues"]} >= {
        "DRAWING_REQUESTED_VIEWS_UNSUPPORTED",
        "DRAWING_REQUIRED_DIMENSIONS_UNSUPPORTED",
        "DRAWING_HOLE_REQUIREMENTS_UNSUPPORTED",
        "DRAWING_TITLE_BLOCK_FIELDS_UNSUPPORTED",
        "DRAWING_PROFESSIONAL_ANNOTATIONS_UNSUPPORTED",
    }


def test_reviewer_flags_requested_detail_view_that_is_not_in_structure():
    """Review must explicitly identify a missing detail view when a custom workflow creates only the section."""
    payload = _spec(views={
        "front": {},
        "top": {},
        "right": {},
        "sections": [{"id": "A-A"}],
        "details": [{"id": "DETAIL-F"}],
    })
    structure = {
        "views": [
            {"name": "Front", "orientation": "*Front", "box": {"left": 0.20, "bottom": 0.10, "right": 0.30, "top": 0.18}},
            {"name": "Top", "orientation": "*Top", "box": {"left": 0.20, "bottom": 0.07, "right": 0.30, "top": 0.09}},
            {"name": "Right", "orientation": "*Right", "box": {"left": 0.10, "bottom": 0.10, "right": 0.18, "top": 0.18}},
            {"name": "Section view A-A", "type": 2, "box": {"left": 0.31, "bottom": 0.10, "right": 0.38, "top": 0.18}},
        ]
    }

    result = review_drawing_artifacts(payload, structure=structure)

    assert result["view_evidence"]["status"] == "fail"
    assert result["view_evidence"]["missing"] == ["DETAIL-F"]
    assert any(item["code"] == "DRAWING_REQUIRED_VIEWS_MISSING" for item in result["findings"])


def test_professional_annotation_schema_and_reviewer_use_structured_evidence():
    """Verify center marks, hole callouts, datums, GD&T, and surface finishes by type and view."""
    annotations = {
        "centerMarks": [{"id": "CM1", "view": "Front", "count": 2, "targets": ["holes"]}],
        "holeCallouts": [{"id": "HC1", "view": "Front", "text": "Ø8 THRU", "count": 1}],
        "datums": [{"id": "DAT-A", "view": "Front", "text": "A"}],
        "geometricTolerances": [{"id": "GDT1", "view": "Front", "text": "0.1 A"}],
        "surfaceFinishSymbols": [{"id": "SF1", "view": "Front", "text": "Ra 3.2"}],
    }
    structure = {
        "professional_annotations": {
            "center_marks": [
                {"semantic_view": "front"},
                {"semantic_view": "front"},
            ],
            "hole_callouts": [{"semantic_view": "front", "text_parts": ["Ø8 THRU"]}],
            "datum_tags": [{"semantic_view": "front", "label": "A"}],
            "geometric_tolerances": [{"semantic_view": "front", "frames": [{"values": ["0.1", "A"], "symbols": []}]}],
            "surface_finish_symbols": [{"semantic_view": "front", "text_parts": ["Ra 3.2"]}],
        }
    }

    result = review_drawing_artifacts(_spec(professionalAnnotations=annotations), structure=structure)

    assert validate_drawing_spec(_spec(professionalAnnotations=annotations))["status"] == "pass"
    assert result["professional_annotation_evidence"]["status"] == "pass"
    assert result["professional_annotation_evidence"]["matched_count"] == 5


def test_empty_professional_annotation_groups_do_not_block_generic_generator():
    """Empty declarations do not request professional annotations and must not create unnecessary capability blocks."""
    result = validate_generic_drawing_generation(_spec(professionalAnnotations={"centerMarks": []}))

    assert result["status"] == "pass"


def test_center_marks_are_supported_by_generic_generator_capability_gate():
    """Automatic center marks have write/read-back support and must not be blocked by the general annotation gate."""
    result = validate_generic_drawing_generation(_spec(professionalAnnotations={
        "centerMarks": [{"id": "CM1", "view": "Front", "count": 1, "targets": ["holes"]}],
    }))

    assert result["status"] == "pass"


def test_center_mark_schema_requires_targets_and_rejects_duplicate_view_groups():
    """Automatic insertion requires explicit target geometry; combine targets for the same view in one request."""
    missing_targets = validate_drawing_spec(_spec(professionalAnnotations={
        "centerMarks": [{"id": "CM1", "view": "Front", "count": 1}],
    }))
    duplicated = validate_drawing_spec(_spec(professionalAnnotations={
        "centerMarks": [
            {"id": "CM1", "view": "Front", "count": 1, "targets": ["holes"]},
            {"id": "CM2", "view": "front-view", "count": 1, "targets": ["slots"]},
        ],
    }))

    assert missing_targets["status"] == "blocked"
    assert any(item["code"] == "DRAWING_SPEC_SCHEMA_INVALID" for item in missing_targets["issues"])
    assert duplicated["status"] == "blocked"
    assert any(item["code"] == "DRAWING_CENTER_MARK_VIEW_DUPLICATE" for item in duplicated["issues"])


def test_professional_annotation_mutation_does_not_false_pass():
    """Changed datum or hole-callout text must not pass using another object of the same type."""
    annotations = {
        "holeCallouts": [{"id": "HC-M8", "view": "Front", "text": "M8"}],
        "datums": [{"id": "DAT-A", "view": "Front", "text": "A"}],
    }
    structure = {"professional_annotations": {
        "hole_callouts": [{"semantic_view": "front", "text_parts": ["M6"]}],
        "datum_tags": [{"semantic_view": "front", "label": "AB"}],
    }}

    result = review_drawing_artifacts(_spec(professionalAnnotations=annotations), structure=structure)

    assert result["professional_annotation_evidence"]["status"] == "fail"
    assert result["professional_annotation_evidence"]["missing"] == ["HC-M8", "DAT-A"]


def test_note_creation_reads_back_text_and_sheet_position():
    """InsertNote not throwing is insufficient proof that a note reached the drawing."""
    class Annotation:
        def __init__(self):
            self.position = None

        def SetPosition2(self, x, y, z):
            self.position = (x, y, z)
            return True

        def GetPosition(self):
            return self.position

    class Note:
        def __init__(self, text):
            self.text = text
            self.annotation = Annotation()

        def GetText(self):
            return self.text

        def GetAnnotation(self):
            return self.annotation

        def GetExtent(self):
            return (0.02, 0.018, 0.0, 0.05, 0.023, 0.0)

    class Drawing:
        def InsertNote(self, text):
            return Note(text)

    result = add_note(Drawing(), 0.02, 0.02, "Material: ABS")

    assert result["status"] == "pass"
    assert result["verified"] is True
    assert result["text_evidence"] == "Material: ABS"
    assert result["position_evidence_m"] == [0.02, 0.02, 0.0]


def test_review_requires_dimension_and_layout_evidence():
    structure = {
        "views": [
            {"name": "Front", "box": {"left": 0.20, "bottom": 0.10, "right": 0.32, "top": 0.18}},
            {"name": "Top", "box": {"left": 0.20, "bottom": 0.08, "right": 0.32, "top": 0.095}},
            {"name": "Right", "box": {"left": 0.08, "bottom": 0.10, "right": 0.18, "top": 0.18}},
        ],
        "dimensions": [],
        "title_block": {"box": {"left": 0.23, "bottom": 0.01, "right": 0.40, "top": 0.06}},
    }
    result = review_drawing_artifacts(_spec(requiredDimensions=[{"id": "D1", "kind": "overall", "view": "Front"}]), structure=structure)

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_REQUIRED_DIMENSIONS_MISSING" for item in result["findings"])


def test_review_names_missing_model_dimensions_when_auto_insert_is_requested():
    """Report an explicit reason for failed model-dimension insertion instead of blaming bounding-box limitations."""
    structure = {
        "views": [
            {"name": "Front", "box": {"left": 0.20, "bottom": 0.10, "right": 0.32, "top": 0.18}},
            {"name": "Top", "box": {"left": 0.20, "bottom": 0.08, "right": 0.32, "top": 0.095}},
            {"name": "Right", "box": {"left": 0.08, "bottom": 0.10, "right": 0.18, "top": 0.18}},
        ],
        "dimensions": [],
        "title_block": {"box": {"left": 0.23, "bottom": 0.01, "right": 0.40, "top": 0.06}},
    }
    result = review_drawing_artifacts(_spec(insertModelDimensions=True), structure=structure)

    assert result["status"] == "blocked"
    assert any(item["code"] == "DRAWING_MODEL_DIMENSIONS_MISSING" for item in result["findings"])


def test_final_pdf_dimension_boxes_replace_com_estimates_for_delivery_pass(tmp_path: Path):
    """When COM lacks text boxes, exact final-PDF dimension boxes can complete automated delivery review."""
    import fitz

    pdf_path = tmp_path / "drawing.pdf"
    document = fitz.open()
    page = document.new_page(width=1190.55, height=841.89)
    # A3 landscape conversion: meters to points; PDF and SolidWorks sheet Y axes run in opposite directions.
    page.insert_text((456.3, 598.2), "120", fontsize=12)
    page.insert_text((100, 700), "Material: ABS", fontsize=12)
    document.save(pdf_path)
    document.close()
    structure = {
        "sheets": ["Sheet1"],
        "sheet_size": {"width_m": 0.42, "height_m": 0.297},
        "views": [
            {"name": "Front", "box": {"left": 0.20, "bottom": 0.10, "right": 0.32, "top": 0.18}},
            {"name": "Top", "box": {"left": 0.20, "bottom": 0.08, "right": 0.32, "top": 0.095}},
            {"name": "Right", "box": {"left": 0.08, "bottom": 0.10, "right": 0.18, "top": 0.18}},
        ],
        "dimensions": [{
            "sheet": "Sheet1",
            "name": "D1@Front",
            "kind": "overall",
            "text": "",
            "box": {"left": 0.150, "bottom": 0.075, "right": 0.171, "top": 0.096},
            "box_source": "estimated",
            "box_confidence": "low",
            "box_evidence": {"position_m": [0.161, 0.086]},
        }],
        "notes": [{"sheet": "Sheet1", "text": "Material: ABS", "position_m": [0.02, 0.02, 0.0]}],
        "title_block": {"box": {"left": 0.23, "bottom": 0.01, "right": 0.40, "top": 0.06}},
    }
    result = review_drawing_artifacts(
        _spec(requiredDimensions=[{"id": "D1", "kind": "overall", "view": "Front"}], notes=["Material: ABS"]),
        structure=structure,
        pdf_path=pdf_path,
        preview_evidence=[{"exists": True, "likely_blank": False}],
    )

    assert result["status"] == "pass"
    assert result["manual_review_required"] is False
    assert result["pdf_dimension_rendering"]["status"] == "pass"
    assert result["note_evidence"]["status"] == "pass"
    assert result["layout"]["evidence_summary"]["rendered_dimension_box_count"] == 1


def test_required_dimension_id_does_not_use_substring_matching():
    """D10 or 110 text must not falsely satisfy D1."""
    structure = {
        "views": [{"name": "Front", "box": {"left": 0.1, "bottom": 0.1, "right": 0.2, "top": 0.2}}],
        "dimensions": [{"name": "D10@Front", "view": "Front", "kind": "overall", "text": "110"}],
    }

    result = review_drawing_artifacts(
        _spec(requiredDimensions=[{"id": "D1", "kind": "overall", "view": "Front", "valueMm": 10}]),
        structure=structure,
    )

    assert result["dimension_evidence"]["status"] == "fail"
    assert result["dimension_evidence"]["checks"][0]["mismatches"] == ["id"]


def test_required_dimension_checks_view_kind_and_value():
    """A matching ID must still fail when the view, kind, or value is wrong."""
    structure = {
        "views": [{"name": "Top", "box": {"left": 0.1, "bottom": 0.1, "right": 0.2, "top": 0.2}}],
        "dimensions": [{"name": "D1@Top", "view": "Top", "kind": "diameter", "text": "20"}],
    }

    result = review_drawing_artifacts(
        _spec(requiredDimensions=[{"id": "D1", "kind": "overall", "view": "Front", "valueMm": 10}]),
        structure=structure,
    )

    assert result["dimension_evidence"]["status"] == "fail"
    assert set(result["dimension_evidence"]["checks"][0]["mismatches"]) == {"view", "kind", "valueMm"}


def test_m8_hole_requirement_is_not_satisfied_by_other_hole_groups():
    """M3/M4 text or numerous unrelated hole groups cannot satisfy an M8 thread requirement."""
    requirement = {
        "id": "H-M8",
        "specification": "M8",
        "count": 2,
        "locationsMm": [[10, 10, 0], [30, 10, 0]],
    }
    model_evidence = {
        "hole_groups": [
            {"position_mm": [10, 10, 0], "diameters_mm": [2.5], "thread": "M3"},
            {"position_mm": [30, 10, 0], "diameters_mm": [3.3], "thread": "M4"},
        ]
    }

    result = review_drawing_artifacts(_spec(holeRequirements=[requirement]), structure={}, model_evidence=model_evidence)

    assert result["hole_evidence"]["status"] == "fail"
    assert result["hole_evidence"]["checks"][0]["matched_count"] == 0


def test_diameter_holes_require_exact_count_positions_and_diameter():
    """Match plain holes one-to-one by diameter and individual position without reusing a hole group."""
    requirement = {
        "id": "H-D8",
        "specification": "Ø8",
        "count": 2,
        "locationsMm": [[10, 10, 0], [30, 10, 0]],
    }
    model_evidence = {
        "hole_groups": [
            {"position_mm": [10.04, 10, 0], "diameters_mm": [8.0]},
            {"position_mm": [30, 10, 0], "diameters_mm": [8.04]},
        ]
    }

    result = review_drawing_artifacts(_spec(holeRequirements=[requirement]), structure={}, model_evidence=model_evidence)

    assert result["hole_evidence"]["status"] == "pass"
    assert result["hole_evidence"]["checks"][0]["matched_count"] == 2


def test_general_table_cannot_satisfy_required_bom():
    """An arbitrary general table cannot stand in for a BOM with data rows."""
    result = review_drawing_artifacts(
        _spec(documentType="assembly", bom={"required": True, "templatePath": __file__}),
        structure={"tables": [{"type": 0, "kind": "general", "row_count": 4}]},
    )

    assert result["bom_evidence"]["status"] == "fail"
    assert result["bom_evidence"]["tables"] == []


def test_title_block_candidate_without_content_is_not_a_pass():
    """Recognizing a sheet-format template does not prove that title-block fields are populated."""
    result = review_drawing_artifacts(
        _spec(titleBlock={"required": True, "format": "GB_T"}),
        structure={"title_block": {"candidate": True, "gbt_candidate": True, "content_verified": False}},
    )

    assert result["title_block_evidence"]["status"] == "review_required"
    assert result["title_block_evidence"]["content_verified"] is False


def test_note_absent_from_final_pdf_blocks_delivery(tmp_path: Path):
    """A note present in COM but missing from the PDF is not delivery evidence."""
    import fitz

    pdf_path = tmp_path / "drawing.pdf"
    document = fitz.open()
    document.new_page(width=1190.55, height=841.89)
    document.save(pdf_path)
    document.close()
    structure = {
        "sheets": ["Sheet1"],
        "sheet_size": {"width_m": 0.42, "height_m": 0.297},
        "views": [],
        "dimensions": [],
        "notes": [{"sheet": "Sheet1", "text": "Material: ABS", "position_m": [0.02, 0.02, 0.0]}],
        "title_block": {"candidate": True},
    }

    result = review_drawing_artifacts(_spec(notes=["Material: ABS"]), structure=structure, pdf_path=pdf_path)

    assert result["status"] == "blocked"
    assert result["note_evidence"]["missing_pdf"] == ["Material: ABS"]
    assert result["note_evidence"]["error_code"] == "DRAWING_NOTE_EVIDENCE_INCOMPLETE"


def test_unmatched_final_pdf_dimension_keeps_review_gate(tmp_path: Path):
    """Do not pass when final text boxes cannot be associated with COM dimensions."""
    import fitz

    pdf_path = tmp_path / "drawing.pdf"
    document = fitz.open()
    page = document.new_page(width=1190.55, height=841.89)
    page.insert_text((100, 100), "120", fontsize=12)
    document.save(pdf_path)
    document.close()
    structure = {
        "sheets": ["Sheet1"],
        "sheet_size": {"width_m": 0.42, "height_m": 0.297},
        "views": [
            {"name": "Front", "box": {"left": 0.20, "bottom": 0.10, "right": 0.32, "top": 0.18}},
            {"name": "Top", "box": {"left": 0.20, "bottom": 0.08, "right": 0.32, "top": 0.095}},
            {"name": "Right", "box": {"left": 0.08, "bottom": 0.10, "right": 0.18, "top": 0.18}},
        ],
        "dimensions": [{
            "sheet": "Sheet1",
            "name": "D1@Front",
            "text": "",
            "box": {"left": 0.150, "bottom": 0.075, "right": 0.171, "top": 0.096},
            "box_source": "estimated",
            "box_evidence": {"position_m": [0.161, 0.086]},
        }],
        "title_block": {"box": {"left": 0.23, "bottom": 0.01, "right": 0.40, "top": 0.06}},
    }
    result = review_drawing_artifacts(_spec(), structure=structure, pdf_path=pdf_path)

    assert result["status"] == "review_required"
    assert result["error_code"] == "DRAWING_PDF_DIMENSION_MATCH_INCOMPLETE"
