"""Parsing tests for the 2026-10 adult manhwa providers.

Fixtures are trimmed copies of the live markup (checked on two series
per site), so a layout change on a site shows up here first.
"""
import unittest

from src.providers.router import get_provider_for_url


def provider(url):
    p = get_provider_for_url(url)
    assert p is not None, f"no provider for {url}"
    return p


# ── Madara sites: manhwa68 / toongod / webtoon.xyz ──────────────────────

MADARA_SERIES = """
<meta property="og:title" content="Love Cheer! Manhwa Free Chapters in English | ToonGod" />
<meta property="og:description" content="&quot;Go, go, team!&quot; A mascot..." />
<meta property="og:image" content="https://www.toongod.org/wp-content/uploads/2026/06/love-cheer-manhwa.webp" />
<div class="post-title"> <span class="manga-title-badges hot">HOT</span> <h1> Love Cheer! </h1> </div>
<div class="post-content_item"> <div class="summary-heading"> <h5> Alternative </h5> </div> <div class="summary-content"> 치어 러브! </div> </div>
<div class="post-content_item"> <div class="summary-heading"> <h5> Status </h5> </div> <div class="summary-content"> OnGoing </div> </div>
<ul class="main version-chap no-volumn">
<li class="wp-manga-chapter "> <a href="https://www.toongod.org/webtoon/love-cheer/chapter-27/"> Chapter 27 </a>
 <span class="chapter-release-date"> <a href="https://www.toongod.org/webtoon/love-cheer/chapter-27/" class="c-new-tag"></a> </span> </li>
<li class="wp-manga-chapter "> <a href="https://www.toongod.org/webtoon/love-cheer/chapter-26-5/"> Chapter 26.5 </a> </li>
<li class="wp-manga-chapter "> <a href="https://www.toongod.org/webtoon/love-cheer/chapter-1/"> Chapter 1 </a> </li>
</ul>
"""

MADARA_READER = """
<div class="reading-content"> <input type="hidden" id="wp-manga-current-chap" data-id="34474" value="chapter-1"/>
<div class="page-break "> <img id="image-0" data-src=" https://i.tngcdn.com/manga_6a1/7965/001_1.jpg" class="wp-manga-chapter-img img-responsive lazyload effect-fade"> </div>
<div class="page-break "> <img id="image-1" src="https://i.tngcdn.com/manga_6a1/7965/001_2.jpg" class="wp-manga-chapter-img"> </div>
</div>
<div class="related"><img src="https://www.toongod.org/wp-content/uploads/2025/08/other-cover.jpg"></div>
"""


class MadaraSitesTest(unittest.TestCase):
    def test_routing_and_slug(self):
        cases = {
            "https://manhwa68.com/manga/simple-yet-sexy/": ("manhwa68", "simple-yet-sexy"),
            "https://www.toongod.org/webtoon/love-cheer/chapter-3/": ("toongod", "love-cheer"),
            "https://www.webtoon.xyz/read/single-daddy/": ("webtoonxyz", "single-daddy"),
        }
        for url, (name, slug) in cases.items():
            p = provider(url)
            self.assertEqual((p.name, p.extract_code(url)), (name, slug))

    def test_metadata(self):
        meta = provider("https://www.toongod.org/webtoon/love-cheer/")._parse_metadata(
            MADARA_SERIES, "love-cheer"
        )
        self.assertEqual(meta["title"], "Love Cheer!")
        self.assertEqual(meta["cover"], "https://www.toongod.org/wp-content/uploads/2026/06/love-cheer-manhwa.webp")
        self.assertEqual(meta["status"], "OnGoing")
        self.assertEqual(meta["alt_titles"], ["치어 러브!"])
        self.assertTrue(meta["description"].startswith('"Go, go, team!"'))

    def test_chapters_dedupe_and_decimal_numbers(self):
        rows = provider("https://www.toongod.org/webtoon/love-cheer/")._parse_chapter_rows(
            MADARA_SERIES, "love-cheer"
        )
        self.assertEqual([n for _u, n in rows], ["27", "26.5", "1"])
        self.assertEqual(rows[0][0], "https://www.toongod.org/webtoon/love-cheer/chapter-27/")

    def test_reader_images_only_chapter_pages(self):
        imgs = provider("https://www.toongod.org/webtoon/love-cheer/")._extract_images(MADARA_READER)
        self.assertEqual(imgs, [
            "https://i.tngcdn.com/manga_6a1/7965/001_1.jpg",
            "https://i.tngcdn.com/manga_6a1/7965/001_2.jpg",
        ])

    def test_numeric_alternative_is_ignored(self):
        html = MADARA_SERIES.replace("치어 러브!", "1")
        meta = provider("https://manhwa68.com/manga/x/")._parse_metadata(html, "x")
        self.assertEqual(meta["alt_titles"], [])


