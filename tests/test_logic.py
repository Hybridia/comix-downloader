"""Pure UI logic in gui/qml/**/*.js, run through QJSEngine."""
import unittest

from tests.qmljs import load


class Motion(unittest.TestCase):
    def test_stagger_delay_capped(self):
        m = load("gui/qml/logic/motion.js")
        self.assertEqual(m.call("staggerDelay", 0), 0)
        self.assertEqual(m.call("staggerDelay", 3), 135)
        self.assertEqual(m.call("staggerDelay", 259), 540)


class Chapters(unittest.TestCase):
    def test_matches(self):
        c = load("gui/qml/logic/chapters.js")
        self.assertTrue(c.call("matches", {"number": "55.5", "title": "Chapter 55.5"}, "55"))
        self.assertTrue(c.call("matches", {"number": "3", "title": "The END"}, "end"))
        self.assertFalse(c.call("matches", {"number": "3", "title": "x"}, "9"))
        self.assertTrue(c.call("matches", {"number": "3", "title": "x"}, "  "))

    def test_range(self):
        c = load("gui/qml/logic/chapters.js")
        self.assertEqual(c.call("rangeIndices", 5, 2), [2, 3, 4, 5])
        self.assertEqual(c.call("rangeIndices", -1, 4), [4])


class Badge(unittest.TestCase):
    def test_counts_down(self):
        b = load("gui/qml/logic/badge.js")
        s = b.call("jobStarted", b.call("empty"), "j1", 4)
        s = b.call("jobStarted", s, "j2", 2)
        s = b.call("chapterDone", s, "j1")
        self.assertEqual(b.call("count", s), 5)

    def test_badge_cancel_and_error(self):
        b = load("gui/qml/logic/badge.js")
        s = b.call("jobStarted", b.call("empty"), "j1", 3)
        s = b.call("jobEnded", s, "j1")
        s = b.call("chapterDone", s, "j1")  # late signal after end
        s = b.call("chapterDone", s, "unknown")
        self.assertEqual(b.call("count", s), 0)


class Palettes(unittest.TestCase):
    def test_exact_values_and_fallback(self):
        p = load("gui/qml/Style/palettes.js")
        self.assertEqual(p.call("palette", "ink")["accent"].lower(), "#ff7a93")
        self.assertEqual(p.call("palette", "neon")["cool"].lower(), "#35f0ff")
        self.assertEqual(p.call("palette", "ember")["bg"].lower(), "#0a0a0c")
        self.assertEqual(p.call("palette", "bogus"), p.call("palette", "ink"))


if __name__ == "__main__":
    unittest.main()
