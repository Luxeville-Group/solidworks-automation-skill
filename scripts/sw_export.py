"""
SOLIDWORKS file export utilities.
Supports STEP, STL, IGES, PDF, DXF/DWG, Parasolid, and other formats.
"""
import os
from pathlib import Path

try:
    from .sw_preflight import import_com_dependencies
    from .sw_connect import create_empty_dispatch_variant, get_com_member, open_document
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import create_empty_dispatch_variant, get_com_member, open_document

pythoncom, _win32com, VARIANT = import_com_dependencies()

SUPPORTED_BATCH_FORMATS = {".step", ".stp", ".stl", ".igs", ".iges", ".x_t", ".pdf", ".dxf", ".dwg"}


def _ensure_parent_dir(file_path):
    """Ensure the output file parent directory exists."""
    parent = os.path.dirname(os.path.abspath(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def export_to_step(model, output_path):
    """Export STEP format."""
    return _export_generic(model, output_path)


def export_to_stl(model, output_path, quality="fine"):
    """
    Export STL format.

    Args:
        quality: "coarse" | "fine" | "custom".
    """
    # Set STL quality.
    quality_map = {"coarse": 1, "fine": 0}
    if quality in quality_map:
        model.SetUserPreferenceIntegerValue(78, quality_map[quality])  # swSTLQuality
    return _export_generic(model, output_path)


def export_to_iges(model, output_path):
    """Export IGES format."""
    return _export_generic(model, output_path)


def export_to_parasolid(model, output_path):
    """Export Parasolid (.x_t) format."""
    return _export_generic(model, output_path)


def export_to_pdf(model, output_path, sheet_names=None):
    """
    Export a drawing to PDF.

    Args:
        model: IModelDoc2, which must be a drawing document.
        output_path: PDF file path.
        sheet_names: Sheet names; None exports all sheets.
    """
    sw = model.GetSldWorksObject()
    pdf_data = sw.GetExportFileData(1)  # swExportPDFData

    if sheet_names is None:
        sheet_names = get_com_member(model, "GetSheetNames")

    if pdf_data:
        pdf_data.SetSheets(0, sheet_names)

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    success = model.Extension.SaveAs(output_path, 0, 1, pdf_data, errors, warnings)

    _print_result("PDF", output_path, success, errors, warnings)
    return success


SW_EXPORT_TO_DWG_SHEET_METAL = 1
SW_SHEET_METAL_EXPORT_GEOMETRY = 1
SW_SHEET_METAL_EXPORT_HIDDEN_EDGES = 2
SW_SHEET_METAL_EXPORT_BEND_LINES = 4
SW_SHEET_METAL_EXPORT_SKETCHES = 8
SW_SHEET_METAL_EXPORT_MERGE_COPLANAR_FACES = 16
SW_SHEET_METAL_EXPORT_LIBRARY_FEATURES = 32
SW_SHEET_METAL_EXPORT_FORMING_TOOLS = 64
SW_SHEET_METAL_EXPORT_BOUNDING_BOX = 2048


def _sheet_metal_alignment_variant(alignment=None):
    """@brief Build the 12 double-precision alignment values required by ExportToDWG2."""
    values = tuple(alignment or (0.0,) * 12)
    if len(values) != 12:
        raise ValueError("Sac levha DXF hizalama dizisi 12 double değeri içermeli")
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, values)


def export_to_dxf(model, output_path):
    """
    Export DXF/DWG format for drawings or sheet-metal flat patterns.
    """
    doc_type = get_com_member(model, "GetType")
    if doc_type == 3:  # Drawing
        return _export_generic(model, output_path)
    else:
        # Parts default to flat-pattern geometry plus bend lines; remaining options use a bitmask.
        return export_flat_pattern_dxf(model, output_path)


def export_flat_pattern_dxf(
    model,
    output_path,
    *,
    include_bend_lines=True,
    include_sketches=False,
    include_hidden_edges=False,
    include_bounding_box=False,
    merge_coplanar_faces=False,
    alignment=None,
):
    """
    Export a sheet-metal flat pattern to DXF.

    Args:
        model: Sheet-metal part IModelDoc2.
    """
    model_path = str(get_com_member(model, "GetPathName") or "")
    if not model_path:
        raise ValueError("Flat pattern DXF dışa aktarımından önce sac levha parçasını kaydedin")

    output_path = os.path.abspath(os.path.expandvars(os.path.expanduser(output_path)))
    _ensure_parent_dir(output_path)
    options = SW_SHEET_METAL_EXPORT_GEOMETRY
    if include_bend_lines:
        options |= SW_SHEET_METAL_EXPORT_BEND_LINES
    if include_sketches:
        options |= SW_SHEET_METAL_EXPORT_SKETCHES
    if include_hidden_edges:
        options |= SW_SHEET_METAL_EXPORT_HIDDEN_EDGES
    if include_bounding_box:
        options |= SW_SHEET_METAL_EXPORT_BOUNDING_BOX
    if merge_coplanar_faces:
        options |= SW_SHEET_METAL_EXPORT_MERGE_COPLANAR_FACES

    return bool(model.ExportToDWG2(
        output_path,
        model_path,
        SW_EXPORT_TO_DWG_SHEET_METAL,
        True,
        _sheet_metal_alignment_variant(alignment),
        False,
        False,
        options,
        None,
    ))


def batch_export(sw, file_paths, output_dir, format_ext=".step"):
    """
    Batch-export files.

    Args:
        sw: ISldWorks application.
        file_paths: Source file paths.
        output_dir: Output directory.
        format_ext: Output extension (".step", ".stl", ".igs", ".pdf").
    """
    report = batch_export_formats(sw, file_paths, output_dir, [format_ext])
    results = []
    for document in report["documents"]:
        output = document.get("outputs", [{}])[0]
        results.append({
            "file": document["source"],
            "success": document["success"],
            "output": output.get("path"),
            "error": document.get("error") or output.get("error"),
        })
    return results


def _normalize_format(format_ext):
    """Normalize and validate batch-export extensions."""
    extension = str(format_ext).strip().lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension not in SUPPORTED_BATCH_FORMATS:
        raise ValueError(f"Toplu dışa aktarma biçimi henüz desteklenmiyor: {extension}")
    return extension


def _file_signature(path):
    """Return file-existence evidence identifying artifacts produced in this run."""
    target = Path(path)
    if not target.is_file():
        return None
    stat = target.stat()
    return stat.st_size, stat.st_mtime_ns


def _activate_source_document(sw, model, source_path):
    """@brief Activate and read back the source document so exporters such as STL do not use the active assembly accidentally."""
    title = str(get_com_member(model, "GetTitle") or "")
    if not title:
        raise RuntimeError("Kaynak belgede etkinleştirilebilir başlık yok")
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    try:
        active = sw.ActivateDoc3(title, False, 0, errors)
    except TypeError:
        ole_object = getattr(sw, "_oleobj_", None)
        if ole_object is None:
            raise
        dynamic_sw = _win32com.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
        active = dynamic_sw.ActivateDoc3(title, False, 0, errors)
    except Exception:
        try:
            sw.ActivateDoc2(title, False, errors)
        except TypeError:
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = _win32com.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            dynamic_sw.ActivateDoc2(title, False, errors)
        active = get_com_member(sw, "ActiveDoc")
    if active is None:
        raise RuntimeError(f"SOLIDWORKS kaynak belgeyi etkinleştiremedi: {source_path}")
    active_path = str(get_com_member(active, "GetPathName") or "")
    if not active_path or Path(active_path).resolve() != Path(source_path).resolve():
        raise RuntimeError(f"Etkin belge dışa aktarma kaynağıyla eşleşmiyor: active={active_path}, source={source_path}")
    return active


def _export_for_format(model, output_path, extension, stl_quality):
    """Route export formats through verified wrappers."""
    if extension in {".step", ".stp"}:
        return export_to_step(model, output_path)
    if extension == ".stl":
        return export_to_stl(model, output_path, quality=stl_quality)
    if extension in {".igs", ".iges"}:
        return export_to_iges(model, output_path)
    if extension == ".x_t":
        return export_to_parasolid(model, output_path)
    if extension == ".pdf":
        return export_to_pdf(model, output_path)
    if extension in {".dxf", ".dwg"}:
        return export_to_dxf(model, output_path)
    raise ValueError(f"Exporter yok: {extension}")


def batch_export_formats(
    sw,
    file_paths,
    output_dir,
    formats=(".step",),
    *,
    overwrite=False,
    close_documents=True,
    stl_quality="fine",
):
    """Batch-export SOLIDWORKS documents to multiple formats.

    Return each output size and produced_this_run evidence. Documents already open in SOLIDWORKS remain open.
    """
    source_paths = [str(Path(os.path.expandvars(str(path))).expanduser().resolve()) for path in file_paths]
    if not source_paths:
        raise ValueError("file_paths boş olamaz")
    extensions = list(dict.fromkeys(_normalize_format(item) for item in formats))
    if not extensions:
        raise ValueError("formats boş olamaz")
    output_root = Path(os.path.expandvars(str(output_dir))).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    claimed_outputs = set()
    documents = []

    for source_path in source_paths:
        source = Path(source_path)
        document_result = {"source": source_path, "success": False, "outputs": [], "was_open": False}
        if not source.is_file():
            document_result["error"] = "Kaynak dosya yok"
            documents.append(document_result)
            continue
        try:
            existing_model = sw.GetOpenDocumentByName(source_path)
        except Exception:
            existing_model = None
        was_open = bool(existing_model)
        document_result["was_open"] = was_open
        model = existing_model or open_document(sw, source_path, silent=True, raise_on_error=False)
        if model is None:
            document_result["error"] = "SOLIDWORKS kaynak dosyayı açamadı"
            documents.append(document_result)
            continue

        try:
            for extension in extensions:
                output_path = output_root / f"{source.stem}{extension}"
                output_key = str(output_path).casefold()
                before = _file_signature(output_path)
                output_result = {"format": extension, "path": str(output_path), "success": False}
                if output_key in claimed_outputs:
                    output_result["error"] = "Farklı kaynaklar aynı çıktı adını üretiyor; üzerine yazma engellendi"
                    document_result["outputs"].append(output_result)
                    continue
                claimed_outputs.add(output_key)
                if before is not None and not overwrite:
                    output_result["error"] = "Hedef dosya zaten var; üzerine yazmaya açıkça izin verilmedi"
                    document_result["outputs"].append(output_result)
                    continue
                try:
                    _activate_source_document(sw, model, source_path)
                    api_success = bool(_export_for_format(model, str(output_path), extension, stl_quality))
                    after = _file_signature(output_path)
                    produced = api_success and after is not None and after != before
                    output_result.update({
                        "success": bool(produced),
                        "api_success": api_success,
                        "exists": after is not None,
                        "size_bytes": after[0] if after else 0,
                        "produced_this_run": bool(produced),
                    })
                    if api_success and not produced:
                        output_result["error"] = "SOLIDWORKS başarı bildirdi ancak bu çalıştırmada yeni çıktı bulunamadı"
                except Exception as error:
                    output_result["error"] = str(error)
                document_result["outputs"].append(output_result)
        finally:
            if close_documents and not was_open:
                sw.CloseDoc(get_com_member(model, "GetTitle"))
        document_result["success"] = bool(document_result["outputs"]) and all(
            output["success"] for output in document_result["outputs"]
        )
        documents.append(document_result)

    output_count = sum(len(item["outputs"]) for item in documents)
    success_count = sum(
        1 for item in documents for output in item["outputs"] if output["success"]
    )
    report = {
        "success": bool(documents) and all(item["success"] for item in documents),
        "output_dir": str(output_root),
        "formats": extensions,
        "documents": documents,
        "summary": {"documents": len(documents), "outputs": output_count, "succeeded": success_count},
    }
    print(f"Toplu dışa aktarma tamamlandı: {success_count}/{output_count} çıktı başarılı")
    return report


def _export_generic(model, output_path):
    """Generic export function (STEP/STL/IGES/Parasolid/DXF)."""
    model.ClearSelection2(True)
    output_path = os.path.abspath(os.path.expandvars(os.path.expanduser(output_path)))
    _ensure_parent_dir(output_path)
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

    success = model.Extension.SaveAs(
        output_path, 0, 1, create_empty_dispatch_variant(), errors, warnings
    )

    ext = os.path.splitext(output_path)[1].upper()
    _print_result(ext, output_path, success, errors, warnings)
    return success


def _print_result(format_name, path, success, errors, warnings):
    """Print export results."""
    if success:
        print(f"{format_name} dışa aktarıldı: {path}")
    else:
        print(f"{format_name} dışa aktarma başarısız; hata kodu: {errors.value}, uyarı kodu: {warnings.value}")
