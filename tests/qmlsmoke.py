"""Headless fixture that loads the real GUI (gui/qml/main.qml).

Every test class gets a fresh engine built by gui.app.build_engine against
a throw-away config.json, so tests never touch the user's settings.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.qtapp import app

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QObject, QEventLoop, QTimer  # noqa: E402
from PyQt6.QtQml import QQmlExpression  # noqa: E402


def use_temp_data(config: dict | None = None, library: list | None = None,
                  pending: dict | None = None) -> Path:
    """Point config.json, library.json and pending_updates.json at fresh
    temp files so tests never read or write the user's real data.
    Returns the temp directory."""
    import src.utils.config as cfg
    import src.utils.library as lib
    import gui.bridge.library_bridge as lb
    d = Path(tempfile.mkdtemp(prefix="comix-test-"))
    (d / "config.json").write_text(json.dumps(config or {}), encoding="utf-8")
    (d / "library.json").write_text(
        json.dumps({"version": lib._SCHEMA_VERSION, "entries": library or []}), encoding="utf-8")
    if pending and "items" not in pending:
        pending = {"checked_at": "", "items": pending}
    (d / "pending_updates.json").write_text(json.dumps(pending or {}), encoding="utf-8")
    cfg._DEFAULT_CONFIG_PATH = d / "config.json"
    lib._DEFAULT_PATH = d / "library.json"
    lib.reset_for_tests()
    lb._PENDING_PATH = d / "pending_updates.json"
    return d


def pump(ms: int) -> None:
    """Run the event loop for ``ms`` milliseconds (animations advance)."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class Smoke(unittest.TestCase):
    """Base class: loads main.qml once per class and records QML warnings."""

    config: dict | None = None
    library: list | None = None
    pending: dict | None = None
    qml_file: Path | None = None   # None = gui/qml/main.qml

    @classmethod
    def setUpClass(cls):
        app()
        cls.data_dir = use_temp_data(cls.config, cls.library, cls.pending)
        from gui.app import build_engine
        cls.warnings = []
        cls.engine, cls.bridges = build_engine(on_warnings=cls.warnings.extend, qml_file=cls.qml_file)
        if not cls.engine.rootObjects():
            raise RuntimeError("main.qml failed to load: " + "\n".join(w.toString() for w in cls.warnings))
        pump(300)

    @classmethod
    def tearDownClass(cls):
        for r in cls.engine.rootObjects():
            r.deleteLater()
        cls.engine.deleteLater()
        pump(50)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    # -- helpers -------------------------------------------------------
    def root(self) -> QObject:
        return self.engine.rootObjects()[0]

    def find(self, name: str) -> QObject:
        obj = self.root().findChild(QObject, name)
        if obj is None:
            raise AssertionError(f"no QML object with objectName {name!r}")
        return obj

    def pump(self, ms: int) -> None:
        pump(ms)

    def call(self, obj: QObject, method: str, *args):
        """Invoke a QML function on ``obj`` (args passed as QVariant)."""
        from PyQt6.QtCore import QMetaObject, Q_ARG, Q_RETURN_ARG, Qt
        qargs = [Q_ARG("QVariant", a) for a in args]
        ok = QMetaObject.invokeMethod(obj, method, Qt.ConnectionType.DirectConnection,
                                      Q_RETURN_ARG("QVariant"), *qargs)
        return ok

    def eval_qml(self, expr: str):
        # The root object's own context carries main.qml's imports (Style).
        ctx = self.engine.contextForObject(self.root())
        e = QQmlExpression(ctx, self.root(), expr)
        value = e.evaluate()
        if isinstance(value, tuple):
            value = value[0]
        if e.hasError():
            raise AssertionError(f"{expr}: {e.error().toString()}")
        return value

    def assert_no_qml_warnings(self):
        msgs = [w.toString() for w in self.warnings]
        self.assertEqual(msgs, [], "QML warnings:\n" + "\n".join(msgs))


def run_smoke_subprocess(software: bool, script: str = "") -> subprocess.CompletedProcess:
    """Run tests/smoke_main.py in a fresh process (one backend per process)."""
    cmd = [sys.executable, str(ROOT / "tests" / "smoke_main.py")]
    if software:
        cmd.append("--software")
    if script:
        cmd += ["--script", script]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=90)


_COLOUR_PROP = re.compile(r'readonly\s+property\s+color\s+\w+\s*:\s*"#[0-9A-Fa-f]{3,8}"')


def scan_hardcoded_colour_props(qml_dir: str) -> list[str]:
    """`readonly property color X: "#..."` outside gui/qml/Style/ → file:line."""
    out = []
    base = ROOT / qml_dir
    for f in sorted(base.rglob("*.qml")):
        if "Style" in f.relative_to(base).parts:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _COLOUR_PROP.search(line):
                out.append(f"{f.relative_to(ROOT)}:{i}")
    return out
