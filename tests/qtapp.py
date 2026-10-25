"""One QApplication per test process (QML needs the GUI flavour)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")  # same as gui/main.py

from PyQt6.QtWidgets import QApplication  # noqa: E402

_app = None


def app() -> QApplication:
    global _app
    inst = QApplication.instance()
    if inst is None:
        _app = QApplication([])
        inst = _app
    return inst
