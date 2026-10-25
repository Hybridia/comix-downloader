"""Performance guards: nothing animates while idle; Library opens fast."""
import time
import unittest

from PyQt6.QtCore import QObject

from tests.qmlsmoke import Smoke
from tests.test_library_ui import entries


def _in_ambient_glow(o):
    p = o.parent()
    while p is not None:
        if p.metaObject().className().startswith("AmbientGlow"):
            return True
        p = p.parent()
    return False


def running_animations(root, allow_glow=True):
    """Running animations / particle systems, as 'Class <- Parent' strings.
    The background glow drifts forever by design, so it's allowed unless
    allow_glow=False."""
    out = []
    for o in root.findChildren(QObject):
        cn = o.metaObject().className()
        busy = "ParticleSystem" in cn or (
            ("Animation" in cn or cn == "QQmlTimer") and o.property("running"))
        if busy and not (allow_glow and _in_ambient_glow(o)):
            parent = o.parent().metaObject().className().split("_QML")[0] if o.parent() else "?"
            out.append(f"{cn} <- {parent}")
    return out


class Perf(Smoke):
    library = entries(263)

    def test_a_library_opens_fast(self):
        t0 = time.perf_counter()
        self.eval_qml("sideBar.activeTab = 2; sideBar.libraryClicked()")
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed, 300, f"opening the Library blocked the UI for {elapsed:.0f} ms")

    def test_b_idle_library_has_no_running_animations(self):
        self.eval_qml("sideBar.activeTab = 2; sideBar.libraryClicked()")
        self.pump(2500)  # entrance animations finish
        self.assertEqual(running_animations(self.root()), [])

    def test_c_idle_browse_has_no_running_animations(self):
        self.eval_qml("sideBar.activeTab = 0; viewStack.currentIndex = 0")
        self.pump(1500)
        self.assertEqual(running_animations(self.root()), [])


class PerfGlowOff(Smoke):
    config = {"ambient_glow": False}
    library = entries(40)

    def test_nothing_animates_when_idle_with_glow_off(self):
        self.eval_qml("sideBar.activeTab = 2; sideBar.libraryClicked()")
        self.pump(2500)
        self.assertEqual(running_animations(self.root(), allow_glow=False), [])


if __name__ == "__main__":
    unittest.main()
