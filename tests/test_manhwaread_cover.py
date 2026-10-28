import unittest

from src.providers.manhwaread import ManhwareadProvider

# Shape of the live page since 2026-10: og:image lost its host
# ("https:/wp-content/..."), while the cover <img> still has the real URL.
BROKEN_OG = """
<meta property="og:image" content="https:/wp-content/uploads/2024/07/manhwaread-bad-thinking-diary.webp">
<img width="227" height="320" alt="Doberman" src="https://mancover.xyz/cover/2025/01/manhwaread-doberman.webp">
<img width="500" height="666" alt="Bad Thinking Diary" loading="lazy" src="https://mancover.xyz/cover/2024/07/manhwaread-bad-thinking-diary.webp" srcset="https://mancover.xyz/cover/2024/07/manhwaread-bad-thinking-diary-350x467.webp 350w">
"""

GOOD_OG = '<meta property="og:image" content="http://mancover.xyz/cover/2024/07/x.webp">'


class ManhwareadCoverTest(unittest.TestCase):
    def cover(self, html):
        return ManhwareadProvider()._parse_metadata(html, "bad-thinking-diary")["cover_url"]

    def test_hostless_og_image_falls_back_to_page_cover_img(self):
        self.assertEqual(
            self.cover(BROKEN_OG),
            "https://mancover.xyz/cover/2024/07/manhwaread-bad-thinking-diary.webp",
        )

    def test_valid_og_image_is_used_and_upgraded_to_https(self):
        self.assertEqual(self.cover(GOOD_OG), "https://mancover.xyz/cover/2024/07/x.webp")


if __name__ == "__main__":
    unittest.main()