# ── manga18fx engine: manhwa18.cc / manga18.me ──────────────────────────

M18_SERIES = """
<meta property="og:description" content="A harmless hypnosis experiment turns into an obsession.">
<meta property="og:image" content="https://manhwa18.cc/manga/under-my-spell-4248.jpg">
<div class="post-title wleft"> <h1> <span>18+</span> Under My Spell </h1> </div>
<div class="post-content_item wleft"> <div class="summary-heading"> <h5> Alternative: </h5> </div> <div class="summary-content"> I Hypnotized My Aunt / 이모에게 최면을 걸다 </div> </div>
<div class="post-content_item wleft"> <div class="summary-heading"> <h5> Status </h5> </div> <div class="summary-content" style="text-align: right"> OnGoing </div> </div>
<a class="rfirst tcenter" href="/webtoon/under-my-spell/chapter-1"> Read First </a>
<li class="a-h wleft"> <a class="chapter-name text-nowrap" href="/webtoon/under-my-spell/chapter-6" title="Under My Spell Chapter 6">Chapter 6</a> </li>
<li class="a-h wleft"> <a class="chapter-name text-nowrap" href="/webtoon/under-my-spell/chapter-5-5" title="x">Chapter 5.5</a> </li>
<li class="a-h wleft"> <a class="chapter-name text-nowrap" href="/webtoon/under-my-spell/chapter-1" title="x">Chapter 1</a> </li>
<div class="chapter-item wleft"> <span class="chapter"> <a href="/webtoon/bad-girl-punishment-raw/chapter-55" class="btn-link">Chapter 55</a></span></div>
"""

M18_READER_DOUBLE = """
<div class="read-content wleft tcenter"> <img class="loading p1" data-src="https://img11.manhwa18.cc/chapters/1892/1/1-7116.jpg" src="https://img11.manhwa18.cc/chapters/1892/1/1-7116.jpg" loading="lazy">
<img class="loading p2" data-src="https://img11.manhwa18.cc/chapters/1892/1/2-7116.jpg" src="https://img11.manhwa18.cc/chapters/1892/1/2-7116.jpg"> </div>
<div class="comments"><img src="https://manhwa18.cc/manga/other-12.jpg"></div>
<img src="//sstatic1.histats.com/0.gif?4521822&101">
"""

M18_READER_SINGLE = """
<div class="read-content wleft"> <img class='p1' data-src='https://img-r11.manga18.me/chapters/223/1/1-87117.jpg' src='https://img-r11.manga18.me/chapters/223/1/1-87117.jpg' alt='Page 1'/><br><img class='p2' data-src='https://img-r11.manga18.me/chapters/223/1/2-87117.jpg' src='x'/><br></div>
<img src='https://manga18.me/${data.content.avatar}'>
"""


class Manga18EngineTest(unittest.TestCase):
    def test_routing_and_slug(self):
        p = provider("https://manhwa18.cc/webtoon/secret-class-01/chapter-320")
        self.assertEqual((p.name, p.extract_code("https://manhwa18.cc/webtoon/secret-class-01/chapter-320")),
                         ("manhwa18cc", "secret-class-01"))
        p = provider("https://manga18.me/manga/love-quest")
        self.assertEqual((p.name, p.extract_code("https://manga18.me/manga/love-quest")), ("manga18me", "love-quest"))

    def test_does_not_steal_existing_sites(self):
        self.assertEqual(provider("https://manga18fx.com/manga/x").name, "manga18fx")
        self.assertEqual(provider("https://www.manhwa18.com/manga/x").name, "manhwa18")
        self.assertEqual(provider("https://www.manhwa18.net/manga/x").name, "manhwa18net")

    def test_metadata_strips_18_badge(self):
        meta = provider("https://manhwa18.cc/webtoon/under-my-spell")._parse_metadata(M18_SERIES, "under-my-spell")
        self.assertEqual(meta["title"], "Under My Spell")
        self.assertEqual(meta["alt_titles"], ["I Hypnotized My Aunt", "이모에게 최면을 걸다"])
        self.assertEqual(meta["status"], "OnGoing")

    def test_chapters_skip_sidebar_and_buttons(self):
        rows = provider("https://manhwa18.cc/webtoon/under-my-spell")._parse_chapter_rows(M18_SERIES, "under-my-spell")
        self.assertEqual([n for _u, n in rows], ["6", "5.5", "1"])
        self.assertEqual(rows[0][0], "https://manhwa18.cc/webtoon/under-my-spell/chapter-6")

    def test_reader_images_both_quote_styles(self):
        self.assertEqual(
            provider("https://manhwa18.cc/webtoon/x")._extract_images(M18_READER_DOUBLE),
            ["https://img11.manhwa18.cc/chapters/1892/1/1-7116.jpg",
             "https://img11.manhwa18.cc/chapters/1892/1/2-7116.jpg"],
        )
        self.assertEqual(
            provider("https://manga18.me/manga/x")._extract_images(M18_READER_SINGLE),
            ["https://img-r11.manga18.me/chapters/223/1/1-87117.jpg",
             "https://img-r11.manga18.me/chapters/223/1/2-87117.jpg"],
        )


