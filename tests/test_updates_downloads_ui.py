"""Task 9: animated updates review and download job cards."""
import unittest

from tests.qmlsmoke import Smoke

URL = "https://toonily.com/serie/moby-dick"
PENDING = {
    "checked_at": "2026-10-25T10:00:00",
    "items": {
        URL: {
            "library_url": URL, "title": "Moby Dick", "recommended": 0,
            "sources": [{
                "provider": "toonily", "url": URL, "latest": "117",
                "newer": [{"number": n, "norm": n, "title": ""} for n in ("115", "116", "117")],
                "gaps": [],
            }],
        }
    },
}


class UpdatesAndDownloads(Smoke):
    pending = PENDING

    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_updates_counter_tracks_selection(self):
        self.eval_qml("sideBar.activeTab = 3; sideBar.updatesClicked()")
        self.pump(1500)
        self.assertEqual(self.eval_qml("updatesView.applyCount"), 3)
        self.eval_qml(f"updatesView.toggleChapter('{URL}', '116')")
        self.pump(1500)
        self.assertEqual(self.eval_qml("updatesView.applyCount"), 2)
        self.assertEqual(self.find("applyCountText").property("text"), "2")
        self.eval_qml(f"updatesView.toggleChapter('{URL}', '116')")

    def test_job_card_finishes(self):
        d = self.bridges["download"]
        d.jobStarted.emit("jx", "Moby Dick", "", 2)
        d.chapterStarted.emit("jx", "Chapter 1")
        d.chapterProgress.emit("jx", "Chapter 1", 5, 10)
        self.pump(100)
        card = "downloadsView.getProgressPanel().cardsByJobId['jx']"
        self.assertFalse(self.eval_qml(card + ".isFinished"))
        d.downloadFinished.emit("jx", 2, 0)
        self.pump(200)
        self.assertTrue(self.eval_qml(card + ".isFinished"))
        self.assertTrue(self.eval_qml(card + ".flashing"))
        self.pump(1200)
        self.assert_no_qml_warnings()


if __name__ == "__main__":
    unittest.main()
