"""The Library remembers which site each chapter was downloaded from, and
the update check always looks at those sites."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.utils import update_check
from src.utils.library import LibraryManager


def manga(url, source):
    return SimpleNamespace(source_url=url, source=source, title="Secret Class", alt_titles=[],
                           poster_url="", manga_type="manhwa", status="ongoing", is_nsfw=True)


class RecordSourceTest(unittest.TestCase):
    def setUp(self):
        self.lib = LibraryManager(Path(tempfile.mkdtemp()) / "library.json")
        self.lib._data["entries"].append({"source_url": "https://manhwabuddy.com/manhwa/secret-class",
                                          "title": "Secret Class", "chapters": {}})
        self.lib._save()

    def record(self, num, url="https://manhwa18.cc/webtoon/secret-class-01", source="manhwa18cc"):
        self.lib.record_chapter(manga(url, source), SimpleNamespace(number=num, title=""), "cbz", "downloads",
                                library_url="https://manhwabuddy.com/manhwa/secret-class")

    def test_chapter_and_entry_remember_the_site(self):
        self.record("322")
        self.record("323")
        e = self.lib.get_entry("https://manhwabuddy.com/manhwa/secret-class")
        self.assertEqual(e["chapters"]["322"]["source"], "https://manhwa18.cc/webtoon/secret-class-01")
        (ds,) = e["download_sources"]
        self.assertEqual((ds["url"], ds["provider"], ds["last_chapter"], ds["chapters"]),
                         ("https://manhwa18.cc/webtoon/secret-class-01", "manhwa18cc", "323", 2))
        self.assertTrue(ds["last_downloaded_at"])

    def test_two_sites_kept_separately_newest_first(self):
        self.record("320", url="https://manhwabuddy.com/manhwa/secret-class/", source="manhwabuddy")
        self.record("322")
        e = self.lib.get_entry("https://manhwabuddy.com/manhwa/secret-class")
        self.assertEqual([d["provider"] for d in e["download_sources"]], ["manhwa18cc", "manhwabuddy"])


class CheckUsesDownloadSourcesTest(unittest.TestCase):
    def test_download_site_is_always_probed_and_wins_ties(self):
        root = Path(tempfile.mkdtemp())
        folder = root / "Secret Class"
        folder.mkdir()
        (folder / "Chapter_321.cbz").write_bytes(b"x")
        entry = {"source_url": "https://manhwabuddy.com/manhwa/secret-class", "title": "Secret Class",
                 "download_path": str(root), "folder": "Secret Class",
                 # enricher thought this mirror was far behind — normally skipped
                 "alternative_sources": [{"url": "https://manhwa18.cc/webtoon/secret-class-01", "chapter_count": 5}],
                 "download_sources": [{"url": "https://manhwa18.cc/webtoon/secret-class-01", "provider": "manhwa18cc",
                                       "last_chapter": "321", "chapters": 1}]}
        probed = []

        def fake_probe(url, on_disk, on_disk_max):
            probed.append(url)
            return {"url": url, "provider": "x", "title": "", "latest": "322", "remote_count": 322,
                    "newer": [{"norm": "322"}], "gaps": [], "error": "", "manga": None, "status": None}

        with mock.patch.object(update_check, "_probe", fake_probe), \
             mock.patch.object(update_check, "downloads_root", return_value=root / "none"), \
             mock.patch("src.utils.library.shared", return_value=mock.Mock()), \
             mock.patch("src.utils.provenance.scan_folder",
                        return_value={"sources": [], "local": 0, "cloud_only": 0}):
            r = update_check.check_entry(entry)
        self.assertIn("https://manhwa18.cc/webtoon/secret-class-01", probed)
        dl = next(s for s in r["sources"] if s["url"] == "https://manhwa18.cc/webtoon/secret-class-01")
        self.assertTrue(dl["is_downloaded"])
        self.assertEqual(dl["downloaded_last"], "321")
        # same number of new chapters as the main site → the site you downloaded from wins
        self.assertEqual(r["sources"][r["recommended"]]["url"], "https://manhwa18.cc/webtoon/secret-class-01")


if __name__ == "__main__":
    unittest.main()
