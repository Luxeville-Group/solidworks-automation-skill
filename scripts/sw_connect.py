"""
SOLIDWORKS connection utilities.
Provides methods for connecting to a SOLIDWORKS instance.
"""
import glob
import os
import tempfile
import time
from pathlib import Path
try:
    from .sw_file_load import SolidWorksDocumentOpenError, classify_sw_file_load_errors, classify_sw_file_load_warnings
except ImportError:
    from sw_file_load import SolidWorksDocumentOpenError, classify_sw_file_load_errors, classify_sw_file_load_warnings

try:
    from .sw_preflight import ensure_solidworks_installed, import_com_dependencies
except ImportError:
    from sw_preflight import ensure_solidworks_installed, import_com_dependencies

pythoncom, win32com_client, VARIANT = import_com_dependencies()
try:
    from .sw_process import solidworks_processes
except ImportError:
    from sw_process import solidworks_processes


DOC_TYPE_MAP = {
    "parça": 1,
    "parca": 1,
    "montaj": 2,
    "teknik çizim": 3,
    "teknik cizim": 3,
    "part": 1,
    "prt": 1,
    "sldprt": 1,
    "assembly": 2,
    "asm": 2,
    "sldasm": 2,
    "drawing": 3,
    "drw": 3,
    "slddrw": 3,
}

DOC_TYPE_LABELS = {
    "part": "parça",
    "assembly": "montaj",
    "drawing": "teknik çizim",
}

DEFAULT_TEMPLATE_PREFS = {
    "part": 8,       # swUserPreferenceStringValue_e.swDefaultTemplatePart
    "assembly": 9,   # swUserPreferenceStringValue_e.swDefaultTemplateAssembly
    "drawing": 10,   # swUserPreferenceStringValue_e.swDefaultTemplateDrawing
}

SW_ALWAYS_USE_DEFAULT_TEMPLATES = 111


class SolidWorksConnectionError(RuntimeError):
    """SOLIDWORKS connection error carrying a stage and error code."""

    def __init__(self, code, stage, message):
        self.code = code
        self.stage = stage
        super().__init__(f"[{code}] {stage}: {message}")


class _LaunchGuard:
    """Cross-process launch lock: named Mutex on Windows, exclusive lock file elsewhere."""

    def __init__(self, name="CADStudio.SolidWorks.Launch"):
        self.name = name
        self.handle = None
        self.path = Path(tempfile.gettempdir()) / "cad-studio-solidworks-launch.lock"
        self._owns_file = False

    def __enter__(self):
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            from ctypes import wintypes
            kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if not self.handle:
                raise SolidWorksConnectionError("SW_MUTEX", "locking", "SOLIDWORKS başlatma mutex oluşturulamadı")
            wait_result = kernel32.WaitForSingleObject(self.handle, 15000)
            if wait_result not in (0, 0x80):
                kernel32.CloseHandle(self.handle)
                self.handle = None
                raise SolidWorksConnectionError("SW_MUTEX_TIMEOUT", "locking", "Diğer başlatma görevi beklenirken zaman aşımı")
            return self

        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            self._owns_file = True
        except FileExistsError as exc:
            try:
                stale_pid = int(self.path.read_text(encoding="ascii").strip())
                os.kill(stale_pid, 0)
            except (ProcessLookupError, ValueError):
                self.path.unlink(missing_ok=True)
                return self.__enter__()
            raise SolidWorksConnectionError("SW_MUTEX_BUSY", "locking", "SOLIDWORKS başlatma görevi zaten var") from exc
        return self

    def __exit__(self, *_):
        if os.name == "nt" and self.handle:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
        elif self._owns_file:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._owns_file = False


_MEMBER_UNSET = object()


def get_com_member(obj, attr_name, *args, default=_MEMBER_UNSET):
    """
    Support COM members that pywin32 exposes as either properties or methods.

    Args:
        obj: COM object.
        attr_name: Member name.
        *args: Arguments supplied when the member is callable.
        default: Value for a missing member; omit to preserve AttributeError behavior.

    Returns:
        Member value or call result, or default when supplied for a missing member.
    """
    try:
        member = getattr(obj, attr_name)
    except AttributeError:
        if default is not _MEMBER_UNSET:
            return default
        raise
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as exc:
        message = str(exc)
        if "-2147352573" in message or "\u627e\u4e0d\u5230\u6210\u5458" in message or "Member not found" in message:
            return member
        raise


