"""@brief comtypes Pack and Go subprocess worker.

Launched by sw_delivery._comtypes_pack_and_go in a separate process. Receives a JSON payload on stdin and emits one JSON result line on stdout. Python COM library state is isolated; quitting a shared CAD service and cleaning documents still require independent PID and ownership checks.
"""
from __future__ import annotations

import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    """@brief Bound JSON input, manage COM lifetime explicitly, and emit exactly one stdout result."""
    initialized = False
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Pack and Go isteği 1 MiB sınırını aşıyor")
        payload = json.loads(raw.decode("utf-8"))
        target = payload["target"]
        existing = payload.get("existing_files") or {}
        if not isinstance(payload.get("expected_pid"), int) or payload["expected_pid"] <= 0:
            raise ValueError("Fallback ana örneğin PID değerini açıkça belirtmeli")
        import pythoncom
        pythoncom.CoInitialize()
        initialized = True
        from sw_delivery import _comtypes_pack_and_go_impl

        with redirect_stdout(sys.stderr):
            result = _comtypes_pack_and_go_impl(
                payload["source_path"], Path(target),
                {key: tuple(value) if value is not None else None for key, value in existing.items()},
                include_drawings=bool(payload["include_drawings"]),
                include_simulation_results=bool(payload["include_simulation_results"]),
                include_toolbox_components=bool(payload["include_toolbox_components"]),
                include_suppressed=bool(payload["include_suppressed"]),
                flatten=bool(payload["flatten"]), dependencies=payload.get("dependencies"),
                expected_pid=payload["expected_pid"],
            )
        print(json.dumps({"result": result}, ensure_ascii=True))
        return 0
    except BaseException as exc:  # noqa: BLE001 - return full details to the parent process
        print(
            json.dumps(
                {
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "code": getattr(exc, "code", None),
                    "traceback": traceback.format_exc(limit=6),
                },
                ensure_ascii=True,
            )
        )
        return 1
    finally:
        if initialized:
            pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
