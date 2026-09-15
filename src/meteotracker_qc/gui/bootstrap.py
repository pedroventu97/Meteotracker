"""Qt bootstrap. Importing the scientific package never requires Qt."""
from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meteotracker-gui", description="Meteotracker QC — applicazione desktop")
    parser.add_argument("--workspace", help="Workspace esistente")
    parser.add_argument("--read-only", action="store_true", help="Disabilita apply e rapporti persistenti del check")
    parser.add_argument("--smoke-test", action="store_true", help="Verifica Qt e finestra senza pipeline")
    args = parser.parse_args(argv)
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from .window import MainWindow
    except ImportError as exc:
        print(f"GUI non disponibile: installare meteotracker-qc[gui]. {exc}", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(["meteotracker-gui"])
    app.setApplicationName("Meteotracker QC")
    app.setOrganizationName("Meteotracker")
    window = MainWindow(workspace=args.workspace, read_only=args.read_only,
                        startup=not args.smoke_test, persist=not args.smoke_test)
    window.show()
    if args.smoke_test:
        app.processEvents()
        assert window.tabs.count() == 4
        assert window.worker is None
        window.close()
        app.processEvents()
        print("Meteotracker GUI smoke test: PASS (Qt, bootstrap, finestra; nessuna pipeline)")
        return 0
    return app.exec()
