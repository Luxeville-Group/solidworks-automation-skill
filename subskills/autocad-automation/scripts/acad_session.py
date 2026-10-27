# -*- coding: utf-8 -*-
"""@file acad_session.py
@brief AutoCAD COM sessions and common drawing wrappers.

These wrappers remain thin and transparent to help compare official documentation with local results.
"""

from __future__ import annotations

import ctypes
import math
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence, Tuple

try:
    import pythoncom
    import win32com.client
except Exception as exc:  # pragma: no cover - environment-dependent
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]
    _IMPORT_ERROR: Optional[BaseException] = exc
else:
    _IMPORT_ERROR = None


PointLike = Sequence[float]
_RETRYABLE_COM_HRESULTS = {-2147418111, -2147417846}


def _retry_com_busy(operation, label: str, attempts: int = 10) -> Any:
    """@brief Retry transient COM rejections caused by busy AutoCAD with bounded backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            hresult = getattr(exc, "hresult", exc.args[0] if exc.args else None)
            if hresult not in _RETRYABLE_COM_HRESULTS:
                raise
            last_error = exc
            time.sleep(0.08 + attempt * 0.06)
    raise RuntimeError(f"AutoCAD remains busy; cannot complete operation: {label}") from last_error


def _window_process_id(app: Any) -> Optional[int]:
    """@brief Obtain the exact process PID from AutoCAD's main window handle."""
    try:
        hwnd = int(app.HWND)
        process_id = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return int(process_id.value) or None
    except Exception:
        return None


def _process_is_running(process_id: int) -> bool:
    """@brief Use Win32 to check whether the specified PID remains active."""
    try:
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(process_id))
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


def _wait_for_process_exit(
    process_id: int,
    *,
    timeout_s: float,
    poll_interval_s: float = 0.1,
) -> bool:
    """@brief Wait a bounded time for the exact PID to exit, rechecking at the timeout boundary."""
    interval = max(float(poll_interval_s), 0.01)
    attempts = max(1, int(math.ceil(max(float(timeout_s), 0.0) / interval)))
    for _ in range(attempts):
        if not _process_is_running(process_id):
            return True
        time.sleep(interval)
    return not _process_is_running(process_id)


def _terminate_owned_process(process_id: int) -> bool:
    """@brief Terminate only the exact PID confirmed by window handle as owned by this task."""
    try:
        handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, int(process_id))
        if not handle:
            return not _process_is_running(process_id)
        try:
            return bool(ctypes.windll.kernel32.TerminateProcess(handle, 1))
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


def require_pywin32() -> None:
    """@brief Ensure pywin32 is available."""
    if _IMPORT_ERROR is not None:
        raise RuntimeError("pywin32 missing; first run: python -m pip install pywin32") from _IMPORT_ERROR


def mm(value: float) -> float:
    """@brief AutoCAD database values are unitless; default convention is 1 value = 1 mm."""
    return float(value)


def acad_point(values: PointLike) -> Any:
    """@brief Convert to the 3D point array required by AutoCAD COM.

    @param values Two- or three-dimensional coordinates.
    @return COM VARIANT array.
    """
    require_pywin32()
    xyz = list(values)
    if len(xyz) == 2:
        xyz.append(0.0)
    if len(xyz) != 3:
        raise ValueError(f"An AutoCAD point requires two or three numbers: {values!r}")
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(float(v) for v in xyz))


def acad_double_array(values: Iterable[float]) -> Any:
    """@brief Convert to an AutoCAD COM double-precision array."""
    require_pywin32()
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8,
        tuple(float(v) for v in values),
    )


def connect_autocad(
    create_if_missing: bool = True,
    visible: bool = True,
    *,
    return_ownership: bool = False,
) -> Any:
    """@brief Connect to or start AutoCAD.

    @param create_if_missing Start AutoCAD if no running instance exists.
    @param visible Whether to display the AutoCAD window.
    @param return_ownership Also return whether this call started a new instance.
    @return AutoCAD Application COM object.
    """
    require_pywin32()
    pythoncom.CoInitialize()
    started = False
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        if not create_if_missing:
            raise
        # Dispatch may reattach to an existing singleton; DispatchEx establishes reliable process ownership.
        app = win32com.client.DispatchEx("AutoCAD.Application")
        started = True
    try:
        app.Visible = visible
    except Exception:
        pass
    return (app, started) if return_ownership else app