def safe_get_com_member(obj, attr_name, *args):
    """
    Read a COM member with support for pywin32 pseudo-callable properties.

    Keep this alias to express safe-read intent; get_com_member owns the implementation.
    """
    return get_com_member(obj, attr_name, *args)


def create_empty_dispatch_variant():
    """Create an empty Dispatch argument for COM interfaces."""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def normalize_doc_type(doc_type):
    """
    Normalize a document type.

    Args:
        doc_type: "part", "assembly", "drawing", or a common abbreviation/extension.

    Returns:
        (name, enum_value) tuple.
    """
    key = str(doc_type).strip().lower().lstrip(".")
    enum_value = DOC_TYPE_MAP.get(key)
    if enum_value is None:
        raise ValueError(f"Bilinmeyen belge türü: {doc_type}")

    name_map = {1: "part", 2: "assembly", 3: "drawing"}
    return name_map[enum_value], enum_value


def _expand_path(file_path):
    """Expand user directories and environment variables and return an absolute path."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(file_path)))


def _ensure_parent_dir(file_path):
    """Ensure the output file parent directory exists."""
    parent = os.path.dirname(_expand_path(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _prog_id_for_version(version):
    """Return the ProgID for a SOLIDWORKS release year."""
    if version is None:
        return "SldWorks.Application"
    try:
        year = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SOLIDWORKS sürümü yıl olmalı; örneğin 2024: {version}") from exc
    if year < 2010 or year > 2035:
        raise ValueError(f"Desteklenmeyen SOLIDWORKS sürüm yılı: {year}")
    return f"SldWorks.Application.{(year - 2000) + 8}"


def _read_active_document(sw):
    """Read the active document with support for COM property/method differences."""
    try:
        return get_com_member(sw, "ActiveDoc", default=None)
    except Exception:
        return None


def _wait_until_ready(sw, timeout_seconds):
    """Wait for readable COM state instead of a fixed sleep that can leave the UI unresponsive."""
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last_error = None
    while time.monotonic() < deadline:
        try:
            get_com_member(sw, "RevisionNumber")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise SolidWorksConnectionError(
        "SW_START_TIMEOUT", "ready", f"SOLIDWORKS başlatma zaman aşımı ({timeout_seconds:.1f}s): {last_error or 'COM hazır değil'}"
    )


def close_owned_solidworks(sw, started_by_cad_studio, expected_pid=None):
    """Quit only the SOLIDWORKS instance launched by the current CAD Studio session."""
    if not started_by_cad_studio:
        return False
    if expected_pid is not None:
        try:
            if int(get_com_member(sw, "GetProcessID")) != int(expected_pid):
                return False
        except Exception:
            return False
    for member_name in ("ExitApp", "Quit"):
        try:
            member = getattr(sw, member_name)
            member() if callable(member) else None
            return True
        except Exception:
            continue
    return False


def connect_solidworks(version=None, wait_seconds=5, visible=True, return_metadata=False):
    """
    Connect to a SOLIDWORKS instance.

    Args:
        version: Release year (such as 2024); None auto-detects.
        wait_seconds: Seconds to wait after launching a new instance.
        visible: Show the new instance window when True.

    Returns:
        (sw, model), where model may be None when no document is open.
    """
    ensure_solidworks_installed()
    prog_id = _prog_id_for_version(version)
    sw = None
    launched_here = False
    dispatched = False

    # Launch and attach share one mutex to prevent concurrent workers from launching instances.
    with _LaunchGuard():
        before = solidworks_processes()
        try:
            sw = win32com_client.GetActiveObject(prog_id)
            print(f"Çalışan SOLIDWORKS örneğine bağlanıldı (ProgID: {prog_id})")
        except Exception as attach_error:
            try:
                if before is None:
                    raise SolidWorksConnectionError("SW_PROCESS_STATE_UNAVAILABLE", "attach", "CAD süreç durumu okunamadı; belirsiz başlatma engellendi")
                if before and (version is None or any(year is None or year == int(version) for year in before.values())):
                    # Wait for an existing instance before ROT registration; never Dispatch a duplicate of the same version.
                    deadline = time.monotonic() + max(.1, float(wait_seconds))
                    while time.monotonic() < deadline:
                        try:
                            sw = win32com_client.GetActiveObject(prog_id)
                            break
                        except Exception:
                            time.sleep(.1)
                    if sw is None:
                        raise SolidWorksConnectionError("SW_INSTANCE_NOT_READY", "attach", "Mevcut örneğe henüz bağlanılamıyor; yinelenen başlatma engellendi")
                if sw is None:
                    sw = win32com_client.Dispatch(prog_id)
                    dispatched = True
                    try:
                        pid = int(get_com_member(sw, "GetProcessID"))
                        launched_here = before is not None and pid > 0 and pid not in before
                    except Exception:
                        launched_here = False
                try:
                    sw.Visible = visible
                except Exception:
                    pass
                print(f"SOLIDWORKS bağlantısı kuruldu (ProgID: {prog_id})")
                _wait_until_ready(sw, wait_seconds)
            except SolidWorksConnectionError:
                close_owned_solidworks(sw, launched_here)
                raise
            except Exception as launch_error:
                close_owned_solidworks(sw, launched_here)
                raise SolidWorksConnectionError(
                    "SW_LAUNCH_FAILED", "launch", f"Başlatılamadı: {prog_id}: {launch_error}; attach={attach_error}"
                ) from launch_error

        _wait_until_ready(sw, wait_seconds)
        if dispatched and before is not None:
            pid = int(get_com_member(sw, "GetProcessID"))
            launched_here = pid > 0 and pid not in before
        actual = get_sw_version(sw)
        if version is not None and actual["year"] != int(version):
            close_owned_solidworks(sw, launched_here)
            raise SolidWorksConnectionError("SW_VERSION_MISMATCH", "verify", f"İstenen {version}; bağlanılan {actual['year']}")

    if sw is None:
        raise SolidWorksConnectionError("SW_NO_INSTANCE", "connect", "SOLIDWORKS COM örneği alınamadı")

    model = _read_active_document(sw)
    if model:
        doc_types = {1: "parça", 2: "montaj", 3: "teknik çizim"}
        doc_type = get_com_member(model, "GetType")
        title = get_com_member(model, "GetTitle")
        print(f"Etkin belge: {title} (tür: {doc_types.get(doc_type, 'Bilinmiyor')})")
    else:
        print("Şu anda açık belge yok")

    metadata = {
        "prog_id": prog_id,
        "requested_version": int(version) if version is not None else None,
        "started_by_cad_studio": launched_here,
        "actual_version": actual["year"],
        "actual_revision": actual["revision"],
        "process_id": get_com_member(sw, "GetProcessID", default=None),
    }
    return (sw, model, metadata) if return_metadata else (sw, model)


def get_sw_version(sw):
    """Get SOLIDWORKS version information."""
    rev = get_com_member(sw, "RevisionNumber")
    major = int(rev.split(".")[0])
    year = major - 8 + 2000
    return {"revision": rev, "year": year, "major": major}


def find_template(sw, doc_type="part"):
    """
    Find a SOLIDWORKS document template automatically.

    Args:
        sw: SOLIDWORKS application object.
        doc_type: "part" | "assembly" | "drawing".

    Returns:
        Template file path string.
    """
    doc_type, _ = normalize_doc_type(doc_type)

    type_map = {
        "part": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["part"]), "*.prtdot"),
        "assembly": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["assembly"]), "*.asmdot"),
        "drawing": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["drawing"]), "*.drwdot"),
    }

    default_path, pattern = type_map.get(doc_type, type_map["part"])
    if default_path:
        for candidate_root in str(default_path).split(";"):
            candidate_root = _expand_path(candidate_root.strip().strip('"'))
            if not candidate_root:
                continue

            if os.path.isfile(candidate_root):
                return candidate_root

            if os.path.isdir(candidate_root):
                matches = glob.glob(os.path.join(candidate_root, pattern))
                if matches:
                    return matches[0]

    search_dirs = [
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\chinese-simplified",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english",
    ]
    for search_dir in search_dirs:
        matches = glob.glob(os.path.join(os.path.expandvars(search_dir), pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(f"Bulunamadı: {doc_type} şablon dosyası; yolu elle belirtin")


def ensure_default_templates(sw):
    """
    @brief Configure default templates and disable the new-file template selection prompt.
    @param sw SOLIDWORKS application object.
    @return Dictionary of verified default template paths.
    """
    templates = {}
    for doc_type, preference in DEFAULT_TEMPLATE_PREFS.items():
        template_path = find_template(sw, doc_type)
        templates[doc_type] = template_path
        current_path = str(sw.GetUserPreferenceStringValue(preference) or "")
        if _expand_path(current_path) != _expand_path(template_path):
            sw.SetUserPreferenceStringValue(preference, template_path)
    try:
        sw.SetUserPreferenceToggle(SW_ALWAYS_USE_DEFAULT_TEMPLATES, True)
    except Exception as exc:
        print(f"Bilgi: varsayılan şablonu her zaman kullan ayarı uygulanamadı: {exc}")
    return templates


def snapshot_open_documents(sw, *, strict=False):
    """
    Snapshot titles of currently open documents.

    ISldWorks.GetDocuments returns all open session documents; some versions return None instead of an empty array. Titles identify newly created documents because unsaved NewDocument results have an empty GetPathName and cannot be distinguished by path.
    """
    titles = set()
    try:
        documents = get_com_member(sw, "GetDocuments")
    except Exception as error:
        if strict:
            raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "documents", "Açık belge listesi okunamadı; yeni belge oluşturma engellendi") from error
        return titles
    for document in documents or ():
        try:
            titles.add(str(get_com_member(document, "GetTitle")))
        except Exception as error:
            if strict:
                raise SolidWorksConnectionError("SW_DOCUMENT_STATE_UNAVAILABLE", "documents", "Mevcut belge kimliği doğrulanamadı; yeni belge oluşturma engellendi") from error
            continue
    return titles


def _find_new_document(sw, preexisting_titles):
    """
    Locate the actual new document after creation.

    Return only a title absent from preexisting_titles. Never fall back to bare ActiveDoc: if NewDocument fails or returns None, ActiveDoc may be another user document and subsequent features would silently be created in that wrong document.
    """
    try:
        documents = get_com_member(sw, "GetDocuments")
    except Exception:
        return None
    for document in documents or ():
        try:
            title = str(get_com_member(document, "GetTitle"))
        except Exception:
            continue
        if title and title not in preexisting_titles:
            return document
    return None


def new_document(sw, doc_type="part", template_path=None, *, max_documents=None):
    """
    Create a new document.

    Args:
        sw: SOLIDWORKS application object.
        doc_type: "part" | "assembly" | "drawing".
        template_path: Template path; None auto-detects.

    Returns:
        Newly created IModelDoc2.

    Raises:
        RuntimeError: Creation failed. The earlier implementation blindly used sw.ActiveDoc when NewDocument returned None, risking an existing user document. This implementation compares document titles and fails explicitly if no new document is identified.
    """
    doc_type, _ = normalize_doc_type(doc_type)
    if not template_path:
        template_path = find_template(sw, doc_type)
    else:
        template_path = _expand_path(template_path)

    preexisting_titles = snapshot_open_documents(sw, strict=True)
    budget = int(max_documents if max_documents is not None else os.environ.get("SW_MAX_DOCUMENTS", "8"))
    if budget < 1 or len(preexisting_titles) >= budget:
        raise SolidWorksConnectionError("SW_DOCUMENT_BUDGET", "new_document", f"Açık belge sayısı bütçeye ulaştı: {budget}; bu çalıştırmadaki belgeleri kaydedip kapatın")

    model = sw.NewDocument(template_path, 0, 0, 0)
    if model is not None:
        # Normal path: NewDocument returns a document; still verify it is new
        # because some versions can return a stale reference.
        try:
            if str(get_com_member(model, "GetTitle")) in preexisting_titles:
                model = None
        except Exception:
            pass

    if model is None:
        # Fallback: when NewDocument returns None, poll for a new title absent from the snapshot.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            model = _find_new_document(sw, preexisting_titles)
            if model is not None:
                break
            time.sleep(0.25)

    if model is None:
        raise RuntimeError(
            f"Oluşturulacak {DOC_TYPE_LABELS.get(doc_type, doc_type)} belgesi başarısız: SOLIDWORKS yeni belge döndürmedi."
            f"Şablonun kullanılabildiğini doğrulayın ({template_path}) ve otomasyonu engelleyen modal iletişim kutusu bulunmadığını denetleyin."
        )

    print(f"Yeni oluşturulan {DOC_TYPE_LABELS.get(doc_type, doc_type)} belgesi")
    return model


def open_document(sw, file_path, read_only=False, silent=False, raise_on_error=False):
    """
    Open an existing document.

    Args:
        sw: SOLIDWORKS application object.
        file_path: Full file path.
        read_only: Open read-only when True.
        silent: Open silently when True.
        raise_on_error: Raise if opening fails.

    Returns:
        IModelDoc2 object.
    """
    file_path = _expand_path(file_path)
    if not os.path.exists(file_path):
        message = f"Dosya yok: {file_path}"
        if raise_on_error:
            raise FileNotFoundError(message)
        print(message)
        return None

    # Assemblies load component documents into the session; another OpenDoc6 may return
    # swFileWithSameTitleAlreadyOpen. Reuse the same-path object to preserve document ownership.
    try:
        existing_model = sw.GetOpenDocumentByName(file_path)
    except Exception:
        existing_model = None
    if existing_model is not None:
        print(f"Açık belge yeniden kullanıldı: {file_path}")
        return existing_model

    ext = os.path.splitext(file_path)[1].lower()
    foreign_exts = {".step", ".stp", ".igs", ".iges"}
    type_map = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    options = 2 if read_only else 0  # swOpenDocOptions_ReadOnly = 2
    if silent:
        options |= 1  # swOpenDocOptions_Silent = 1

    if ext in foreign_exts:
        if read_only:
            print("Bilgi: LoadFile4 ile dış CAD dosyası içe aktarımı read_only desteklemiyor; parametre yok sayıldı")
        if silent:
            print("Bilgi: LoadFile4 dış CAD içe aktarımında OpenDoc6 silent seçeneğini desteklemiyor; parametre yok sayıldı")
        ensure_default_templates(sw)
        import_data = sw.GetImportFileData(file_path)
        if import_data is None:
            message = f"İçe aktarma verisi alınamadı: {file_path}"
            if raise_on_error:
                raise RuntimeError(message)
            print(message)
            return None
        # For foreign files other than DXF/DWG and Pro/E, pass "r" to import as a new SOLIDWORKS document;
        # an empty string may open a blocking template selection dialog in some SW2024 environments.
        try:
            model = sw.LoadFile4(file_path, "r", import_data, errors)
        except TypeError:
            # The SW2026 makepy strongly typed proxy applies int(VARIANT) again to the LoadFile4 [out] long,
            # matching the known OpenDoc6 issue. A dynamic proxy
            # preserves the by-ref error code while reusing the import options already obtained.
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = win32com_client.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            model = dynamic_sw.LoadFile4(file_path, "r", import_data, errors)
        warnings.value = 0
    else:
        doc_type = type_map.get(ext, 1)
        try:
            model = sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        except TypeError:
            # The SW2024 makepy strongly typed proxy may apply int(VARIANT) again to [out] long;
            # a dynamic proxy passes the explicit by-ref VARIANT correctly to native OpenDoc6.
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = win32com_client.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            model = dynamic_sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        if isinstance(model, (tuple, list)):
            values = list(model)
            model = values[0] if values else None
            if len(values) > 1 and values[1] is not None:
                errors.value = int(values[1])
            if len(values) > 2 and values[2] is not None:
                warnings.value = int(values[2])
    if model:
        print(f"Açıldı: {file_path}")
    else:
        message = f"Açma başarısız; hata kodu: {errors.value} ({classify_sw_file_load_errors(errors.value)}), uyarı kodu: {warnings.value} ({classify_sw_file_load_warnings(warnings.value)})"
        if raise_on_error:
            raise SolidWorksDocumentOpenError(message, errors.value, warnings.value)
        print(message)
    return model


def save_document(model, file_path=None):
    """
    Save a document.

    Args:
        model: IModelDoc2 object.
        file_path: Save-as path; None saves at the current location.

    Returns:
        bool indicating success.
    """
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

    if file_path:
        file_path = _expand_path(file_path)
        _ensure_parent_dir(file_path)
        success = model.Extension.SaveAs(
            file_path, 0, 1, create_empty_dispatch_variant(), errors, warnings
        )
    else:
        success = model.Save3(1, errors, warnings)

    if success:
        print(f"Kaydedildi: {file_path or get_com_member(model, 'GetPathName')}")
    else:
        print(f"Kaydetme başarısız; hata kodu: {errors.value}, uyarı kodu: {warnings.value}")
    return bool(success)


def mm(value):
    """Convert millimeters to meters (SOLIDWORKS API units)."""
    return value / 1000.0


def deg(value):
    """Convert degrees to radians."""
    import math
    return value * math.pi / 180.0
