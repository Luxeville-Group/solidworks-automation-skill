"""@brief Compatibility package for Python helpers; load native COM on demand so pure-logic imports do not require Windows."""
from importlib import import_module

_EXPORTS = {
    "connect_solidworks": "sw_connect", "deg": "sw_connect", "mm": "sw_connect",
    "new_document": "sw_connect", "open_document": "sw_connect", "save_document": "sw_connect",
    "build_prompt": "sw_macro_guard", "generate_macro_with_guard": "sw_macro_guard",
    "validate_vba_macro": "sw_macro_guard", "run_preflight": "sw_preflight",
    "SolidWorksSession": "sw_session", "session": "sw_session",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """@brief Preserve legacy import names and load dependencies only when their capability is invoked."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module("." + module, __name__), name)
    globals()[name] = value
    return value
