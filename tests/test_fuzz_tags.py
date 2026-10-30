import unittest

from src.utils.update_check import _fuzz_loose


class FuzzTagsTest(unittest.TestCase):
    def test_motion_tag_is_ignored_like_uncensored(self):
        # Library title vs the iCloud folder the user made for it
        self.assertEqual(_fuzz_loose("[MOTION] Tales of the Feral Maidens (Uncensored)"),
                         _fuzz_loose("Tales of the Feral Maidens _Uncensored_"))
        # the downloader's own folder name for the same series
        self.assertEqual(_fuzz_loose("_MOTION_ Tales of the Feral Maidens _Uncensored_"),
                         _fuzz_loose("Tales of the Feral Maidens"))
