"""Chapters already waiting in ./downloads count as "on disk" for the
update check — otherwise every check re-lists chapters that were already
downloaded but not yet moved into iCloud."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.utils import update_check


def cbz(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", b"x")


class ChaptersOnDiskTest(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.icloud = root / "Manga" / "Someone Stop Her"
        self.downloads = root / "downloads"
        for n in (77, 78):
            cbz(self.icloud / f"Chapter_{n}.cbz")
        cbz(self.downloads / "Someone Stop Her_ _Uncensored_" / "Chapter_79.cbz")   # site's title
        cbz(self.downloads / "Someone Else" / "Chapter_80.cbz")                     # another series
        self.entry = {"title": "Someone Stop Her!", "folder": "Someone Stop Her",
                      "download_path": str(self.icloud.parent), "source_url": "https://x/s",
                      "alternative_sources": [{"title_on_site": "Someone Stop Her! (Uncensored)"}]}

    def test_includes_matching_downloads_folder(self):
        got = update_check.chapters_on_disk(self.entry, self.icloud, downloads_root=self.downloads)
        self.assertEqual(got, {"77", "78", "79"})

    def test_folder_inside_downloads_is_not_counted_twice(self):
        folder = self.downloads / "Someone Else"
        got = update_check.chapters_on_disk({"title": "Someone Else"}, folder, downloads_root=self.downloads)
        self.assertEqual(got, {"80"})

    def test_check_entry_treats_downloaded_chapters_as_present(self):
        seen = {}

        def fake_probe(url, on_disk, on_disk_max):
            seen["on_disk"], seen["max"] = set(on_disk), on_disk_max
            return {"url": url, "provider": "x", "title": "", "latest": "79", "remote_count": 79,
                    "newer": [], "gaps": [], "error": "", "manga": None, "status": None}

        lib = mock.Mock()
        with mock.patch.object(update_check, "_probe", fake_probe), \
             mock.patch.object(update_check, "downloads_root", return_value=self.downloads), \
             mock.patch("src.utils.library.shared", return_value=lib), \
             mock.patch("src.utils.provenance.scan_folder",
                        return_value={"sources": [], "local": 0, "cloud_only": 0}):
            update_check.check_entry(self.entry)
        self.assertEqual(seen["on_disk"], {"77", "78", "79"})
        self.assertEqual(seen["max"], 79.0)


class DownloadsProvenanceTest(unittest.TestCase):
    def test_sites_of_cbzs_waiting_in_downloads_are_detected(self):
        root = Path(tempfile.mkdtemp())
        icloud = root / "Manga" / "Secret Class"
        cbz(icloud / "Chapter_321.cbz")
        dl = root / "downloads" / "Secret Class"
        dl.mkdir(parents=True)
        with zipfile.ZipFile(dl / "Chapter_322.cbz", "w") as z:
            z.writestr("ComicInfo.xml", "<ComicInfo><Web>https://manhwa18.cc/webtoon/secret-class-01</Web></ComicInfo>")
            z.writestr("001.jpg", b"x")
        entry = {"title": "Secret Class", "folder": "Secret Class", "download_path": str(icloud.parent),
                 "source_url": "https://manhwabuddy.com/manhwa/secret-class"}
        probed = []

        def fake_probe(url, on_disk, on_disk_max):
            probed.append(url)
            return {"url": url, "provider": "x", "title": "", "latest": "322", "remote_count": 1,
                    "newer": [], "gaps": [], "error": "", "manga": None, "status": None}

        with mock.patch.object(update_check, "_probe", fake_probe), \
             mock.patch.object(update_check, "downloads_root", return_value=root / "downloads"), \
             mock.patch("src.utils.library.shared", return_value=mock.Mock()):
            r = update_check.check_entry(entry)
        self.assertEqual(probed[0], "https://manhwa18.cc/webtoon/secret-class-01")
        self.assertIn("https://manhwa18.cc/webtoon/secret-class-01", [d["url"] for d in r["detected"]])


if __name__ == "__main__":
    unittest.main()