# ── hentai20.io (MangaReader theme) ─────────────────────────────────────

H20_SERIES = """
<meta property="og:description" content="I was the only commoner at an elite school" />
<h1 class="entry-title" itemprop="name">I Banged All My Classmates After Graduation</h1>
<div class="thumb" itemprop="image"> <img width="193" height="278" src="https://hentai20.io/wp-content/uploads/2026/10/7730d7-193x278.jpg" class="attachment- size- wp-post-image" alt="x"> </div>
<table class="infotable"> <tbody> <tr> <td>Status</td> <td>Ongoing</td> </tr> </tbody></table>
<div class="inepcx"> <a href="https://hentai20.io/i-banged-all-my-classmates-after-graduation-chapter-20/"> <span>Latest:</span> </a></div>
<li data-num="20"> <div class="chbox"> <div class="eph-num"> <a href="https://hentai20.io/i-banged-all-my-classmates-after-graduation-chapter-20/"> <span class="chapternum">Chapter 20</span> </a> </div> </div> </li>
<li data-num="19.5"> <div class="chbox"> <div class="eph-num"> <a href="https://hentai20.io/i-banged-all-my-classmates-after-graduation-chapter-19-5/"> <span class="chapternum">Chapter 19.5</span> </a> </div> </div> </li>
<li data-num="1"> <div class="chbox"> <div class="eph-num"> <a href="https://hentai20.io/i-banged-all-my-classmates-after-graduation-chapter-1/"> <span class="chapternum">Chapter 1</span> </a> </div> </div> </li>
"""

H20_READER = """
<div id="readerarea"><noscript><p><img decoding="async" src="https://img.hentai1.io/x/chapter-19/001-c50a.jpg" /><br />
<img decoding="async" src="https://img.hentai1.io/x/chapter-19/002-2c2e.jpg" /></p></noscript>
<p><img decoding="async" src="https://img.hentai1.io/x/chapter-19/001-c50a.jpg" /><img decoding="async" src="https://img.hentai1.io/x/chapter-19/002-2c2e.jpg" /></p></div>
<div class="bixbox"><img src="https://hentai20.io/wp-content/themes/mangareader/assets/img/readerarea.svg"></div>
"""


class Hentai20Test(unittest.TestCase):
    url = "https://hentai20.io/manga/i-banged-all-my-classmates-after-graduation/"

    def test_routing_from_series_and_chapter_urls(self):
        p = provider(self.url)
        self.assertEqual(p.name, "hentai20")
        self.assertEqual(p.extract_code(self.url), "i-banged-all-my-classmates-after-graduation")
        self.assertEqual(
            p.extract_code("https://hentai20.io/i-banged-all-my-classmates-after-graduation-chapter-19/"),
            "i-banged-all-my-classmates-after-graduation",
        )

    def test_metadata(self):
        meta = provider(self.url)._parse_metadata(H20_SERIES, "x")
        self.assertEqual(meta["title"], "I Banged All My Classmates After Graduation")
        # Only the 193x278 thumbnail exists (the un-suffixed file 404s).
        self.assertEqual(meta["cover"], "https://hentai20.io/wp-content/uploads/2026/10/7730d7-193x278.jpg")
        self.assertEqual(meta["status"], "Ongoing")
        self.assertEqual(meta["alt_titles"], [])

    def test_chapters(self):
        rows = provider(self.url)._parse_chapter_rows(H20_SERIES, "x")
        self.assertEqual([n for _u, n in rows], ["20", "19.5", "1"])

    def test_reader_images_deduped(self):
        self.assertEqual(provider(self.url)._extract_images(H20_READER), [
            "https://img.hentai1.io/x/chapter-19/001-c50a.jpg",
            "https://img.hentai1.io/x/chapter-19/002-2c2e.jpg",
        ])


