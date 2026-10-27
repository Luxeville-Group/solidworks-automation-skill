"""
SOLIDWORKS result review utilities.

After CAD creation or modification, export multiple views and collect basic model summaries so an agent can assess geometry against user intent from screenshots or exported BMPs.
"""
import os
import json
import argparse
import math
import re
import sys
from pathlib import Path

try:
    from .sw_connect import connect_solidworks, get_com_member, open_document
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import connect_solidworks, get_com_member, open_document
    from sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()


STANDARD_VIEWS = {
    "front": 1,
    "back": 2,
    "left": 3,
    "right": 4,
    "top": 5,
    "bottom": 6,
    "isometric": 7,
    "trimetric": 8,
    "dimetric": 9,
}


_PDF_DIMENSION_TEXT = re.compile(
    r"(?:^\s*\d+(?:[.,]\d+)?\s*$|[Ø⌀Rr]\s*\d|\bM\d|\d+(?:[.,]\d+)?\s*(?:mm|°|deg)\b|\d+(?:[.,]\d+)?\s*[±]\s*\d)",
    re.IGNORECASE,
)


def _pdf_text_overlap_candidate(text: str) -> bool:
    """@brief Exclude border-zone letters and single-character page numbers from false PDF box overlaps."""
    compact = re.sub(r"\s+", "", str(text or "")).strip()
    return not (len(compact) == 1 and compact.isalnum())


def _import_pdf_parser():
    """@brief Import PyMuPDF, supporting explicit optional dependency directories such as drive E."""
    try:
        import fitz
        return fitz
    except ImportError as first_error:
        configured = os.environ.get("CADSTUDIO_PYMUPDF_PATH")
        if configured:
            candidate = str(Path(configured).expanduser().resolve())
            if Path(candidate).is_dir() and candidate not in sys.path:
                sys.path.insert(0, candidate)
            try:
                import fitz
                return fitz
            except ImportError:
                pass
        raise first_error


def _drawing_boxes_overlap(first, second, padding_m=0.001) -> bool:
    """@brief Check intersection of two drawing 2D bounding boxes."""
    if not first or not second:
        return False
    required = {"left", "bottom", "right", "top"}
    if not required <= set(first) or not required <= set(second):
        return False
    return not (
        float(first["right"]) + padding_m <= float(second["left"])
        or float(second["right"]) + padding_m <= float(first["left"])
        or float(first["top"]) + padding_m <= float(second["bottom"])
        or float(second["top"]) + padding_m <= float(first["bottom"])
    )


