"""Task 3: motion primitives in gui/qml/fx/."""
import unittest

from tests.qmlsmoke import Smoke, ROOT


class FxGallery(Smoke):
    qml_file = ROOT / "tests" / "qml" / "FxGallery.qml"

    def test_gallery_instantiates_clean(self):
        self.assert_no_qml_warnings()

    def test_toast_stacks_and_expires(self):
        for i in range(6):
            self.eval_qml(f'Fx.toast("t{i}", "info")')
        self.pump(100)
        self.assertEqual(self.find("toastHost").property("count"), 4)
        self.pump(3800)
        self.assertEqual(self.find("toastHost").property("count"), 0)

    def test_countup_reaches_value(self):
        c = self.find("count")
        c.setProperty("value", 312)
        self.pump(1400)
        self.assertEqual(c.property("text"), "312")

    def test_countup_thousands(self):
        c = self.find("count")
        c.setProperty("value", 48210)
        self.pump(1400)
        self.assertEqual(c.property("text"), "48,210")

    def test_burst_runs(self):
        self.eval_qml("burst.burst()")
        self.pump(100)
        self.assert_no_qml_warnings()

    def test_zz_animations_off_kills_decor(self):  # zz: runs last, flips a setting
        self.bridges["settings"].setProperty("animationsEnabled", False)
        self.pump(50)
        self.assertEqual(self.eval_qml("Theme.dur(400)"), 0)
        self.assertFalse(self.find("ambient").property("visible"))
        self.assertFalse(self.find("burstLoader").property("active"))  # only alive during a burst
        self.assertFalse(self.find("pulseLoader").property("active"))


if __name__ == "__main__":
    unittest.main()
