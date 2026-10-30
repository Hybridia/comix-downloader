"""scripts/make_mac_app.py builds a double-clickable Comix Downloader.app."""
import os
import plistlib
import tempfile
import unittest
from pathlib import Path

from scripts.make_mac_app import ROOT, build_app


class MacAppTest(unittest.TestCase):
    def test_bundle_launches_the_gui_from_this_checkout(self):
        app = build_app(Path(tempfile.mkdtemp()))
        self.assertEqual(app.name, "Comix Downloader.app")
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleName"], "Comix Downloader")
        self.assertEqual(info["CFBundleExecutable"], "launcher")
        self.assertEqual(info["CFBundleIconFile"], "AppIcon")
        self.assertEqual(info["CFBundleIdentifier"], "com.hybridia.comixdownloader")
        exe = app / "Contents" / "MacOS" / "launcher"
        self.assertTrue(os.access(exe, os.X_OK))
        text = exe.read_text()
        self.assertIn(str(ROOT / ".venv" / "bin" / "python"), text)
        self.assertIn("gui/main.py", text)
        self.assertIn("exec ", text)  # the app *is* the GUI process (one Dock icon)
        self.assertTrue((app / "Contents" / "Resources" / "AppIcon.icns").is_file())

    def test_rebuild_replaces_the_old_bundle(self):
        dest = Path(tempfile.mkdtemp())
        build_app(dest)
        (dest / "Comix Downloader.app" / "stale").write_text("x")
        build_app(dest)
        self.assertFalse((dest / "Comix Downloader.app" / "stale").exists())


if __name__ == "__main__":
    unittest.main()