def review_drawing_layout(structure, *, padding_m=0.001, preview_evidence=None) -> dict:
    """@brief Review structured collision evidence for views, dimension text, and title blocks.

    SOLIDWORKS bounding boxes screen for risk; they cannot replace visual PDF/PNG review.
    """
    views = list(structure.get("views") or [])
    dimensions = list(structure.get("dimensions") or [])
    notes = list(structure.get("notes") or [])
    title_block = structure.get("title_block") or {}
    title_box = title_block.get("box")
    findings = []

    def add_finding(code, severity, first_kind, first_name, second_kind, second_name, *, evidence_source="native", confidence="high"):
        """@brief Append a drawing collision record with stable fields."""
        findings.append({
            "code": code,
            "severity": severity,
            "first": {"kind": first_kind, "name": str(first_name or "")},
            "second": {"kind": second_kind, "name": str(second_name or "")},
            "evidence_source": evidence_source,
            "confidence": confidence,
            "confirmed_collision": evidence_source == "native",
        })

    for index, view in enumerate(views):
        for other in views[index + 1:]:
            if _drawing_boxes_overlap(view.get("box"), other.get("box"), padding_m):
                add_finding("DRAWING_VIEW_OVERLAP", "fail", "view", view.get("name"), "view", other.get("name"))
        if _drawing_boxes_overlap(view.get("box"), title_box, padding_m):
            add_finding("DRAWING_VIEW_TITLE_BLOCK_INTRUSION", "fail", "view", view.get("name"), "title_block", "title_block")

    for index, dimension in enumerate(dimensions):
        dimension_source = dimension.get("box_source") or "native"
        dimension_confidence = dimension.get("box_confidence") or "high"
        dimension_severity = "warning" if dimension_source == "estimated" else "fail"
        for other in dimensions[index + 1:]:
            if _drawing_boxes_overlap(dimension.get("box"), other.get("box"), padding_m):
                other_source = other.get("box_source") or "native"
                source = "estimated" if "estimated" in {dimension_source, other_source} else "native"
                confidence = min(
                    (dimension_confidence, other.get("box_confidence") or "high"),
                    key={"unavailable": 0, "low": 1, "medium": 2, "high": 3}.get,
                )
                add_finding(
                    "DRAWING_DIMENSION_TEXT_OVERLAP",
                    "warning" if source == "estimated" else "fail",
                    "dimension", dimension.get("name"), "dimension", other.get("name"),
                    evidence_source=source,
                    confidence=confidence,
                )
        if _drawing_boxes_overlap(dimension.get("box"), title_box, padding_m):
            add_finding(
                "DRAWING_DIMENSION_TITLE_BLOCK_INTRUSION", dimension_severity,
                "dimension", dimension.get("name"), "title_block", "title_block",
                evidence_source=dimension_source,
                confidence=dimension_confidence,
            )
        for view in views:
            if dimension.get("view") == view.get("name"):
                continue
            if _drawing_boxes_overlap(dimension.get("box"), view.get("box"), padding_m):
                add_finding(
                    "DRAWING_DIMENSION_OTHER_VIEW_INTRUSION", "warning",
                    "dimension", dimension.get("name"), "view", view.get("name"),
                    evidence_source=dimension_source,
                    confidence=dimension_confidence,
                )

    def same_sheet(first, second):
        """@brief Check annotation/object collisions only within the same drawing sheet."""
        first_sheet = str(first.get("sheet") or "")
        second_sheet = str(second.get("sheet") or "")
        return not first_sheet or not second_sheet or first_sheet == second_sheet

    def evidence_for(item):
        source = item.get("box_source") or "native"
        confidence = item.get("box_confidence") or "high"
        return source, confidence, "warning" if source != "native" else "fail"

    def is_owner_view_label(note, view):
        """@brief Recognize section/detail-view labels to avoid flagging them against their owning views."""
        if note.get("note_kind") == "view_label":
            owner_name = str(note.get("owner_view") or "")
            return bool(owner_name and owner_name == str(view.get("name") or ""))
        if str(note.get("text") or "").strip():
            return False
        overlapping_special_views = [
            item for item in views
            if item.get("type") in {2, 3}
            and same_sheet(note, item)
            and _drawing_boxes_overlap(note.get("box"), item.get("box"), padding_m)
        ]
        return len(overlapping_special_views) == 1 and overlapping_special_views[0] is view

    for index, note in enumerate(notes):
        note_source, note_confidence, note_severity = evidence_for(note)
        if _drawing_boxes_overlap(note.get("box"), title_box, padding_m):
            add_finding(
                "DRAWING_NOTE_TITLE_BLOCK_INTRUSION", note_severity,
                "note", note.get("text"), "title_block", "title_block",
                evidence_source=note_source, confidence=note_confidence,
            )
        for view in views:
            if is_owner_view_label(note, view):
                continue
            if same_sheet(note, view) and _drawing_boxes_overlap(note.get("box"), view.get("box"), padding_m):
                add_finding(
                    "DRAWING_NOTE_VIEW_INTRUSION", note_severity,
                    "note", note.get("text"), "view", view.get("name"),
                    evidence_source=note_source, confidence=note_confidence,
                )
        for dimension in dimensions:
            if same_sheet(note, dimension) and _drawing_boxes_overlap(note.get("box"), dimension.get("box"), padding_m):
                dimension_source = dimension.get("box_source") or "native"
                source = "estimated" if "estimated" in {note_source, dimension_source} else note_source if note_source != "native" else dimension_source
                confidence = min(
                    (note_confidence, dimension.get("box_confidence") or "high"),
                    key={"unavailable": 0, "low": 1, "medium": 2, "high": 3}.get,
                )
                add_finding(
                    "DRAWING_NOTE_DIMENSION_OVERLAP",
                    "warning" if source != "native" else "fail",
                    "note", note.get("text"), "dimension", dimension.get("name"),
                    evidence_source=source, confidence=confidence,
                )
        for other in notes[index + 1:]:
            if same_sheet(note, other) and _drawing_boxes_overlap(note.get("box"), other.get("box"), padding_m):
                source = note_source if note_source != "native" else other.get("box_source") or "native"
                confidence = min(
                    (note_confidence, other.get("box_confidence") or "high"),
                    key={"unavailable": 0, "low": 1, "medium": 2, "high": 3}.get,
                )
                add_finding(
                    "DRAWING_NOTE_TEXT_OVERLAP", "warning" if source != "native" else "fail",
                    "note", note.get("text"), "note", other.get("text"),
                    evidence_source=source, confidence=confidence,
                )

    view_boxes_complete = bool(views) and all(item.get("box") for item in views)
    dimension_boxes_complete = not dimensions or all(item.get("box") for item in dimensions)
    note_boxes_complete = not notes or all(item.get("box") for item in notes)
    estimated_dimensions = [item for item in dimensions if item.get("box_source") == "estimated"]
    native_dimensions = [item for item in dimensions if (item.get("box_source") or "native") == "native"]
    rendered_dimensions = [item for item in dimensions if item.get("box_source") == "pdf_vector_text"]
    rendered_notes = [item for item in notes if item.get("box_source") == "pdf_vector_text"]
    confirmed_findings = [item for item in findings if item.get("confirmed_collision")]
    estimated_risk_findings = [item for item in findings if not item.get("confirmed_collision")]
    previews = list(preview_evidence or [])
    pixel_preview_available = bool(previews) and all(
        item.get("exists") and not item.get("likely_blank")
        for item in previews
    )
    checks = [
        {"id": "drawing-view-count", "status": "pass" if len(views) >= 3 else "fail", "message": f"Okunan {len(views)} teknik çizim görünüşü"},
        {"id": "drawing-view-boxes", "status": "pass" if view_boxes_complete else "warning", "message": "Görünüş sınırları eksiksiz" if view_boxes_complete else "Görünüş sınırı kanıtı eksik"},
        {
            "id": "drawing-dimension-boxes",
            "status": "pass" if dimension_boxes_complete and not estimated_dimensions else "warning",
            "message": (
                "Ölçü varlığı okunamadı"
                if not dimensions
                else "Ölçü metni sınırları eksiksiz (yerel SOLIDWORKS veya son PDF vektör metni)"
                if dimension_boxes_complete and not estimated_dimensions
                else f"Yerel SOLIDWORKS sınırları {len(native_dimensions)}/{len(dimensions)}; son PDF metin sınırları {len(rendered_dimensions)}/{len(dimensions)}; temkinli tahmin {len(estimated_dimensions)}/{len(dimensions)}"
            ),
        },
        {
            "id": "drawing-dimension-estimate-provenance",
            "status": "warning" if estimated_dimensions else "pass",
            "message": "Tahmini sınırlar yalnızca risk taraması içindir; yerel SOLIDWORKS bounding box değildir" if estimated_dimensions else "Tahmini ölçü sınırı kullanılmadı",
        },
        {"id": "drawing-title-block-box", "status": "pass" if title_box else "warning", "message": "Antet alanı çakışma denetimi için kullanılabilir" if title_box else "Antet alanı kanıtı eksik"},
        {
            "id": "drawing-note-boxes",
            "status": "pass" if note_boxes_complete else "warning",
            "message": f"Açıklama sınırları eksiksiz (PDF ile tamamlanan {len(rendered_notes)} öğe)" if note_boxes_complete else "Bazı açıklamaların sınırları eksik; tüm açıklama çakışmaları denetlenemiyor",
        },
        {
            "id": "drawing-layout-collisions",
            "status": "fail" if confirmed_findings else "warning" if estimated_risk_findings else "pass",
            "message": (
                f"Doğrulanmış çakışma {len(confirmed_findings)}; tahmini risk {len(estimated_risk_findings)} öğe"
                if findings else "Yapılandırılmış yerleşim çakışması riski bulunamadı"
            ),
        },
        {
            "id": "drawing-pixel-preview",
            "status": "pass" if pixel_preview_available else "warning",
            "message": "BMP önizleme mevcut ve boş değil; görsel doğrulamayı destekler" if pixel_preview_available else "Kullanılabilir BMP piksel kanıtı yok; tahmini sınırlar görsel olarak desteklenemiyor",
        },
    ]
    if len(views) < 3:
        status = "blocked"
        error_code = "DRAWING_STANDARD_VIEWS_MISSING"
    elif confirmed_findings:
        status = "review_required"
        error_code = "DRAWING_LAYOUT_COLLISION_DETECTED"
    elif estimated_risk_findings:
        status = "review_required"
        error_code = "DRAWING_LAYOUT_ESTIMATED_COLLISION_RISK"
    elif not view_boxes_complete or not dimension_boxes_complete or not title_box or not note_boxes_complete:
        status = "review_required"
        error_code = "DRAWING_LAYOUT_EVIDENCE_INCOMPLETE"
    elif estimated_dimensions:
        status = "review_required"
        error_code = "DRAWING_LAYOUT_ESTIMATED_EVIDENCE_REQUIRES_VISUAL_REVIEW"
    else:
        status = "pass"
        error_code = None
    return {
        "status": status,
        "stage": "review",
        "checks": checks,
        "findings": findings,
        "evidence_summary": {
            "dimension_count": len(dimensions),
            "native_dimension_box_count": len(native_dimensions),
            "rendered_dimension_box_count": len(rendered_dimensions),
            "estimated_dimension_box_count": len(estimated_dimensions),
            "confirmed_collision_count": len(confirmed_findings),
            "estimated_collision_risk_count": len(estimated_risk_findings),
            "pixel_preview_available": pixel_preview_available,
            "estimated_evidence_is_native": False,
        },
        "manual_review_required": status != "pass",
        "retryable": status != "pass",
        "error_code": error_code,
    }


