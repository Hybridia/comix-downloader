"""The app (window + macOS Dock) icon is the chibi icon."""
import unittest

from tests.qtapp import app


class AppIcon(unittest.TestCase):
    def test_icon_files_exist(self):
        from gui.app import ICON_PNG, ICON_ICNS
        self.assertTrue(ICON_PNG.exists())
        self.assertTrue(ICON_ICNS.exists())

    def test_apply_app_icon_sets_window_icon(self):
        from gui.app import apply_app_icon
        a = app()
        apply_app_icon(a)
        self.assertFalse(a.windowIcon().isNull())
        self.assertGreaterEqual(max(s.width() for s in a.windowIcon().availableSizes()), 512)


if __name__ == "__main__":
    unittest.main()
