"""Task 5: animated settings drawer, theme picker with colour wipe, hold-to-reset."""
import unittest

from tests.qmlsmoke import Smoke, run_smoke_subprocess


class SettingsDrawer(Smoke):
    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_drawer_opens_and_closes(self):
        self.eval_qml("settingsDrawer.isOpen = true")
        self.pump(900)
        panel = self.find("settingsPanel")
        win_w = self.eval_qml("root.width")
        self.assertAlmostEqual(panel.property("x"), win_w - panel.property("width"), delta=1)
        self.assertTrue(self.eval_qml("settingsDrawer.visible"))
        self.eval_qml("settingsDrawer.isOpen = false")
        self.pump(900)
        self.assertFalse(self.eval_qml("settingsDrawer.visible"))

    def test_theme_card_switches_theme(self):
        self.eval_qml('settingsDrawer.chooseTheme("neon", Qt.point(10, 10))')
        self.pump(1200)
        self.assertEqual(self.bridges["settings"].property("theme"), "neon")
        self.assertFalse(self.find("themeWipe").property("active"))
        self.eval_qml('settingsDrawer.chooseTheme("ink", Qt.point(10, 10))')
        self.pump(1200)

    def test_rapid_theme_switch_leaves_one_overlay(self):
        for n in ("neon", "ember", "ink"):
            self.eval_qml(f'Fx.themeWipeRequested("{n}", Qt.point(10, 10))')
        self.pump(1400)
        self.assertEqual(self.bridges["settings"].property("theme"), "ink")
        self.assertFalse(self.find("themeWipe").property("active"))
        self.assertFalse(self.find("themeWipeSnapshot").property("visible"))

    def test_hold_reset_requires_full_hold(self):
        s = self.bridges["settings"]
        s.setValue("max_chapter_workers", 7)
        hold = self.find("holdReset")
        hold.begin()
        self.pump(500)
        hold.end()
        self.pump(500)
        self.assertEqual(s.getValue("max_chapter_workers"), 7)
        hold.begin()
        self.pump(1700)
        self.assertEqual(s.getValue("max_chapter_workers"), 3)

    def test_login_status_ends_busy_and_toasts(self):
        before = self.find("toastHost").property("count")
        self.eval_qml("settingsDrawer.loginBusy = true")
        self.bridges["settings"].toomicsStatus.emit("ok", "Logged in")
        self.pump(100)
        self.assertFalse(self.eval_qml("settingsDrawer.loginBusy"))
        self.assertEqual(self.find("toastHost").property("count"), min(4, before + 1))

    def test_appearance_toggles_write_settings(self):
        s = self.bridges["settings"]
        self.eval_qml("settingsDrawer.setAmbient(false)")
        self.assertFalse(s.property("ambientGlow"))
        self.eval_qml("settingsDrawer.setAmbient(true)")
        self.assertTrue(s.property("ambientGlow"))


class SoftwareThemeSwitch(unittest.TestCase):
    def test_theme_switch_software_backend(self):
        r = run_smoke_subprocess(
            software=True,
            script="Fx.themeWipeRequested('neon', Qt.point(5, 5));;pump 900;;"
                   "(function(){ if (SettingsBridge.theme !== 'neon') throw new Error('theme not switched') })()",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
