"""Task 2: live theme system."""
import unittest

from tests.qmlsmoke import Smoke, run_smoke_subprocess, scan_hardcoded_colour_props


class ThemeTests(Smoke):
    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_default_is_ink(self):
        self.assertEqual(self.bridges["settings"].property("theme"), "ink")
        self.assertEqual(self.eval_qml("Theme.accent").name().lower(), "#ff7a93")

    def test_live_switch(self):
        s = self.bridges["settings"]
        s.setProperty("theme", "neon")
        self.pump(50)
        self.assertEqual(self.eval_qml("Theme.accent").name().lower(), "#ff3da8")
        s.setProperty("theme", "ink")
        self.pump(50)

    def test_invalid_theme_ignored(self):
        s = self.bridges["settings"]
        s.setProperty("theme", "bogus")
        self.assertIn(s.property("theme"), ("ink", "neon", "ember"))

    def test_settings_defaults(self):
        s = self.bridges["settings"]
        self.assertTrue(s.property("animationsEnabled"))
        self.assertTrue(s.property("ambientGlow"))

    def test_no_hardcoded_palette_left(self):
        self.assertEqual(scan_hardcoded_colour_props("gui/qml"), [])


class SoftwareBackend(unittest.TestCase):
    def test_loads_clean_software_backend(self):
        r = run_smoke_subprocess(software=True, script="SettingsBridge.theme = 'neon';;pump 100")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
