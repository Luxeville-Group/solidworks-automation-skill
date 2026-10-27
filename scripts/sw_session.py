"""
SOLIDWORKS session facade API.

A convenient facade over COM helpers for scripts and AI agents composing open/create/save/export/close workflows. Lower-level helpers remain in sw_connect.py, sw_part.py, sw_export.py, and related modules for finer control.
"""
from pathlib import Path
import os

try:
    from .sw_connect import close_owned_solidworks, connect_solidworks, get_com_member, new_document, open_document, save_document
    from .sw_export import export_to_dxf, export_to_iges, export_to_pdf, export_to_stl, export_to_step
except ImportError:
    from sw_connect import close_owned_solidworks, connect_solidworks, get_com_member, new_document, open_document, save_document
    from sw_export import export_to_dxf, export_to_iges, export_to_pdf, export_to_stl, export_to_step


EXPORTERS = {
    ".step": export_to_step,
    ".stp": export_to_step,
    ".stl": export_to_stl,
    ".iges": export_to_iges,
    ".igs": export_to_iges,
    ".pdf": export_to_pdf,
    ".dxf": export_to_dxf,
    ".dwg": export_to_dxf,
}


class SolidWorksSession:
    """
    SOLIDWORKS automation session.

    Example:
        session = SolidWorksSession()
        model = session.new_part()
        session.save(model, r"C:\\temp\\part.sldprt")
        session.export(model, r"C:\\temp\\part.step")
    """

    def __init__(self, version=None, wait_seconds=5, visible=True, *, max_documents=8):
        """
        Initialize and connect to SOLIDWORKS.

        Args:
            version: Release year; current acceptance target is 2026. None connects to the default ProgID.
            wait_seconds: Wait after launching a new instance.
            visible: Show a newly launched instance window.
        """
        self.sw, self.model, self.connection_info = connect_solidworks(
            version=version,
            wait_seconds=wait_seconds,
            visible=visible,
            return_metadata=True,
        )
        self.max_documents = int(max_documents)
        if self.max_documents < 1:
            raise ValueError("Belge bütçesi sıfırdan büyük olmalı")
        self._owned_documents = []

    def __enter__(self):
        """@brief Enter a controlled session; automatic cleanup applies only to documents registered in this run."""
        return self

    def __exit__(self, *_):
        """@brief Clean up owned documents on exit; keep shared instances and user documents open."""
        self.close_owned_documents()
        self.quit_owned_instance()

    def _documents(self):
        """@brief Read current documents; failure never implies absence of user documents."""
        return list(get_com_member(self.sw, "GetDocuments") or [])

    def _remember(self, model):
        """@brief Register only documents actually created or newly opened in this run."""
        if model is not None and not any(item is model for item in self._owned_documents):
            self._owned_documents.append(model)
        return model

    def close_owned_documents(self):
        """@brief Clean up this run documents; never use stale titles to close other documents through invalid proxies."""
        for model in list(reversed(self._owned_documents)):
            try:
                self.close(model=model)
            except Exception:
                # SOLIDWORKS may already have unloaded dependencies; never reuse stale titles.
                pass
        self._owned_documents.clear()

    @property
    def active_doc(self):
        """Return the active document and synchronize session.model."""
        self.model = self.sw.ActiveDoc
        return self.model

    def new(self, doc_type="part", template_path=None):
        """
        Create a document.

        Args:
            doc_type: "part", "assembly", "drawing", or a common extension.
            template_path: Explicit template; None auto-detects.
        """
        self.model = new_document(self.sw, doc_type=doc_type, template_path=template_path, max_documents=self.max_documents)
        self._remember(self.model)
        return self.model

    def new_part(self, template_path=None):
        """Create a part document."""
        return self.new("part", template_path=template_path)

    def new_assembly(self, template_path=None):
        """Create an assembly document."""
        return self.new("assembly", template_path=template_path)

    def new_drawing(self, template_path=None):
        """Create a drawing document."""
        return self.new("drawing", template_path=template_path)

    def open(self, file_path, read_only=False, silent=False, raise_on_error=True):
        """
        Open a document.

        Args:
            file_path: SOLIDWORKS or interchange-format path.
            read_only: Open read-only.
            silent: Open silently.
            raise_on_error: Raise if opening fails.
        """
        before = {os.path.normcase(str(get_com_member(doc, "GetPathName") or "")) for doc in self._documents()}
        requested = os.path.normcase(os.path.abspath(os.path.expandvars(str(file_path))))
        if requested not in before and len(self._documents()) >= self.max_documents:
            raise RuntimeError("Açık belge sayısı oturum bütçesine ulaştı")
        self.model = open_document(
            self.sw,
            file_path,
            read_only=read_only,
            silent=silent,
            raise_on_error=raise_on_error,
        )
        if requested not in before:
            self._remember(self.model)
        return self.model

    def save(self, model=None, file_path=None):
        """
        Save a document.

        Args:
            model: Document; None uses the active document.
            file_path: Save-as path; None saves at the current location.
        """
        model = model if model is not None else self.model
        if model is None:
            raise RuntimeError("Kaydedilebilir etkin belge yok")
        return save_document(model, file_path=file_path)

    def export(self, model=None, output_path=None, format_ext=None, **kwargs):
        """
        Export by output extension.

        Args:
            model: Document; None uses the active document.
            output_path: Output file path.
            format_ext: Explicit extension; None infers it from output_path.
            **kwargs: Format-specific arguments such as STL quality.
        """
        model = model if model is not None else self.model
        if model is None:
            raise RuntimeError("Dışa aktarılabilir etkin belge yok")
        if not output_path:
            raise ValueError("output_path gerekli")

        output = Path(os.path.expandvars(str(output_path))).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        ext = (format_ext or output.suffix).lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        exporter = EXPORTERS.get(ext)
        if exporter is None:
            raise ValueError(f"Dışa aktarma biçimi henüz desteklenmiyor: {ext}")
        return exporter(model, str(output), **kwargs)

    def close(self, model=None, title=None):
        """
        Close a document.

        Args:
            model: Document; None uses title or the active document.
            title: Known document title to close.
        """
        if title is None:
            model = model if model is not None else self.model
            if model is None:
                return False
            title = get_com_member(model, "GetTitle")
        is_current_model = False
        if self.model:
            try:
                is_current_model = get_com_member(self.model, "GetTitle") == title
            except Exception:
                is_current_model = True
        if model is not None:
            try:
                from .sw_part import clear_sketch_selection_cache
            except ImportError:
                from sw_part import clear_sketch_selection_cache
            clear_sketch_selection_cache(model)
        self.sw.CloseDoc(title)
        self._owned_documents = [item for item in self._owned_documents if item is not model]
        if is_current_model:
            self.model = self.sw.ActiveDoc
        return True

    def quit_owned_instance(self):
        """Quit only an instance started by this session; attaching to a user instance never authorizes quitting it."""
        if self._documents():
            return False
        return close_owned_solidworks(
            self.sw,
            bool(self.connection_info.get("started_by_cad_studio")),
            self.connection_info.get("process_id"),
        )


def session(version=None, wait_seconds=5, visible=True):
    """
    Convenience constructor for SolidWorksSession.

    Arguments match SolidWorksSession.
    """
    return SolidWorksSession(version=version, wait_seconds=wait_seconds, visible=visible)