def _expand_path(path):
    """Expand an output path."""
    return Path(os.path.expandvars(str(path))).expanduser().resolve()


def _file_info(path):
    """Return file existence and size information."""
    path = _expand_path(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def _read_bmp_size(path):
    """
    Read BMP dimensions.

    Returns:
        (width, height), or (None, None) on failure.
    """
    try:
        with open(path, "rb") as file:
            header = file.read(26)
        if len(header) < 26 or header[:2] != b"BM":
            return None, None
        width = int.from_bytes(header[18:22], "little", signed=True)
        height = int.from_bytes(header[22:26], "little", signed=True)
        return abs(width), abs(height)
    except Exception:
        return None, None


def inspect_pdf_text_layout(path, *, maximum_spans=20000, minimum_overlap_area_pt2=0.5):
    """@brief Read SOLIDWORKS PDF vector-text bounds and screen for text overlaps.

    Evidence comes from rendered text in official SOLIDWORKS PDF exports, not native COM dimension bounds. Scanned PDFs or outlined fonts may lack extractable text; continue visual BMP/PNG review in that case.
    """
    source = _expand_path(path)
    base = {
        "status": "blocked",
        "stage": "pdf_text_layout",
        "path": str(source),
        "source": "solidworks_pdf_vector_text",
        "native_com_bounding_box_available": False,
        "pages": [],
        "text_span_count": 0,
        "numeric_text_span_count": 0,
        "overlaps": [],
        "manual_review_required": True,
        "retryable": False,
        "error_code": None,
        "limitations": [
            "PDF metin kutuları çıktı kanıtıdır; yerel IAnnotation/IDisplayDimension bounding box değildir.",
            "Yalnızca çıkarılabilir vektör metinleri arasındaki örtüşmeler denetlenir; ölçü çizgileri, geometri veya antet kenarlarıyla çakışma olmadığını kanıtlamaz.",
        ],
    }
    if source.suffix.lower() != ".pdf" or not source.is_file() or not 0 < source.stat().st_size <= 256 * 1024 * 1024:
        base.update({"error_code": "DRAWING_PDF_INVALID", "message": "PDF yok, boş veya 256 MiB sınırını aşıyor."})
        return base
    try:
        fitz = _import_pdf_parser()
    except ImportError:
        base.update({
            "error_code": "DRAWING_PDF_TEXT_PARSER_MISSING",
            "message": "PyMuPDF eksik; PDF gerçek metin sınırlarını okumak için requirements-pdf.txt kurun.",
        })
        return base

    spans = []
    try:
        with fitz.open(source) as document:
            for page_index, page in enumerate(document):
                page_spans = []
                payload = page.get_text("dict")
                for block in payload.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = str(span.get("text") or "").strip()
                            box = list(span.get("bbox") or [])
                            if not text or len(box) != 4 or not all(math.isfinite(float(value)) for value in box):
                                continue
                            record = {
                                "page": page_index + 1,
                                "text": text,
                                "bboxPt": [float(value) for value in box],
                                "font": str(span.get("font") or ""),
                                "fontSizePt": float(span.get("size") or 0.0),
                                "dimensionCandidate": bool(_PDF_DIMENSION_TEXT.search(text)),
                            }
                            page_spans.append(record)
                            spans.append(record)
                            if len(spans) > maximum_spans:
                                raise ValueError(f"PDF metin span sayısı güvenlik sınırını aşıyor: {maximum_spans}.")
                base["pages"].append({
                    "page": page_index + 1,
                    "widthPt": float(page.rect.width),
                    "heightPt": float(page.rect.height),
                    "textSpans": page_spans,
                })
    except Exception as exc:
        base.update({"error_code": "DRAWING_PDF_TEXT_PARSE_FAILED", "message": str(exc), "retryable": True})
        return base

    overlaps = []
    for page in base["pages"]:
        ordered = sorted(page["textSpans"], key=lambda item: item["bboxPt"][0])
        active = []
        for current in ordered:
            x0, y0, x1, y1 = current["bboxPt"]
            active = [item for item in active if item["bboxPt"][2] > x0]
            for other in active:
                if not _pdf_text_overlap_candidate(other["text"]) or not _pdf_text_overlap_candidate(current["text"]):
                    continue
                ox0, oy0, ox1, oy1 = other["bboxPt"]
                width = min(x1, ox1) - max(x0, ox0)
                height = min(y1, oy1) - max(y0, oy0)
                area = width * height if width > 0 and height > 0 else 0.0
                if area > minimum_overlap_area_pt2:
                    overlaps.append({
                        "page": page["page"],
                        "firstText": other["text"],
                        "secondText": current["text"],
                        "intersectionAreaPt2": area,
                        "confirmedGeometryOverlap": True,
                        "confirmedVisualDefect": False,
                        "evidenceSource": "pdf_vector_text_bbox",
                    })
            active.append(current)
    base.update({
        "status": "review_required",
        "text_span_count": len(spans),
        "numeric_text_span_count": sum(1 for item in spans if item["dimensionCandidate"]),
        "overlaps": overlaps,
        "error_code": "DRAWING_PDF_TEXT_OVERLAP_RISK" if overlaps else None,
        "message": "PDF içinden vektör metni çıkarılamadı." if not spans else "PDF vektör metni sınırları okundu.",
    })
    if not spans:
        base["error_code"] = "DRAWING_PDF_VECTOR_TEXT_MISSING"
    return base


def inspect_bmp_preview(path, sample_limit=200000):
    """
    Run lightweight BMP preview checks.

    Detect obvious issues such as blank images, tiny files, and export failures. This does not replace human or visual-model judgment.
    """
    info = _file_info(path)
    info.update({
        "width": None,
        "height": None,
        "unique_sample_values": 0,
        "dark_pixel_ratio": 0.0,
        "likely_blank": True,
    })
    if not info["exists"] or info["size_bytes"] <= 0:
        return info

    width, height = _read_bmp_size(path)
    info["width"] = width
    info["height"] = height

    try:
        with open(path, "rb") as file:
            data = file.read()
        # Do not sample only the file start: SOLIDWORKS borders and geometry may occur later in pixel data.
        # Read the standard BI_RGB pixel grid, supporting 24/32-bit exports without an imaging dependency.
        pixel_offset = int.from_bytes(data[10:14], "little") if len(data) >= 14 else 54
        bits_per_pixel = int.from_bytes(data[28:30], "little") if len(data) >= 30 else 0
        row_stride = ((width * bits_per_pixel + 31) // 32) * 4 if width and bits_per_pixel else 0
        channels = bits_per_pixel // 8 if bits_per_pixel in (24, 32) else 0
        samples = []
        dark = 0
        total = 0
        if pixel_offset > 0 and row_stride > 0 and channels:
            # Positive BMP height means bottom-up pixels; negative height means top-down.
            signed_height = int.from_bytes(data[22:26], "little", signed=True)
            top_down = signed_height < 0
            sample_width = min(width, 96)
            sample_height = min(abs(signed_height), 96)
            for grid_y in range(sample_height):
                y = grid_y * max(abs(signed_height) - 1, 1) // max(sample_height - 1, 1)
                source_y = y if top_down else abs(signed_height) - 1 - y
                row_start = pixel_offset + source_y * row_stride
                for grid_x in range(sample_width):
                    x = grid_x * max(width - 1, 1) // max(sample_width - 1, 1)
                    start = row_start + x * channels
                    pixel = data[start:start + channels]
                    if len(pixel) != channels:
                        continue
                    # BGR(A) to luminance; below 245 counts as nonwhite, reliably detecting mechanical linework.
                    luminance = (pixel[0] * 0.114) + (pixel[1] * 0.587) + (pixel[2] * 0.299)
                    samples.append(tuple(pixel[:3]))
                    dark += int(luminance < 245)
                    total += 1
        if not samples:
            sample = data[pixel_offset:pixel_offset + sample_limit] if len(data) > pixel_offset else data
            info["unique_sample_values"] = len(set(sample))
            info["likely_blank"] = info["unique_sample_values"] < 8
        else:
            info["unique_sample_values"] = len(set(samples))
            info["dark_pixel_ratio"] = dark / total if total else 0.0
            info["likely_blank"] = info["dark_pixel_ratio"] < 0.0005
    except Exception as exc:
        info["error"] = str(exc)
    return info


def zoom_to_fit(model):
    """Zoom to fit and refresh graphics."""
    get_com_member(model, "ViewZoomtofit2")
    get_com_member(model, "GraphicsRedraw2")


def clear_selection_for_preview(model):
    """Clear selection highlights and redraw so green selection colors do not obscure appearance."""
    get_com_member(model, "ClearSelection2", True)
    selection_manager = get_com_member(model, "SelectionManager")
    if selection_manager is not None:
        try:
            selected_count = get_com_member(selection_manager, "GetSelectedObjectCount2", -1)
            if selected_count:
                get_com_member(model, "ClearSelection2", True)
        except Exception:
            pass
    get_com_member(model, "GraphicsRedraw2")


def activate_model_for_preview(model):
    """Activate the reviewed document so SaveBMP does not capture another active part/subassembly."""
    if model is None:
        return False
    title = get_com_member(model, "GetTitle")
    if not title:
        return False
    try:
        sw = _win32com.GetActiveObject("SldWorks.Application")
    except Exception:
        return False
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        active = sw.ActivateDoc3(title, False, 0, errors)
    except Exception:
        try:
            sw.ActivateDoc2(title, False, errors)
            active = sw.ActiveDoc
        except Exception:
            return False
    return active is not None


def set_standard_view(model, view_name="isometric"):
    """
    Set a standard view direction.

    Args:
        view_name: "isometric", "front", "top", "right", or a SOLIDWORKS view name.
    """
    view_id = STANDARD_VIEWS.get(str(view_name).lower())
    if view_id is None:
        model.ShowNamedView2(str(view_name), -1)
    else:
        model.ShowNamedView2("", view_id)
    zoom_to_fit(model)


def save_preview(model, output_path, view_name="isometric", width=1600, height=1000):
    """
    Export the current model preview.

    Args:
        model: IModelDoc2.
        output_path: BMP output path.
        view_name: Standard view direction.
        width: Image width.
        height: Image height.

    Returns:
        Output path string.
    """
    output_path = _expand_path(output_path)
    if output_path.suffix.lower() != ".bmp":
        output_path = output_path.with_suffix(".bmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    activate_model_for_preview(model)
    clear_selection_for_preview(model)
    set_standard_view(model, view_name)
    clear_selection_for_preview(model)
    ok = model.SaveBMP(str(output_path), int(width), int(height))
    if not ok or not output_path.exists():
        raise RuntimeError(f"Önizleme dışa aktarılamadı: {output_path}")
    return str(output_path)


def save_review_previews(model, output_dir, basename="review", views=None):
    """
    Export multiple model views.

    Args:
        model: IModelDoc2.
        output_dir: Output directory.
        basename: File-name prefix.
        views: View list; defaults to isometric, front, top, and right.

    Returns:
        Preview paths.
    """
    views = views or ("isometric", "front", "top", "right")
    output_dir = _expand_path(output_dir)
    return [
        save_preview(model, output_dir / f"{basename}_{view}.bmp", view)
        for view in views
    ]


def _feature_health(feature):
    """@brief Read GetErrorCode2 warning flags; never interpret unknown evidence as a fatal error."""
    result = {"error_code": None, "is_warning": None, "health_status": "unknown"}
    try:
        method = getattr(feature, "GetErrorCode2", None)
        if method is None:
            code = int(get_com_member(feature, "GetErrorCode"))
            result.update(error_code=code, health_status="healthy" if code == 0 else "unknown")
            return result
        warning = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)
        try:
            value = method(warning)
            is_warning = bool(warning.value)
        except TypeError:
            value = method()
            is_warning = None
        if isinstance(value, (tuple, list)):
            code, is_warning = value
            is_warning = None if is_warning is None else bool(is_warning)
        else:
            code = value
        code = int(code)
        result.update(error_code=code, is_warning=is_warning,
            health_status="healthy" if code == 0 else "warning" if is_warning is True else "error" if is_warning is False else "unknown")
    except Exception as error:
        result["health_error"] = str(error)
    return result


def collect_model_summary(model):
    """
    Collect a basic model summary.

    Returns:
        dict including title, type, feature count, and saved path.
    """
    features = []
    feature_error = None
    try:
        feature = get_com_member(model, "FirstFeature")
        while feature:
            features.append({
                "name": get_com_member(feature, "Name"),
                "type": get_com_member(feature, "GetTypeName2"),
                **_feature_health(feature),
            })
            feature = get_com_member(feature, "GetNextFeature")
    except Exception as exc:
        feature_error = str(exc)

    summary = {
        "title": get_com_member(model, "GetTitle"),
        "path": get_com_member(model, "GetPathName"),
        "type": get_com_member(model, "GetType"),
        "feature_count": len(features),
        "features": features,
        "faulty_features": [item for item in features if item["health_status"] == "error"],
        "warning_features": [item for item in features if item["health_status"] == "warning"],
        "unknown_feature_health": [item for item in features if item["health_status"] == "unknown"],
    }
    if feature_error:
        summary["feature_error"] = feature_error
    return summary


def _unit_vector(values):
    """@brief Return a 3D unit vector; None for a zero vector."""
    vector = [float(value) for value in values[:3]]
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return None
    return [value / length for value in vector]


def _axis_distance_mm(point_mm, origin_mm, axis):
    """@brief Calculate perpendicular distance from a millimeter point to a spatial axis."""
    direction = _unit_vector(axis)
    if direction is None:
        return float("inf")
    offset = [float(point_mm[index]) - float(origin_mm[index]) for index in range(3)]
    projection = sum(offset[index] * direction[index] for index in range(3))
    perpendicular = [offset[index] - projection * direction[index] for index in range(3)]
    return math.sqrt(sum(value * value for value in perpendicular))


def group_coaxial_hole_segments(segments, position_tolerance_mm=0.05, axis_tolerance=1e-5):
    """
    @brief Merge coaxial cylinder segments into simple/compound-hole evidence.
    @param segments Hole segments from collect_geometry_measurements().
    @param position_tolerance_mm Coaxial-line distance tolerance.
    @param axis_tolerance Parallel-axis tolerance.
    @return Hole groups with segment_count, diameters_mm, and feature_kind.
    """
    groups = []
    for segment in segments:
        axis = _unit_vector(segment.get("axis") or [])
        origin = segment.get("position_mm") or segment.get("origin_mm") or []
        if axis is None or len(origin) < 3:
            continue
        matched = None
        for group in groups:
            group_axis = group["axis"]
            parallel = abs(sum(axis[index] * group_axis[index] for index in range(3)))
            distance = _axis_distance_mm(origin, group["position_mm"], group_axis)
            if abs(1.0 - parallel) <= axis_tolerance and distance <= position_tolerance_mm:
                matched = group
                break
        if matched is None:
            matched = {"position_mm": list(origin[:3]), "axis": axis, "segments": []}
            groups.append(matched)
        matched["segments"].append(segment)

    normalized = []
    for group in groups:
        diameters = sorted({round(float(item.get("diameter_mm", 0.0)), 6) for item in group["segments"]})
        normalized.append({
            "position_mm": [round(float(value), 6) for value in group["position_mm"]],
            "axis": [round(float(value), 9) for value in group["axis"]],
            "segment_count": len(group["segments"]),
            "diameters_mm": diameters,
            "feature_kind": "compound" if len(diameters) > 1 else "simple",
            "segments": group["segments"],
        })
    return normalized


def validate_hole_positions(measurements, expected_holes, position_tolerance_mm=0.1, diameter_tolerance_mm=0.05):
    """
    @brief Validate expected hole diameters and positions using axes; return per-hole acceptance results.

    This proves only diameter and axis position. Cross-check blind depth, through status, and countersink type using feature-parameter readback or feature_evidence returned by creation functions.
    """
    actual = measurements.get("holes") or []
    checks = []
    used = set()
    for index, expected in enumerate(expected_holes):
        expected_position = expected.get("position_mm") or []
        expected_diameter = float(expected.get("diameter_mm", 0.0))
        best = None
        for actual_index, candidate in enumerate(actual):
            if actual_index in used or len(expected_position) < 3:
                continue
            diameter_error = abs(float(candidate.get("diameter_mm", 0.0)) - expected_diameter)
            position_error = _axis_distance_mm(expected_position, candidate.get("position_mm") or [], candidate.get("axis") or [])
            score = diameter_error + position_error
            if best is None or score < best[0]:
                best = (score, actual_index, candidate, diameter_error, position_error)
        passed = bool(best and best[3] <= diameter_tolerance_mm and best[4] <= position_tolerance_mm)
        if passed:
            used.add(best[1])
        checks.append({
            "id": expected.get("id") or f"hole-{index + 1}",
            "passed": passed,
            "expected_diameter_mm": expected_diameter,
            "expected_position_mm": list(expected_position),
            "actual_diameter_mm": best[2].get("diameter_mm") if best else None,
            "diameter_error_mm": round(best[3], 6) if best else None,
            "position_error_mm": round(best[4], 6) if best else None,
            "evidence_scope": "B-Rep diameter and axis position only",
        })
    return {
        "status": "pass" if checks and all(item["passed"] for item in checks) else "fail",
        "position_tolerance_mm": float(position_tolerance_mm),
        "diameter_tolerance_mm": float(diameter_tolerance_mm),
        "checks": checks,
        "unmatched_actual_count": max(0, len(actual) - len(used)),
    }


def collect_geometry_measurements(model):
    """
    @brief Read part B-Rep bounding boxes and internal cylinders as manufacturing geometry evidence.
    @param model SOLIDWORKS IModelDoc2/IPartDoc.
    @return dict with envelope_mm, holes, and cylindrical_faces.

    Cylinders with FaceInSurfaceSense=True count as internal hole walls. External cylinders remain in cylindrical_faces but Reviewer Gate does not treat them as hole-diameter evidence.
    """
    measurements = {
        "units": "mm",
        "measurement_source": "SolidWorks API GetPartBox(True) + B-Rep cylindrical faces",
        "envelope_mm": None,
        "holes": [],
        "compound_holes": [],
        "slot_arc_candidates": [],
        "cylindrical_faces": [],
        "errors": [],
    }
    document_type = get_com_member(model, "GetType", default=None)
    if document_type not in (None, 1):
        measurements.update(unsupported_doc_type=document_type, hole_count=0, hole_groups=[])
        return measurements
    try:
        box = list(get_com_member(model, "GetPartBox", True) or [])
        if len(box) >= 6:
            sizes = [abs(float(box[index + 3]) - float(box[index])) * 1000.0 for index in range(3)]
            measurements["envelope_mm"] = {
                "length": round(sizes[0], 6),
                "width": round(sizes[1], 6),
                "height": round(sizes[2], 6),
                "axis_order": "model_xyz",
            }
        else:
            measurements["errors"].append("GetPartBox(True) 6 koordinat değeri döndürmedi")
    except Exception as exc:
        measurements["errors"].append(f"Bounding box okunamadı: {exc}")

    try:
        bodies = get_com_member(model, "GetBodies2", 0, False) or []
        for body_index, body in enumerate(bodies):
            for face_index, face in enumerate(get_com_member(body, "GetFaces") or []):
                try:
                    surface = get_com_member(face, "GetSurface")
                    if not surface or not get_com_member(surface, "IsCylinder"):
                        continue
                    params = list(get_com_member(surface, "CylinderParams") or [])
                    if len(params) < 7:
                        continue
                    internal = bool(get_com_member(face, "FaceInSurfaceSense"))
                    area_mm2 = float(get_com_member(face, "GetArea") or 0.0) * 1_000_000.0
                    diameter_mm = float(params[6]) * 2000.0
                    circumference_mm = 3.141592653589793 * diameter_mm
                    cylinder = {
                        "diameter_mm": round(diameter_mm, 6),
                        "origin_mm": [round(float(value) * 1000.0, 6) for value in params[:3]],
                        "axis": [round(float(value), 9) for value in params[3:6]],
                        "area_mm2": round(area_mm2, 6),
                        "axial_length_mm": round(area_mm2 / circumference_mm, 6) if circumference_mm else None,
                        "internal": internal,
                        "loop_count": int(get_com_member(face, "GetLoopCount") or 0),
                        "edge_count": int(get_com_member(face, "GetEdgeCount") or 0),
                        "body_index": body_index,
                        "face_index": face_index,
                    }
                    measurements["cylindrical_faces"].append(cylinder)
                    if internal:
                        evidence = {
                            "diameter_mm": cylinder["diameter_mm"],
                            "position_mm": cylinder["origin_mm"],
                            "axis": cylinder["axis"],
                            "axial_length_mm": cylinder["axial_length_mm"],
                            "through_state": "unknown",
                            "through_evidence": "B-Rep cylinder boundaries cannot distinguish blind from through",
                            "measurement_source": "B-Rep internal cylindrical face",
                        }
                        if cylinder["edge_count"] <= 2:
                            measurements["holes"].append(evidence)
                        else:
                            evidence["classification_reason"] = "internal cylinder has more than two boundary edges"
                            measurements["slot_arc_candidates"].append(evidence)
                except Exception as exc:
                    measurements["errors"].append(f"Silindirik yüz okunamadı body={body_index} face={face_index}: {exc}")
    except Exception as exc:
        measurements["errors"].append(f"Gövde topolojisi okunamadı: {exc}")
    measurements["hole_count"] = len(measurements["holes"])
    measurements["hole_groups"] = group_coaxial_hole_segments(measurements["holes"])
    measurements["compound_holes"] = [
        group for group in measurements["hole_groups"] if group["feature_kind"] == "compound"
    ]
    return measurements


def build_review_report(model, output_dir, basename="review", views=None, expected_outputs=None):
    """
    Build structured review data.

    Args:
        model: IModelDoc2.
        output_dir: Preview/report output directory.
        basename: Output file prefix.
        views: Views to export.
        expected_outputs: Required output files such as sldprt, step, and stl.

    Returns:
        Review report dict.
    """
    output_dir = _expand_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rebuild_ok = bool(get_com_member(model, "ForceRebuild3", False))
    zoom_to_fit(model)

    views = views or ("isometric", "front", "top", "right")
    preview_paths = save_review_previews(model, output_dir, basename=basename, views=views)
    previews = [inspect_bmp_preview(path) for path in preview_paths]
    expected = [_file_info(path) for path in (expected_outputs or [])]
    summary = collect_model_summary(model)
    geometry = collect_geometry_measurements(model)
    interference = None
    drawing_structure = None
    drawing_layout = None
    if summary.get("type") == 2:
        try:
            from .sw_assembly import get_interference_detection
        except ImportError:
            from sw_assembly import get_interference_detection
        interference = get_interference_detection(model)
    elif summary.get("type") == 3:
        try:
            from .sw_drawing import inspect_drawing_structure
        except ImportError:
            from sw_drawing import inspect_drawing_structure
        drawing_structure = inspect_drawing_structure(model)
        drawing_layout = review_drawing_layout(drawing_structure)
    sketch_quality = None
    if summary.get("type") == 1:
        try:
            from .sw_sketch_quality import inspect_model_sketches
        except ImportError:
            from sw_sketch_quality import inspect_model_sketches
        sketch_quality = inspect_model_sketches(model)

    checks = {
        "rebuild_succeeded": rebuild_ok,
        "model_available": model is not None,
        "previews_created": all(item["exists"] and item["size_bytes"] > 0 for item in previews),
        "previews_not_blank": all(not item["likely_blank"] for item in previews),
        "expected_outputs_exist": all(item["exists"] and item["size_bytes"] > 0 for item in expected) if expected else None,
        "feature_summary_available": "feature_error" not in summary,
        "geometry_measurements_available": geometry.get("envelope_mm") is not None,
        "geometry_measurements_error_free": not geometry.get("errors"),
        "feature_errors_absent": not summary.get("faulty_features"),
    }

    review_notes = [
        "İnsan veya görsel model; ana gövdeyi, oranları, yönü, kritik parçaları, örtüşmeleri ve havada kalan bileşenleri önizlemelerde incelemeli.",
        "previews_not_blank false ise önce zoom, boş model ve SaveBMP başarısını denetleyin.",
        "expected_outputs_exist false ise önce kaydetme/dışa aktarma yollarını ve COM hata kodlarını denetleyin.",
    ]

    report = {
        "model": summary,
        "cad_spec": geometry,
        "sketch_quality": sketch_quality,
        "interference": interference,
        "drawing_structure": drawing_structure,
        "drawing_layout": drawing_layout,
        "previews": previews,
        "expected_outputs": expected,
        "checks": checks,
        "review_notes": review_notes,
    }
    report["evaluation"] = evaluate_review_report(report)
    return report


def evaluate_review_report(report):
    """
    Score a structured review report using rules.

    Returns:
        dict with status, score, issues, recommendations, and manual_review_required.
    """
    checks = report.get("checks", {})
    previews = report.get("previews", [])
    expected_outputs = report.get("expected_outputs", [])
    issues = []
    recommendations = []
    score = 100
    hard_fail = False

    def add_issue(code, severity, message, recommendation, penalty):
        nonlocal score, hard_fail
        issues.append({
            "code": code,
            "severity": severity,
            "message": message,
        })
        recommendations.append(recommendation)
        score -= penalty
        if severity == "fail":
            hard_fail = True

    if checks.get("rebuild_succeeded") is False:
        add_issue("rebuild_failed", "fail", "Model Rebuild başarısız; teslim durumu doğrulanamıyor.", "Özellik hatalarını giderip Rebuild ve incelemeyi yeniden çalıştırın.", 40)
    summary = report.get("model") or {}
    if summary.get("faulty_features"):
        add_issue("feature_errors_present", "fail", "Feature tree doğrulanmış hatalı özellikler içeriyor.", "Rapordaki özellikleri düzeltip Rebuild çalıştırın.", 35)
    if summary.get("warning_features") or summary.get("unknown_feature_health"):
        add_issue("feature_health_review_required", "warn", "Özellik uyarıları var veya hata kanıtı eksik.", "Özellik hata/uyarı ayrıntılarını inceleyin.", 8)
    envelope = (report.get("cad_spec") or {}).get("envelope_mm")
    if summary.get("type") == 1 and envelope:
        try:
            values = [float(envelope[name]) for name in ("length", "width", "height")]
            valid = all(math.isfinite(value) and value >= 0 for value in values)
            valid = valid and any(value > 1e-6 for value in values)
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            add_issue("degenerate_envelope", "fail", "Parça zarfı dejenere veya boyutlar sonlu değil.", "Gerçek katı gövde bulunduğunu doğrulayın.", 35)
    interference = report.get("interference")
    if interference:
        if interference.get("status") == "blocked":
            add_issue("interference_check_blocked", "warn", "Montaj interference kanıtı okunamadı.", "Tam yüklemeyi ve CAD durumunu denetleyin.", 8)
        elif interference.get("interference_count"):
            add_issue("interference_detected", "warn", "Montajda interference var; hacim ve bileşenler ayrıntılarda.", "Geçmenin kasıtlı olup olmadığını doğrulayın; değilse Mate ilişkilerini düzeltin.", 20)
    structure = report.get("drawing_structure")
    if structure is not None:
        if structure.get("error_code") == "DRAWING_VIEWS_MISSING" or (structure.get("status") in {"pass", "ok"} and not structure.get("views")):
            add_issue("drawing_views_missing", "fail", "Teknik çizimde kullanılabilir görünüş yok.", "Teknik çizim görünüşlerini oluşturup inceleyin.", 35)
        elif structure.get("status") == "blocked":
            add_issue("drawing_structure_blocked", "warn", "Teknik çizim yapı kanıtı okunamadı.", "Teknik çizim yapısını inceleyin.", 8)
    layout = report.get("drawing_layout")
    if layout and layout.get("status") not in {"pass", "ok"}:
        add_issue("drawing_layout_review_required", "warn", "Teknik çizim yerleşimi hâlâ inceleme gerektiriyor.", "Yerleşim ayrıntılarını ve son PDF dosyasını denetleyin.", 8)
    quality = report.get("sketch_quality")
    if quality and quality.get("status") != "pass":
        add_issue("sketch_quality_review_required", "warn", "Model Sketch kısıtları veya sürücü ölçüleri readback denetiminden geçemedi.", "Sketch kısıtlarını, Fix ve tasarım parametrelerini denetleyip kabulü yeniden çalıştırın.", 10)

    if not checks.get("model_available"):
        add_issue(
            "model_missing",
            "fail",
            "İncelenebilir SOLIDWORKS model nesnesi yok.",
            "Önce bağlantıyı ve geçerli belgenin açıldığını veya oluşturulduğunu doğrulayın.",
            40,
        )

    if not checks.get("previews_created"):
        add_issue(
            "previews_missing",
            "fail",
            "Önizleme oluşturulamadı.",
            "SaveBMP, çıktı dizini yetkileri ve model görünürlüğünü denetleyin.",
            35,
        )

    if checks.get("previews_created") and not checks.get("previews_not_blank"):
        add_issue(
            "previews_blank",
            "fail",
            "En az bir önizleme boş görünüyor.",
            "Boş model, Zoom to Fit ve yalnızca Sketch durumunda kalma olasılığını denetleyin.",
            35,
        )

    if checks.get("expected_outputs_exist") is False:
        add_issue(
            "expected_outputs_missing",
            "fail",
            "Beklenen çıktı dosyası yok veya boyutu sıfır.",
            "Kaydetme/dışa aktarma yolunu ve SOLIDWORKS SaveAs hata kodunu yeniden denetleyin.",
            30,
        )

    if checks.get("expected_outputs_exist") is None:
        add_issue(
            "expected_outputs_not_declared",
            "warn",
            "Beklenen çıktı dosyaları belirtilmedi; teslimatın eksiksizliği doğrulanamıyor.",
            "run_review() çağrısında expected_outputs belirtin.",
            8,
        )

    if not checks.get("feature_summary_available"):
        add_issue(
            "feature_summary_unavailable",
            "warn",
            "Feature tree özeti okunamadı.",
            "Geometri önizlemesi normalse devam edilebilir; feature tree hata ayıklaması için COM üye uyumluluğunu denetleyin.",
            8,
        )

    if len(previews) < 2:
        add_issue(
            "too_few_previews",
            "warn",
            "3D geometriyi değerlendirmek için önizleme açısı sayısı yetersiz.",
            "En az isometric/front/top/right görünüşlerini dışa aktarın.",
            8,
        )

    for preview in previews:
        if preview.get("exists") and preview.get("size_bytes", 0) < 10000:
            add_issue(
                "preview_file_too_small",
                "warn",
                f"Önizleme dosyası çok küçük: {preview.get('path')}",
                "BMP çıktısının tamamlandığını doğrulayın; gerekirse yeniden dışa aktarın.",
                5,
            )
        if preview.get("width") and preview.get("height"):
            if preview["width"] < 640 or preview["height"] < 480:
                add_issue(
                    "preview_resolution_low",
                    "warn",
                    f"Önizleme çözünürlüğü düşük: {preview.get('path')}",
                    "Varsayılan 1600x1000 veya daha yüksek çözünürlük kullanın.",
                    4,
                )

    for output in expected_outputs:
        if output.get("exists") and output.get("size_bytes", 0) < 1024:
            add_issue(
                "output_file_too_small",
                "warn",
                f"Çıktı dosyası çok küçük: {output.get('path')}",
                "Dosyanın boş kabuk veya başarısız dışa aktarma kalıntısı olup olmadığını denetleyin.",
                6,
            )

    score = max(0, min(100, score))
    if hard_fail:
        status = "fail"
    elif issues:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "score": score,
        "issues": issues,
        "recommendations": list(dict.fromkeys(recommendations)),
        "manual_review_required": True,
        "manual_review_reason": "Kural puanlaması yalnızca belirgin hataları yakalar; geometrinin kullanıcı isteğine uygunluğu önizleme veya ekran görüntüsüyle incelenmeli.",
    }


def write_review_report(report, output_path):
    """
    Write a JSON review report.

    Returns:
        Report path string.
    """
    output_path = _expand_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    return str(output_path)


def write_markdown_summary(report, output_path):
    """
    Write a Markdown review summary.

    Returns:
        Summary path string.
    """
    output_path = _expand_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evaluation = report.get("evaluation", {})
    checks = report.get("checks", {})
    lines = [
        "# SolidWorks Review Summary",
        "",
        f"- Status: `{evaluation.get('status', 'unknown')}`",
        f"- Score: `{evaluation.get('score', 0)}`",
        f"- Manual review required: `{evaluation.get('manual_review_required', True)}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in checks.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Issues", ""])
    issues = evaluation.get("issues", [])
    if issues:
        for issue in issues:
            lines.append(f"- `{issue.get('severity')}` `{issue.get('code')}`: {issue.get('message')}")
    else:
        lines.append("- No rule-based issues.")

    lines.extend(["", "## Recommendations", ""])
    recommendations = evaluation.get("recommendations", [])
    if recommendations:
        for item in recommendations:
            lines.append(f"- {item}")
    else:
        lines.append("- Inspect generated previews and confirm geometry matches the user request.")

    lines.extend(["", "## Previews", ""])
    for preview in report.get("previews", []):
        lines.append(f"- `{preview.get('path')}`")

    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return str(output_path)


