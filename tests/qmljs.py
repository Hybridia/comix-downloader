"""Load a `.pragma library` QML JavaScript file into a QJSEngine for tests."""
from pathlib import Path

from PyQt6.QtQml import QJSEngine

from tests.qtapp import app

ROOT = Path(__file__).resolve().parent.parent


class JsLib:
    def __init__(self, path: Path):
        app()  # QJSEngine needs an application object
        self._engine = QJSEngine()
        src = path.read_text(encoding="utf-8")
        src = "\n".join(l for l in src.splitlines() if not l.strip().startswith(".pragma"))
        result = self._engine.evaluate(src, str(path))
        if result.isError():
            raise RuntimeError(f"{path}: {result.toString()}")

    def call(self, fn: str, *args):
        func = self._engine.globalObject().property(fn)
        if not func.isCallable():
            raise AttributeError(f"{fn} is not a function")
        result = func.call([self._engine.toScriptValue(a) for a in args])
        if result.isError():
            raise RuntimeError(result.toString())
        return result.toVariant()


def load(rel_path: str) -> JsLib:
    path = ROOT / rel_path
    if not path.exists():
        raise FileNotFoundError(path)
    return JsLib(path)
