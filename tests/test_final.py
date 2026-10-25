"""Task 10: animations off + software rendering pass."""
import unittest

from tests.qmlsmoke import Smoke, run_smoke_subprocess


class AnimationsOff(Smoke):
    config = {"animations_enabled": False}

    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_everything_instant_when_animations_off(self):
        self.assertEqual(self.eval_qml("Theme.dur(500)"), 0)
        self.eval_qml("settingsDrawer.isOpen = true")
        self.pump(50)
        panel = self.find("settingsPanel")
        self.assertAlmostEqual(panel.property("x"), self.eval_qml("root.width") - panel.property("width"), delta=1)
        self.eval_qml("settingsDrawer.isOpen = false")
        self.pump(50)
        self.eval_qml("sideBar.activeTab = 2; viewStack.currentIndex = 2")
        self.pump(50)
        self.assertAlmostEqual(self.eval_qml("libraryView.parent.parent.opacity"), 1.0, places=2)
        self.eval_qml("sideBar.activeTab = 0; viewStack.currentIndex = 0")
        self.pump(50)
        self.assertAlmostEqual(self.eval_qml("browsePane.opacity"), 1.0, places=2)

    def test_theme_switch_instant(self):
        self.eval_qml('Fx.themeWipeRequested("neon", Qt.point(5, 5))')
        self.pump(30)
        self.assertEqual(self.bridges["settings"].property("theme"), "neon")
        self.assertFalse(self.find("themeWipe").property("active"))
        self.eval_qml('Fx.themeWipeRequested("ink", Qt.point(5, 5))')


class CpuWalkthrough(unittest.TestCase):
    def test_cpu_full_walkthrough(self):
        steps = ";;".join([
            "sideBar.activeTab = 1; viewStack.currentIndex = 1", "pump 600",
            "sideBar.activeTab = 2; sideBar.libraryClicked()", "pump 800",
            "sideBar.activeTab = 3; sideBar.updatesClicked()", "pump 600",
            "settingsDrawer.isOpen = true", "pump 800",
            "Fx.themeWipeRequested('ember', Qt.point(900, 200))", "pump 900",
            "settingsDrawer.isOpen = false", "pump 700",
            "DownloadBridge.jobStarted('jc', 'Moby Dick', '', 1)",
            "DownloadBridge.chapterComplete('jc', 'Chapter 1', true, '')",
            "DownloadBridge.downloadFinished('jc', 1, 0)", "pump 1200",
            "(function(){ if (SettingsBridge.theme !== 'ember') throw new Error('theme') })()",
        ])
        r = run_smoke_subprocess(software=True, script=steps)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
