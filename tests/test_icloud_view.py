"""Copy to iCloud view: chapters waiting in ./downloads → the series'
folder in the iCloud Manga folder (temp folders here, never the real one)."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.qmlsmoke import Smoke


def cbz(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", b"x")
    return path


def make_env():
    """Fresh iCloud + downloads folders and the Library entries for them."""
    root = Path(tempfile.mkdtemp(prefix="comix-icloud-"))
    icloud, downloads = root / "Manga", root / "downloads"
    cbz(icloud / "Study Buddies" / "Chapter_116.cbz")
    cbz(downloads / "Study Buddies" / "Chapter_117.cbz")
    cbz(downloads / "Study Buddies" / "Chapter_118.cbz")
    cbz(downloads / "Brand New_" / "Chapter_1.cbz")
    library = [
        {"source": "toonily", "source_url": "https://toonily.com/serie/study-buddies", "title": "Study Buddies",
         "download_path": str(icloud), "folder": "Study Buddies", "chapters": {}},
        {"source": "toonily", "source_url": "https://toonily.com/serie/study-buddies-2", "title": "Study Buddies",
         "download_path": str(icloud), "folder": "Study Buddies", "chapters": {}},  # duplicate entry
        {"source": "toonily", "source_url": "https://toonily.com/serie/brand-new", "title": "Brand New!",
         "download_path": str(downloads), "folder": "Brand New_", "chapters": {}},
    ]
    return icloud, downloads, library


ICLOUD, DOWNLOADS, LIBRARY = make_env()  # used by the GUI tests


class ScanTest(unittest.TestCase):
    def test_one_row_per_icloud_folder(self):
        from gui.bridge.icloud_bridge import scan_pending
        icloud, downloads, library = make_env()
        rows = scan_pending(library, downloads_root=downloads, icloud_root=icloud)
        self.assertEqual([(r["title"], r["target"], r["target_exists"], [c["number"] for c in r["chapters"]])
                          for r in rows],
                         [("Brand New!", "Brand New_", False, ["1"]),
                          ("Study Buddies", "Study Buddies", True, ["117", "118"])])


class IcloudView(Smoke):
    library = LIBRARY

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        b = cls.bridges["icloud"]
        b.icloud_root, b.downloads_root = ICLOUD, DOWNLOADS
        # iCloud upload: each file first reports an error (iCloud retries),
        # then "uploading", then "uploaded".
        cls.polls = {}
        def status(paths):
            out = {}
            for p in map(str, paths):
                cls.polls[p] = cls.polls.get(p, 0) + 1
                n = cls.polls[p]
                st = "error: Couldn't access your iCloud account." if n == 1 else \
                     "uploading" if n <= 3 else "uploaded"
                out[p] = {"state": st, "size": 1000,
                          "done": 1000 if st == "uploaded" else 400 if st == "uploading" else 0}
            return out
        b.status_fn, b.poll_seconds = status, 0.1

    def open_view(self):
        self.eval_qml("sideBar.activeTab = 4; sideBar.icloudClicked()")
        for _ in range(40):
            self.pump(100)
            if self.eval_qml("icloudView.rows.length") == 2:
                break

    def test_lists_series_and_copies_selected_chapters(self):
        self.open_view()
        self.assertEqual(self.eval_qml("icloudView.rows.length"), 2)
        self.assertEqual(self.eval_qml("icloudView.selectedCount"), 0)  # nothing ticked until you say so
        key = str(ICLOUD / "Study Buddies")
        self.eval_qml(f"icloudView.toggleRow('{key}')")
        self.assertEqual(self.eval_qml("icloudView.selectedCount"), 2)
        self.eval_qml(f"icloudView.toggleChapter('{key}', '118')")
        self.assertEqual(self.eval_qml("icloudView.selectedCount"), 1)
        seen = []
        self.bridges["icloud"].uploadProgress.connect(lambda s: seen.append(dict(s)))
        self.eval_qml("icloudView.copySelected()")
        for _ in range(80):
            self.pump(50)
            if not self.eval_qml("icloudView.copying") and "Copied" in self.eval_qml("icloudView.summary"):
                break
        self.assertEqual([(x["retrying"], x["uploading"], x["uploaded"]) for x in seen][0], (1, 0, 0))
        self.assertIn("Couldn't access", seen[0]["reason"])
        self.assertEqual((seen[-1]["uploaded"], seen[-1]["retrying"]), (1, 0))
        self.assertEqual((seen[1]["done_bytes"], seen[1]["total_bytes"]), (400, 1000))
        self.assertIn("Copied 1 chapter to iCloud", self.eval_qml("icloudView.summary"))
        self.assertIn("uploaded to iCloud ✓", self.eval_qml("icloudView.summary"))
        self.assertEqual(self.eval_qml("icloudView.uploadDone"), 1)
        self.assertTrue((ICLOUD / "Study Buddies" / "Chapter_117.cbz").is_file())
        self.assertFalse((ICLOUD / "Study Buddies" / "Chapter_118.cbz").exists())
        self.assertTrue((DOWNLOADS / "Study Buddies" / "Chapter_117.cbz").is_file())  # copy, not move
        self.pump(800)
        self.assertEqual(self.eval_qml("sideBar.icloudCount"), 2)  # 118 + Brand New ch 1 still waiting

    def test_select_all_and_new_folder(self):
        self.open_view()
        self.eval_qml("icloudView.setAll(true)")
        self.assertGreaterEqual(self.eval_qml("icloudView.selectedCount"), 2)
        self.eval_qml("icloudView.copySelected()")
        for _ in range(50):
            self.pump(100)
            if not self.eval_qml("icloudView.copying") and "Copied" in self.eval_qml("icloudView.summary"):
                break
        self.assertTrue((ICLOUD / "Brand New_" / "Chapter_1.cbz").is_file())
        self.assert_no_qml_warnings()


if __name__ == "__main__":
    unittest.main()
