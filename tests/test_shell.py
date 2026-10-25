"""Task 4: animated shell — sidebar, view transitions, Downloads badge, toasts."""
import unittest

from tests.qmlsmoke import Smoke


class Shell(Smoke):
    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_switch_views_keeps_state(self):
        self.eval_qml("browseView.objectName = 'kept-marker'")
        self.eval_qml("sideBar.activeTab = 2; viewStack.currentIndex = 2")
        self.pump(700)
        self.assertFalse(self.eval_qml("browseView.visible"))
        self.assertTrue(self.eval_qml("libraryView.visible"))
        self.eval_qml("sideBar.activeTab = 0; viewStack.currentIndex = 0")
        self.pump(700)
        self.assertEqual(self.eval_qml("browseView.objectName"), "kept-marker")
        self.assertTrue(self.eval_qml("browseView.visible"))
        self.assertAlmostEqual(self.eval_qml("browsePane.opacity"), 1.0)

    def test_indicator_follows_active_tab(self):
        self.eval_qml("sideBar.activeTab = 3")
        self.pump(800)
        ind = self.find("navIndicator")
        self.assertAlmostEqual(ind.property("y"), self.eval_qml("sideBar.activeButtonY"), delta=1)
        self.eval_qml("sideBar.activeTab = 0")
        self.pump(800)

    def test_downloads_badge_from_signals(self):
        d = self.bridges["download"]
        d.jobStarted.emit("j1", "T", "", 3)
        d.chapterComplete.emit("j1", "c1", True, "")
        self.pump(50)
        self.assertEqual(self.find("sideBar").property("downloadsCount"), 2)
        d.jobCancelled.emit("j1")
        self.pump(50)
        self.assertEqual(self.find("sideBar").property("downloadsCount"), 0)

    def test_finished_download_toasts(self):
        d = self.bridges["download"]
        before = self.find("toastHost").property("count")
        d.jobStarted.emit("j2", "Moby Dick", "", 1)
        d.downloadFinished.emit("j2", 1, 0)
        self.pump(100)
        self.assertEqual(self.find("toastHost").property("count"), before + 1)
        self.assertEqual(self.find("sideBar").property("downloadsCount"), 0)

    def test_job_error_clears_badge_and_toasts(self):
        d = self.bridges["download"]
        before = self.find("toastHost").property("count")
        d.jobStarted.emit("j3", "Set It!", "", 4)
        d.jobError.emit("j3", "boom")
        self.pump(100)
        self.assertEqual(self.find("sideBar").property("downloadsCount"), 0)
        self.assertEqual(self.find("toastHost").property("count"), min(4, before + 1))

    def test_cancelled_job_is_not_celebrated(self):
        # Review finding: cancel → in-flight chapters finish → `finished`
        # fired and was toasted as a success with confetti.
        d = self.bridges["download"]
        d.jobStarted.emit("jcan", "Moby Dick", "", 5)
        d.chapterComplete.emit("jcan", "c1", True, "")
        d.jobCancelled.emit("jcan")
        d.chapterComplete.emit("jcan", "c2", True, "")
        d.downloadFinished.emit("jcan", 2, 0)
        self.pump(100)
        self.assertEqual(self.find("toastHost").property("lastText"), "Cancelled Moby Dick after 2 chapters")
        self.assertEqual(self.find("toastHost").property("lastKind"), "info")
        card = "downloadsView.getProgressPanel().cardsByJobId['jcan']"
        self.assertFalse(self.eval_qml(card + ".flashing"))
        self.assertEqual(self.find("sideBar").property("downloadsCount"), 0)

    def test_fly_bubble_lands(self):
        self.eval_qml("Fx.flyRequested(Qt.point(900, 700), 5)")
        self.pump(100)
        self.assertEqual(self.eval_qml("flyLayer.children.length"), 1)
        self.pump(1200)
        self.assertEqual(self.eval_qml("flyLayer.children.length"), 0)


if __name__ == "__main__":
    unittest.main()