def run_review(model, output_dir, basename="review", views=None, expected_outputs=None):
    """
    Run the full review and write review_report.json.

    Returns:
        (report, report_path).
    """
    output_dir = _expand_path(output_dir)
    report = build_review_report(
        model,
        output_dir=output_dir,
        basename=basename,
        views=views,
        expected_outputs=expected_outputs,
    )
    report_path = write_review_report(report, output_dir / f"{basename}_review_report.json")
    summary_path = write_markdown_summary(report, output_dir / f"{basename}_review_summary.md")
    report["summary_path"] = summary_path
    write_review_report(report, report_path)
    return report, report_path


def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="SOLIDWORKS çok açılı önizlemeleri dışa aktar ve yapılandırılmış inceleme raporu oluştur.")
    parser.add_argument("--file", help="Açılıp incelenecek SOLIDWORKS dosyası; verilmezse etkin belge incelenir.")
    parser.add_argument("--output-dir", required=True, help="Önizleme ve review_report.json çıktı dizini.")
    parser.add_argument("--basename", default="review", help="Çıktı dosya adı öneki.")
    parser.add_argument("--views", default="isometric,front,top,right", help="Virgülle ayrılmış görünüş listesi.")
    parser.add_argument("--expected", action="append", default=[], help="Beklenen çıktı dosyası; birden çok kez verilebilir.")
    parser.add_argument("--version", type=int, help="SOLIDWORKS yılı; örneğin 2024.")
    parser.add_argument("--silent-open", action="store_true", help="--file dosyasını sessiz aç.")
    parser.add_argument("--fail-on-warn", action="store_true", help="warn durumunda da sıfırdan farklı çıkış kodu döndür.")
    return parser.parse_args()


def main():
    """CLI entry point."""
    args = _parse_args()
    sw, model = connect_solidworks(version=args.version)
    if args.file:
        model = open_document(sw, args.file, silent=args.silent_open, raise_on_error=True)
    if model is None:
        raise RuntimeError("İncelenebilir etkin SOLIDWORKS belgesi yok")

    views = [item.strip() for item in args.views.split(",") if item.strip()]
    report, report_path = run_review(
        model,
        output_dir=args.output_dir,
        basename=args.basename,
        views=views,
        expected_outputs=args.expected,
    )
    evaluation = report["evaluation"]
    print(f"Rapor: {report_path}")
    print(f"Özet: {report.get('summary_path')}")
    print(f"Durum: {evaluation['status']} / Puan: {evaluation['score']}")
    if evaluation["issues"]:
        print("Sorunlar:")
        for issue in evaluation["issues"]:
            print(f"- [{issue['severity']}] {issue['code']}: {issue['message']}")
    if evaluation["status"] == "fail":
        return 2
    if args.fail_on_warn and evaluation["status"] == "warn":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
