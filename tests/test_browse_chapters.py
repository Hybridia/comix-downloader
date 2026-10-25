"""Task 7: chapter list (filter, range select, select-all), format selector, download button."""
import unittest

from tests.qmlsmoke import Smoke


def chapters(n):
    return [{"chapter_id": 0, "number": str(i), "title": f"Chapter {i}", "group_name": "",
             "volume": f"https://x/ch-{i}", "selected": False} for i in range(n, 0, -1)]


class BrowseChapters(Smoke):
    def setUp(self):
        self.list = self.find("chapterList")
        self.call(self.list, "setTextFilter", "")
        self.call(self.list, "setChapters", chapters(12))
        self.pump(50)

    def selected(self):
        return self.list.property("selectedCount")

    def test_loads_clean(self):
        self.assert_no_qml_warnings()

    def test_filter_hides_rows(self):
        self.call(self.list, "setTextFilter", "1")
        self.pump(50)
        # numbers containing "1": 12, 11, 10, 1  (titles "Chapter 1x" too → same set)
        self.assertEqual(self.list.property("visibleCount"), 4)
        self.call(self.list, "setTextFilter", "")
        self.pump(50)
        self.assertEqual(self.list.property("visibleCount"), 12)

    def test_select_all_visible_only(self):
        self.call(self.list, "setTextFilter", "1")
        self.call(self.list, "selectAllVisible", True)
        self.pump(50)
        self.assertEqual(self.selected(), 4)
        self.call(self.list, "setTextFilter", "")
        self.call(self.list, "selectAllVisible", False)
        self.assertEqual(self.selected(), 0)

    def test_shift_click_range(self):
        self.call(self.list, "toggleAt", 2, False)
        self.call(self.list, "toggleAt", 5, True)
        self.pump(50)
        self.assertEqual(self.selected(), 4)

    def test_shift_click_without_anchor_is_plain_click(self):
        self.call(self.list, "toggleAt", 3, True)
        self.assertEqual(self.selected(), 1)

    def test_format_selector_writes_setting(self):
        s = self.bridges["settings"]
        sel = self.find("browseFormat")
        self.call(sel, "choose", 1)
        self.assertEqual(s.property("outputFormat"), "pdf")
        s.setValue("output_format", "images")
        self.pump(20)
        self.assertEqual(sel.property("idx"), 2)

    def test_download_with_none_selected_does_not_dispatch(self):
        d = self.bridges["download"]
        events = []
        d.errorOccurred.connect(lambda *_: events.append("err"))
        d.downloadStarted.connect(lambda *_: events.append("start"))
        controls = self.find("downloadControls")
        self.call(controls, "requestDownload")
        self.pump(60)
        self.assertTrue(controls.property("shaking"))
        self.pump(600)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
