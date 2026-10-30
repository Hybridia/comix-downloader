"""Copy chapters waiting in ./downloads into the series' iCloud folder."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.utils import icloud_push


def cbz(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", data)
    return path


class Env:
    def __init__(self):
        root = Path(tempfile.mkdtemp())
        self.icloud = root / "Manga"
        self.downloads = root / "downloads"
        self.icloud.mkdir()
        self.downloads.mkdir()
        (self.icloud / ".reader_state.json").write_text("{}")


class CopyChaptersTest(unittest.TestCase):
    def test_copies_and_never_overwrites(self):
        e = Env()
        target = e.icloud / "Secret Class"
        cbz(target / "Chapter_321.cbz", b"old")
        new = cbz(e.downloads / "Secret Class" / "Chapter_322.cbz")
        dup = cbz(e.downloads / "Secret Class" / "Chapter_321.cbz", b"newer bytes")
        res = icloud_push.copy_chapters([new, dup], target, icloud_root=e.icloud)
        self.assertEqual(res["copied"], ["Chapter_322.cbz"])
        self.assertEqual(res["skipped"], ["Chapter_321.cbz"])
        self.assertEqual((target / "Chapter_322.cbz").read_bytes(), new.read_bytes())
        self.assertTrue(new.exists())  # a copy: downloads keeps its file
        with zipfile.ZipFile(target / "Chapter_321.cbz") as z:
            self.assertEqual(z.read("001.jpg"), b"old")  # untouched
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["Chapter_321.cbz", "Chapter_322.cbz"])

    def test_same_chapter_in_another_notation_is_skipped(self):
        e = Env()
        target = e.icloud / "X"
        cbz(target / "Chapter_62_5.cbz")
        res = icloud_push.copy_chapters([cbz(e.downloads / "X" / "Chapter_62.5.cbz")], target,
                                        icloud_root=e.icloud)
        self.assertEqual(res["skipped"], ["Chapter_62.5.cbz"])

    def test_creates_a_new_series_folder(self):
        e = Env()
        target = e.icloud / "Brand New"
        res = icloud_push.copy_chapters([cbz(e.downloads / "Brand New" / "Chapter_1.cbz")], target,
                                        icloud_root=e.icloud)
        self.assertEqual(res["copied"], ["Chapter_1.cbz"])
        self.assertTrue((target / "Chapter_1.cbz").is_file())

    def test_only_writes_into_a_series_folder_of_the_icloud_folder(self):
        e = Env()
        f = cbz(e.downloads / "X" / "Chapter_1.cbz")
        for bad in (e.icloud, e.icloud.parent / "elsewhere", e.icloud / "A" / "B", e.icloud / ".hidden"):
            with self.assertRaises(ValueError):
                icloud_push.copy_chapters([f], bad, icloud_root=e.icloud)
        self.assertEqual((e.icloud / ".reader_state.json").read_text(), "{}")


class PendingTest(unittest.TestCase):
    def test_lists_chapters_not_yet_in_icloud(self):
        e = Env()
        cbz(e.icloud / "Someone Stop Her_ - Uncensored" / "Chapter_78.cbz")
        cbz(e.downloads / "Someone Stop Her_ _Uncensored_" / "Chapter_78.cbz")
        c79 = cbz(e.downloads / "Someone Stop Her_ _Uncensored_" / "Chapter_79.cbz")
        entry = {"title": "Someone Stop Her! (Uncensored)", "folder": "Someone Stop Her_ - Uncensored",
                 "download_path": str(e.icloud), "source_url": "https://x/s"}
        p = icloud_push.pending_for_entry(entry, downloads_root=e.downloads, icloud_root=e.icloud, entries=[entry])
        self.assertEqual(p["target"], e.icloud / "Someone Stop Her_ - Uncensored")
        self.assertTrue(p["target_exists"])
        self.assertEqual([(c["number"], c["path"]) for c in p["chapters"]], [("79", c79)])

    def test_new_series_targets_a_folder_named_like_its_downloads_folder(self):
        e = Env()
        c1 = cbz(e.downloads / "Brand New_" / "Chapter_1.cbz")
        entry = {"title": "Brand New!", "folder": "Brand New_", "download_path": str(e.downloads),
                 "source_url": "https://x/b"}
        p = icloud_push.pending_for_entry(entry, downloads_root=e.downloads, icloud_root=e.icloud, entries=[entry])
        self.assertEqual(p["target"], e.icloud / "Brand New_")
        self.assertFalse(p["target_exists"])
        self.assertEqual([c["path"] for c in p["chapters"]], [c1])
