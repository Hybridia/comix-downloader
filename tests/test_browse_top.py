"""Task 6: animated URL input and manga card reveal."""
import unittest

from tests.qmlsmoke import Smoke

MANGA = {
    "title": "Moby Dick", "poster_url": "", "is_nsfw": True, "manga_type": "manhwa",
    "original_language": "ko", "status": "releasing", "year": 2023, "latest_chapter": 114,
    "follows_total": 48210, "rated_avg": 4.7, "description": "A harpooner and a whale. " * 20,
    "tags": ["Drama", "Romance", "Full Color"], "source": "toonily", "source_url": "https://toonily.com/serie/x/",
}


class BrowseTop(Smoke):
    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_match_state_on_known_url(self):
        self.find("urlField").setProperty("text", "https://toonily.com/serie/moby-dick-21be71a7/")
        self.pump(100)
        self.assertTrue(self.find("urlInput").property("matched"))
        self.assertTrue(self.find("fetchButton").property("ready"))
        self.find("urlField").setProperty("text", "")
        self.pump(50)
        self.assertFalse(self.find("fetchButton").property("ready"))

    def test_shake_on_unknown_enter(self):
        m = self.bridges["manga"]
        calls = []
        m.errorOccurred.connect(lambda *_: calls.append("err"))
        m.loadingChanged.connect(lambda *_: calls.append("load"))
        self.find("urlField").setProperty("text", "not a manga site at all")
        self.pump(50)
        self.call(self.find("urlInput"), "submit")
        self.pump(60)
        self.assertTrue(self.find("urlInput").property("shaking"))
        self.pump(700)
        self.assertFalse(self.find("urlInput").property("shaking"))
        self.assertEqual(calls, [])
        self.assertTrue(self.find("urlInput").property("invalid"))
        self.find("urlField").setProperty("text", "")

    def test_skeleton_while_fetching(self):
        m = self.bridges["manga"]
        m.loadingChanged.emit(True)
        self.pump(50)
        card = self.find("mangaCard")
        self.assertTrue(card.property("loading"))
        self.assertTrue(card.property("visible"))
        m.mangaLoaded.emit(MANGA)
        self.pump(50)
        self.assertFalse(card.property("loading"))
        m.loadingChanged.emit(False)
        self.pump(1500)
        self.assertEqual(self.find("mangaFollowers").property("text"), "48,210")
        self.assert_no_qml_warnings()


if __name__ == "__main__":
    unittest.main()
