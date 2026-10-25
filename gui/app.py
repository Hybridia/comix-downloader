"""
Engine construction shared by gui/main.py and the headless tests.

Call after the QApplication exists (and after any rendering-backend
environment variables are set).
"""

import sys
from pathlib import Path
from typing import Callable, Optional

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt6.QtCore import QUrl
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface

from gui.bridge import MangaBridge, DownloadBridge, SettingsBridge, LibraryBridge

QML_DIR = Path(__file__).parent / "qml"


def software_rendering() -> bool:
    """True when Qt Quick renders with the software backend (``--cpu``)."""
    return QQuickWindow.graphicsApi() == QSGRendererInterface.GraphicsApi.Software


def build_engine(
    on_warnings: Optional[Callable[[list], None]] = None,
    qml_file: Optional[Path] = None,
) -> tuple[QQmlApplicationEngine, dict]:
    """Create the bridges, expose them to QML and load main.qml.

    ``on_warnings`` receives every batch of QML warnings (tests use it to
    fail on any). ``qml_file`` replaces main.qml (tests load fixtures). Returns ``(engine, bridges)``; check
    ``engine.rootObjects()`` for load success.
    """
    engine = QQmlApplicationEngine()
    if on_warnings is not None:
        engine.warnings.connect(on_warnings)

    bridges = {
        "manga": MangaBridge(),
        "download": DownloadBridge(),
        "settings": SettingsBridge(),
        "library": LibraryBridge(),
    }
    # The Library "Update" flow needs to invoke DownloadBridge once it
    # has diffed local vs remote chapters; wire that connection up here
    # so QML doesn't need to know about it.
    bridges["library"].attach_download_bridge(bridges["download"])

    ctx = engine.rootContext()
    ctx.setContextProperty("MangaBridge", bridges["manga"])
    ctx.setContextProperty("DownloadBridge", bridges["download"])
    ctx.setContextProperty("SettingsBridge", bridges["settings"])
    ctx.setContextProperty("LibraryBridge", bridges["library"])
    # Theme.software reads this: blur / masks / shader effects are skipped.
    ctx.setContextProperty("SoftwareRendering", software_rendering())

    engine.addImportPath(str(QML_DIR))
    engine.load(QUrl.fromLocalFile(str(qml_file or QML_DIR / "main.qml")))
    return engine, bridges
