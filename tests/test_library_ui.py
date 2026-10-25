"""Task 8: animated library — staggered cards, tilt, flip, check/download morphs."""
import unittest

from tests.qmlsmoke import Smoke


def entries(n):
    return [{
        "source": "toonily", "source_url": f"https://toonily.com/serie/s{i}",
        "title": f"Series {i:03d}", "alt_titles": [], "poster_url": "",
        "output_format": "cbz", "download_path": "/nonexistent", "folder": f"S{i}",
        "added_at": "2026-01-01T00:00:00", "last_updated_at": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}",
        "last_checked_at": None, "chapters": {"1": {"title": "c1", "downloaded_at": "x"}},
        "status": "ongoing",
    } for i in range(n)]


class LibraryUI(Smoke):
    library = entries(260)

    def open_library(self):
        self.eval_qml("sideBar.activeTab = 2; sideBar.libraryClicked()")

    def test_library_loads_260_entries_clean(self):
        self.open_library()
        delay = 540 + 800
        self.pump(delay)
        self.assertEqual(self.eval_qml("libraryView.cardCount()"), 260)
        self.assertAlmostEqual(self.eval_qml("libraryView.cardAt(0).opacity"), 1.0, places=2)
        self.assertAlmostEqual(self.eval_qml("libraryView.cardAt(15).opacity"), 1.0, places=2)
        self.assertAlmostEqual(self.eval_qml("libraryView.cardAt(259).opacity"), 1.0, places=2)
        self.assert_no_qml_warnings()

    def test_cards_fit_inside_the_view(self):
        # Regression: the toolbar's minimum width used to force the whole
        # column wider than the window, cutting off the cards' buttons.
        self.open_library()
        self.pump(600)
        self.assertLessEqual(self.eval_qml("libraryView.cardAt(0).width"),
                             self.eval_qml("libraryView.width") - 40)

    def test_flip_and_unflip(self):
        self.open_library()
        self.pump(800)
        self.eval_qml("libraryView.cardAt(0).toggleFlip()")
        self.pump(50)
        self.assertTrue(self.eval_qml("libraryView.cardAt(0).flipped"))
        self.eval_qml("libraryView.cardAt(0).hoverLeft()")
        self.pump(50)
        self.assertFalse(self.eval_qml("libraryView.cardAt(0).flipped"))

    def test_job_finished_shows_done(self):
        self.open_library()
        self.pump(800)
        url = "https://toonily.com/serie/s7"
        self.bridges["download"].libraryJobFinished.emit(url, 3, 0)
        self.pump(100)
        self.assertEqual(self.eval_qml(f"libraryView.cardFor('{url}').statusMessage"), "Downloaded 3 new chapters")
        self.assertTrue(self.eval_qml(f"libraryView.cardFor('{url}').celebrating"))


if __name__ == "__main__":
    unittest.main()
