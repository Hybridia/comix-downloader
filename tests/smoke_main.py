"""Load the GUI headlessly in its own process and report QML warnings.

    python tests/smoke_main.py [--software] [--script "<qml expressions;...>"]

Exit 0 and prints "OK" when the GUI loaded with no QML warnings.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--software", action="store_true")
parser.add_argument("--script", default="")
args = parser.parse_args()
if args.software:
    os.environ["QT_QUICK_BACKEND"] = "software"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.qtapp import app  # noqa: E402
from tests.qmlsmoke import use_temp_data, pump  # noqa: E402

app()
use_temp_data()
from gui.app import build_engine  # noqa: E402
from PyQt6.QtQml import QQmlExpression  # noqa: E402

warnings = []
engine, bridges = build_engine(on_warnings=warnings.extend)
if not engine.rootObjects():
    print("LOAD FAILED")
    for w in warnings:
        print(w.toString())
    sys.exit(2)
pump(300)
root = engine.rootObjects()[0]
for stmt in filter(None, (s.strip() for s in args.script.split(";;"))):
    if stmt.startswith("pump "):
        pump(int(stmt.split()[1]))
        continue
    e = QQmlExpression(engine.contextForObject(root), root, stmt)
    e.evaluate()
    if e.hasError():
        print("SCRIPT ERROR:", stmt, e.error().toString())
        sys.exit(3)
pump(300)
if warnings:
    for w in warnings:
        print(w.toString())
    sys.exit(1)
print("OK")