class AutoCADSession:
    """@brief Manage an AutoCAD COM session."""

    def __init__(self, create_if_missing: bool = True, visible: bool = True) -> None:
        self.create_if_missing = create_if_missing
        self.visible = visible
        self.app: Any = None
        self.doc: Any = None
        self.started_by_session = False
        self.owned_process_id: Optional[int] = None
        self.forced_termination_used = False
        self.last_cleanup: dict[str, Any] = {}

    def connect(self) -> "AutoCADSession":
        """@brief Connect to AutoCAD and attempt to bind the active document."""
        self.app, self.started_by_session = connect_autocad(
            self.create_if_missing,
            self.visible,
            return_ownership=True,
        )
        self.forced_termination_used = False
        self.last_cleanup = {}
        self.ensure_visible()
        if self.started_by_session:
            for _ in range(30):
                self.owned_process_id = _window_process_id(self.app)
                if self.owned_process_id is not None:
                    break
                time.sleep(0.1)
        try:
            self.doc = self.app.ActiveDocument
        except Exception:
            self.doc = None
        return self

    def active_document(self) -> Any:
        """@brief Return the active document; raise an error if none exists."""
        if self.doc is not None:
            return self.doc
        if self.app is None:
            self.connect()
        try:
            self.doc = self.app.ActiveDocument
        except Exception as exc:
            raise RuntimeError("AutoCAD has no active document; call new_document() or open_document() first.") from exc
        return self.doc

    def refresh_document_proxy(self) -> Any:
        """@brief Rebind the active document to bypass stale AutoCAD dynamic-proxy caches."""
        if self.app is None:
            self.connect()
        last_error: Optional[Exception] = None
        for attempt in range(8):
            try:
                document = self.app.ActiveDocument
                _ = document.Name
                self.doc = document
                return document
            except Exception as exc:
                last_error = exc
                time.sleep(0.08 + attempt * 0.04)
        if last_error is not None:
            raise RuntimeError("Failed to refresh the AutoCAD active-document proxy.") from last_error
        raise RuntimeError("Failed to refresh the AutoCAD active-document proxy.")

    def _documents_collection(self) -> Any:
        """@brief Obtain a stable Documents collection proxy."""
        if self.app is None:
            self.connect()
        last_error: Optional[Exception] = None
        for _ in range(20):
            try:
                documents = self.app.Documents
                _ = documents.Count
                return documents
            except Exception as exc:
                last_error = exc
                try:
                    # AutoCAD 2024 dynamic proxies may hide Count and member introspection;
                    # if the collection property is readable, let Add/Open and higher-level retries verify it.
                    documents = self.app.Documents
                    return documents
                except Exception:
                    pass
                time.sleep(0.2)
        if last_error is not None:
            raise RuntimeError("The AutoCAD Documents collection is currently unavailable.") from last_error
        raise RuntimeError("The AutoCAD Documents collection is currently unavailable.")

    def new_document(self, template: Optional[str] = None) -> Any:
        """@brief Create a DWG document."""
        if self.app is None:
            self.connect()
        documents = self._documents_collection()
        add_error: Optional[Exception] = None
        added = False
        for attempt in range(20):
            try:
                if template:
                    documents.Add(str(template))
                else:
                    documents.Add()
                added = True
                break
            except Exception as exc:
                add_error = exc
                time.sleep(0.15 + attempt * 0.08)
        if not added:
            raise RuntimeError("AutoCAD document creation call failed.") from add_error
        # Immediately after startup or drawing creation, ActiveDocument may return an unstable proxy;
        # retry briefly, then fall back to the last drawing in the Documents collection.
        last_error: Optional[Exception] = None
        for _ in range(60):
            try:
                self.doc = self.app.ActiveDocument
                _ = self.doc.Name
                return self.doc
            except Exception as exc:
                last_error = exc
            try:
                self.doc = documents.Item(documents.Count - 1)
                _ = self.doc.Name
                return self.doc
            except Exception as exc:
                last_error = exc
            time.sleep(0.25)
        if last_error is not None:
            raise RuntimeError("Could not obtain a stable document object after AutoCAD document creation.") from last_error
        return self.doc

    def open_document(self, path: str | Path, read_only: bool = False) -> Any:
        """@brief Open a DWG/DXF document."""
        if self.app is None:
            self.connect()
        target = Path(path).resolve()
        if not target.exists():
            raise FileNotFoundError(str(target))
        last_error: Optional[Exception] = None
        for _ in range(20):
            documents = self._documents_collection()
            try:
                self.doc = documents.Open(str(target), bool(read_only))
                _ = self.doc.Name
                return self.doc
            except Exception as exc:
                last_error = exc
                time.sleep(0.2)
        if last_error is not None:
            raise RuntimeError(f"AutoCAD could not open document: {target}") from last_error
        return self.doc

    def ensure_visible(self) -> None:
        """@brief Ensure the AutoCAD window is visible."""
        if self.app is None:
            self.connect()
        try:
            self.app.Visible = True
        except Exception:
            pass

    def activate_window(self) -> None:
        """@brief Try to bring AutoCAD's main window forward so the user can watch drawing progress."""
        if self.app is None:
            self.connect()
        try:
            hwnd = int(self.app.HWND)
        except Exception:
            return
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 3)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    @property
    def model(self) -> Any:
        """@brief ModelSpace of the current document."""
        try:
            return _retry_com_busy(lambda: self.active_document().ModelSpace, "Read ModelSpace")
        except AttributeError:
            # After SaveAs, the old dynamic Document proxy may survive without exposing ModelSpace.
            return _retry_com_busy(lambda: self.refresh_document_proxy().ModelSpace, "Rebind ModelSpace")

    def create_layer(self, name: str, color: Optional[int] = None, linetype: Optional[str] = None) -> Any:
        """@brief Create or retrieve a layer.

        @param name Layer name.
        @param color AutoCAD ACI color index.
        @param linetype Linetype name.
        """
        doc = self.active_document()
        layers = doc.Layers
        try:
            layer = layers.Item(name)
        except Exception:
            _retry_com_busy(lambda: layers.Add(name), f"Create layer {name}")
            # SWIG/pywin32 may wrap Add's return as a collection-method proxy; rebind by name.
            layer = _retry_com_busy(lambda: self.active_document().Layers.Item(name), f"Rebind layer {name}")
        if color is not None:
            _retry_com_busy(lambda: setattr(layer, "Color", int(color)), f"Set layer color {name}")
        if linetype:
            try:
                _retry_com_busy(lambda: self.active_document().Linetypes.Load(linetype, "acad.lin"), f"Load linetype {linetype}")
            except Exception:
                pass
            layer = _retry_com_busy(lambda: self.active_document().Layers.Item(name), f"Rebind layer {name}")
            _retry_com_busy(lambda: setattr(layer, "Linetype", linetype), f"Set layer linetype {name}")
        return layer

    def set_current_layer(self, name: str) -> None:
        """@brief Set the current layer."""
        self.active_document().ActiveLayer = self.create_layer(name)

    def _apply_entity_options(self, entity: Any, layer: Optional[str] = None, color: Optional[int] = None) -> Any:
        """@brief Apply common entity properties."""
        if layer:
            _retry_com_busy(lambda: self.create_layer(layer), f"Create layer {layer}")
            _retry_com_busy(lambda: setattr(entity, "Layer", layer), f"Set entity layer {layer}")
        if color is not None:
            _retry_com_busy(lambda: setattr(entity, "Color", int(color)), "Set entity color")
        return entity

    def add_line(self, start: PointLike, end: PointLike, layer: Optional[str] = None, color: Optional[int] = None) -> Any:
        """@brief Add a line."""
        entity = _retry_com_busy(
            lambda: self.model.AddLine(acad_point(start), acad_point(end)),
            "Create line",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_circle(
        self,
        center: PointLike,
        radius: float,
        layer: Optional[str] = None,
        color: Optional[int] = None,
    ) -> Any:
        """@brief Add a circle."""
        entity = _retry_com_busy(
            lambda: self.model.AddCircle(acad_point(center), float(radius)),
            "Create circle",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_lwpolyline(
        self,
        points: Sequence[Sequence[float]],
        closed: bool = False,
        layer: Optional[str] = None,
        color: Optional[int] = None,
    ) -> Any:
        """@brief Add a 2D lightweight polyline."""
        if len(points) < 2:
            raise ValueError("A polyline requires at least two points.")
        flat = []
        for point in points:
            if len(point) < 2:
                raise ValueError(f"A 2D polyline point requires at least x/y: {point!r}")
            flat.extend([float(point[0]), float(point[1])])
        entity = _retry_com_busy(
            lambda: self.model.AddLightWeightPolyline(acad_double_array(flat)),
            "Create lightweight polyline",
        )
        _retry_com_busy(lambda: setattr(entity, "Closed", bool(closed)), "Set polyline closure")
        return self._apply_entity_options(entity, layer, color)

    def add_rectangle(
        self,
        origin: Sequence[float],
        width: float,
        height: float,
        layer: Optional[str] = None,
        color: Optional[int] = None,
    ) -> Any:
        """@brief Add a closed rectangle from its lower-left corner, width, and height."""
        x = float(origin[0])
        y = float(origin[1])
        w = float(width)
        h = float(height)
        return self.add_lwpolyline(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
            closed=True,
            layer=layer,
            color=color,
        )

    def add_text(
        self,
        text: str,
        point: PointLike,
        height: float,
        layer: Optional[str] = None,
        color: Optional[int] = None,
    ) -> Any:
        """@brief Add single-line text."""
        entity = _retry_com_busy(
            lambda: self.model.AddText(str(text), acad_point(point), float(height)),
            "Create text",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_mtext(
        self,
        text: str,
        point: PointLike,
        width: float,
        layer: Optional[str] = None,
        color: Optional[int] = None,
    ) -> Any:
        """@brief Add multiline text."""
        entity = _retry_com_busy(
            lambda: self.model.AddMText(acad_point(point), float(width), str(text)),
            "Create multiline text",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_dim_aligned(
        self,
        point1: PointLike,
        point2: PointLike,
        text_position: PointLike,
        layer: Optional[str] = "DIM",
        color: Optional[int] = None,
    ) -> Any:
        """@brief Create a real AcDbAlignedDimension entity."""
        entity = _retry_com_busy(
            lambda: self.model.AddDimAligned(
                acad_point(point1),
                acad_point(point2),
                acad_point(text_position),
            ),
            "Create aligned dimension",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_dim_rotated(
        self,
        point1: PointLike,
        point2: PointLike,
        dim_line_position: PointLike,
        rotation_degrees: float,
        layer: Optional[str] = "DIM",
        color: Optional[int] = None,
    ) -> Any:
        """@brief Create a real rotated dimension, accepting the angle in engineering degrees."""
        entity = _retry_com_busy(
            lambda: self.model.AddDimRotated(
                acad_point(point1),
                acad_point(point2),
                acad_point(dim_line_position),
                math.radians(float(rotation_degrees)),
            ),
            "Create rotated dimension",
        )
        return self._apply_entity_options(entity, layer, color)

    def add_dim_diametric(
        self,
        center: PointLike,
        radius: float,
        *,
        angle_degrees: float = 0.0,
        leader_length: float = 8.0,
        layer: Optional[str] = "DIM",
        color: Optional[int] = None,
    ) -> Any:
        """@brief Create a real AcDbDiametricDimension entity."""
        xyz = list(center)
        if len(xyz) == 2:
            xyz.append(0.0)
        if len(xyz) != 3:
            raise ValueError(f"Circle center must be a 2D or 3D point: {center!r}")
        angle = math.radians(float(angle_degrees))
        dx = math.cos(angle) * float(radius)
        dy = math.sin(angle) * float(radius)
        chord = (float(xyz[0]) + dx, float(xyz[1]) + dy, float(xyz[2]))
        far_chord = (float(xyz[0]) - dx, float(xyz[1]) - dy, float(xyz[2]))
        entity = _retry_com_busy(
            lambda: self.model.AddDimDiametric(
                acad_point(chord),
                acad_point(far_chord),
                float(leader_length),
            ),
            "Create diameter dimension",
        )
        return self._apply_entity_options(entity, layer, color)

    def send_command(self, command: str) -> None:
        """@brief Send a command to AutoCAD's command line.

        Commands may execute asynchronously; save and review results afterward.
        """
        if not command.endswith("\n"):
            command += "\n"
        _retry_com_busy(lambda: self.active_document().SendCommand(command), "Send AutoCAD command")


    def regen(self) -> None:
        """@brief Regenerate the current document."""
        _retry_com_busy(lambda: self.active_document().Regen(1), "Regenerate drawing")

    def zoom_extents(self) -> None:
        """@brief Zoom to drawing extents."""
        if self.app is None:
            self.connect()
        _retry_com_busy(lambda: self.app.ZoomExtents(), "Zoom to extents")

    def live_update(self, step_delay_s: float = 0.0, zoom: bool = False) -> None:
        """@brief Refresh and pause briefly so the user can observe drawing progress.

        @param step_delay_s Pause in seconds after each step.
        @param zoom Whether to execute ZoomExtents while refreshing.
        """
        self.ensure_visible()
        self.activate_window()
        self.regen()
        if zoom:
            self.zoom_extents()
        if step_delay_s > 0:
            time.sleep(step_delay_s)

    def iter_model_entities(self) -> Iterator[Any]:
        """@brief Iterate ModelSpace entities, including dynamic proxies that cannot be enumerated directly."""
        model_space = self.model
        try:
            count = int(_retry_com_busy(lambda: model_space.Count, "Read entity count"))
        except Exception:
            yield from model_space
            return
        for index in range(count):
            yield _retry_com_busy(lambda index=index: model_space.Item(index), f"Read entity {index}")

    def save_as(self, path: str | Path) -> Path:
        """@brief Save the current drawing.

        @return Absolute path of the saved file.
        """
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        _retry_com_busy(lambda: self.active_document().SaveAs(str(target)), "Save AutoCAD drawing")
        return target

    def delete_selection_set(self, name: str) -> None:
        """@brief Delete the named SelectionSet, ignoring absence."""
        doc = self.refresh_document_proxy()
        try:
            doc.SelectionSets.Item(name).Delete()
        except Exception:
            pass

    def create_empty_selection_set(self, name: str) -> Any:
        """@brief Create an empty SelectionSet.

        DXF/EPS export ignores selection contents, but the ActiveX Export method still requires
        a SelectionSet argument.
        """
        last_error: Optional[Exception] = None
        for attempt in range(8):
            try:
                doc = self.refresh_document_proxy()
                self.delete_selection_set(name)
                return doc.SelectionSets.Add(name)
            except Exception as exc:
                last_error = exc
                time.sleep(0.08 + attempt * 0.04)
        raise RuntimeError("AutoCAD SelectionSet creation failed.") from last_error

    def export_dxf(self, path: str | Path, selection_set_name: str = "CODEX_EMPTY_EXPORT_SET") -> Path:
        """@brief Export the whole drawing as DXF using Document.Export.

        @param path Target DXF path.
        @param selection_set_name Temporary SelectionSet name.
        @return Absolute path of the exported DXF.
        """
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()

        self.refresh_document_proxy()
        sset = self.create_empty_selection_set(selection_set_name)
        export_base = str(target.with_suffix(""))
        try:
            self.refresh_document_proxy().Export(export_base, "DXF", sset)
        finally:
            try:
                sset.Delete()
            except Exception:
                pass
        return target

    def export_bmp_preview(self, path: str | Path, selection_set_name: str = "CODEX_PREVIEW_SET") -> Path:
        """@brief Export a BMP preview of the entire drawing using native AutoCAD Export.

        @param path Target BMP path.
        @param selection_set_name Temporary SelectionSet name.
        @return Absolute path of the exported BMP.
        """
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()

        self.regen()
        self.zoom_extents()
        self.refresh_document_proxy()
        sset = self.create_empty_selection_set(selection_set_name)
        try:
            # 5 is AutoCAD ActiveX acSelectionSetAll, passing all drawing objects to Export.
            sset.Select(5)
            self.refresh_document_proxy().Export(str(target.with_suffix("")), "BMP", sset)
        finally:
            try:
                sset.Delete()
            except Exception:
                pass
        return target

    def close_document(self, save_changes: bool = False) -> None:
        """@brief Close the current document."""
        if self.doc is not None:
            last_error: Optional[Exception] = None
            for attempt in range(6):
                try:
                    self.refresh_document_proxy().Close(bool(save_changes))
                    self.doc = None
                    return
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.08 + attempt * 0.05)
            # Cleanup must not replace the original drawing-generation error; the caller may still exit.
            self.doc = None
            if last_error is not None:
                return

    def quit_owned_instance(self) -> bool:
        """@brief Exit only the AutoCAD instance started by this session."""
        if self.app is None or not self.started_by_session:
            self.last_cleanup = {
                "owned_instance": False,
                "owned_process_id": self.owned_process_id,
                "quit_requested": False,
                "forced_termination_used": False,
                "process_exit_confirmed": None,
                "error": None,
            }
            return False
        app = self.app
        process_id = self.owned_process_id
        cleanup: dict[str, Any] = {
            "owned_instance": True,
            "owned_process_id": process_id,
            "quit_requested": False,
            "forced_termination_used": False,
            "process_exit_confirmed": False,
            "error": None,
        }
        self.doc = None
        self.app = None
        self.started_by_session = False
        self.owned_process_id = None
        try:
            _retry_com_busy(lambda: app.Quit(), "Exit task-owned AutoCAD")
            cleanup["quit_requested"] = True
        except Exception as exc:
            cleanup["error"] = f"AutoCAD Quit call failed: {exc}"

        if process_id is None:
            # Never force-terminate without exact PID ownership evidence; report only the COM Quit result.
            confirmed = bool(cleanup["quit_requested"])
            cleanup["process_exit_confirmed"] = None
            self.last_cleanup = cleanup
            return confirmed

        if _wait_for_process_exit(process_id, timeout_s=5.0):
            cleanup["process_exit_confirmed"] = True
            self.last_cleanup = cleanup
            return True

        self.forced_termination_used = _terminate_owned_process(process_id)
        cleanup["forced_termination_used"] = self.forced_termination_used
        if self.forced_termination_used and _wait_for_process_exit(process_id, timeout_s=10.0):
            cleanup["process_exit_confirmed"] = True
            self.last_cleanup = cleanup
            return True

        if cleanup["error"] is None:
            cleanup["error"] = "The task-owned AutoCAD PID remains active after the exit timeout"
        self.last_cleanup = cleanup
        return False


def point_tuple(value: Any) -> Tuple[float, float, float]:
    """@brief Convert a COM point to a Python three-tuple."""
    items = list(value)
    if len(items) == 2:
        items.append(0.0)
    return (float(items[0]), float(items[1]), float(items[2]))


SCRIPT_COMMANDS = {
    "zoom_extents": "_.ZOOM\n_E\n",
    "regen": "_.REGEN\n",
    "qsave": "_.QSAVE\n",
}


def run_whitelisted_script_command(session: AutoCADSession, command_id: str) -> dict[str, Any]:
    """@brief Execute fixed allowlisted AutoCAD commands; arbitrary script text is prohibited."""
    if command_id not in SCRIPT_COMMANDS:
        return {
            "backend": "autocad_script",
            "status": "blocked",
            "stage": "preflight",
            "artifacts": [],
            "limitations": ["Only predefined commands are allowed; arbitrary AutoLISP/SCR is prohibited"],
            "retryable": False,
            "error_code": "SCRIPT_COMMAND_NOT_ALLOWED",
        }
    try:
        session.send_command(SCRIPT_COMMANDS[command_id])
    except Exception as exc:
        return {
            "backend": "autocad_script",
            "status": "failed",
            "stage": "create",
            "artifacts": [],
            "limitations": ["Commands may be asynchronous; save and review afterward"],
            "retryable": True,
            "error_code": "AUTOCAD_SCRIPT_COMMAND_FAILED",
            "error": str(exc),
        }
    return {
        "backend": "autocad_script",
        "status": "pilot",
        "stage": "create",
        "artifacts": [],
        "limitations": ["Commands may be asynchronous; save and review afterward"],
        "retryable": True,
        "error_code": None,
    }
