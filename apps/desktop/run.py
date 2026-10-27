"""@brief CAD Automation delivery workbench desktop entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """@brief Start the PySide6 desktop application."""
    app_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(app_dir))

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Eksik PySide6, Önce çalıştırın: : python -m pip install -r apps/desktop/requirements.txt")
        return 1

    from cad_workbench.app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("CAD Otomasyon teslim çalışma alanı")
    app.setOrganizationName("solidworks-automation-skill")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