# ── manhwalike.com ──────────────────────────────────────────────────────

ML_SERIES = """
<meta property="og:image" content="https://media.manhwalike.com/images/fullsize/2021/09/25/secret-class.jpg"/>
<meta property="og:description" content="❶❶✅ Read Secret Class [To Chapter 318] Manga in English Online for Free at ManhwaLike.">
<div class="main-head"> <h1>Secret Class</h1>
<div class="other-name"> <span>Other name: Secret Class; 비밀 수업</span> </div>
<span> <small>Status</small> <strong class="ongoing"> Ongoing</strong> </span>
<div class="summary-block"> <p class="summary">You are reading <strong>Secret Class</strong> manga, one of the most popular...</p> <p class="about">Daeho has been living with his aunt's family.</p> </div>
<ul class="chapter-list">
<li><a href="/manga-secret-class-chapter-318-ch281377">Chapter 318</a> <span class="time">September 28, 2026</span> </li>
<li><a href="/manga-secret-class-chapter-316-5-ch280660">Chapter 316.5</a></li>
<li><a href="/manga-secret-class-chapter-1-ch637 ">Chapter 1</a></li>
</ul>
<a href="/secret-class-latest-chapters">Latest</a>
"""

ML_READER = """
<div class="chapter-content"> <div class="ads-block"> <script src="//ads.example/invoke.js"></script> </div>
<div class="page-chapter"><img src="https://stcdn.manhwalike.com/images/manga/secret-class/chapter-317/0.jpg" alt="Page 1"></div>
<div id="page-1" class="page-chapter"><img data-src="https://stcdn.manhwalike.com/images/manga/secret-class/chapter-317/1.jpg" src="https://static.manhwalike.com/images/loading.gif"></div>
</div>
<footer><img src="https://static.manhwalike.com/images/logo.png"></footer>
"""


class ManhwalikeTest(unittest.TestCase):
    url = "https://manhwalike.com/manga-secret-class"

    def test_routing_from_series_and_chapter_urls(self):
        p = provider(self.url)
        self.assertEqual(p.name, "manhwalike")
        self.assertEqual(p.extract_code(self.url), "secret-class")
        self.assertEqual(p.extract_code("https://manhwalike.com/manga-secret-class-chapter-317-ch280661"), "secret-class")

    def test_metadata(self):
        meta = provider(self.url)._parse_metadata(ML_SERIES, "secret-class")
        self.assertEqual(meta["title"], "Secret Class")
        self.assertEqual(meta["cover"], "https://media.manhwalike.com/images/fullsize/2021/09/25/secret-class.jpg")
        self.assertEqual(meta["status"], "Ongoing")
        self.assertEqual(meta["alt_titles"], ["비밀 수업"])
        self.assertEqual(meta["description"], "Daeho has been living with his aunt's family.")

    def test_boilerplate_about_is_not_a_description(self):
        html = ML_SERIES.replace(
            "Daeho has been living with his aunt's family.",
            "Secret Class manga is updated earliest and fully at ManhwaLike. Readers, don't forget to comment.",
        )
        self.assertEqual(provider(self.url)._parse_metadata(html, "secret-class")["description"], "")

    def test_chapters(self):
        rows = provider(self.url)._parse_chapter_rows(ML_SERIES, "secret-class")
        self.assertEqual([n for _u, n in rows], ["318", "316.5", "1"])
        self.assertEqual(rows[2][0], "https://manhwalike.com/manga-secret-class-chapter-1-ch637")

    def test_reader_images_skip_placeholders(self):
        self.assertEqual(provider(self.url)._extract_images(ML_READER), [
            "https://stcdn.manhwalike.com/images/manga/secret-class/chapter-317/0.jpg",
            "https://stcdn.manhwalike.com/images/manga/secret-class/chapter-317/1.jpg",
        ])

    def test_image_referer_set(self):
        self.assertEqual(provider(self.url).image_referer, "https://manhwalike.com/")


if __name__ == "__main__":
    unittest.main()
