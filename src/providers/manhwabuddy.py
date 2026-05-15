"""
manhwabuddy.com provider — multi-chapter NSFW-leaning manhwa site.

This is the simplest provider in the matrix: plain HTML, no JS, no
AJAX, no obfuscation. Two endpoints are all we need:

- **Series page** ``https://manhwabuddy.com/manhwa/<slug>/`` — embeds
  the full chapter list as ``<li class="myfut"><a href="/manhwa/<slug>/
  chapter-NN/" title="..."><span class="chapter-name">Chapter NN</span>``.
  ``<title>``, ``<meta property="og:image">``, and ``<meta name=
  "description">`` give us title / cover / synopsis (+ alt titles
  baked in slash-delimited at the start of the description).
- **Reader page** ``https://manhwabuddy.com/manhwa/<slug>/chapter-NN/``
  — embeds every image directly as ``<img class="loading" data-src=
  "https://imgNN.manhwabuddy.com/chapters/<manga_id>/<chap_n>/<page>-eeN.jpg"
  src="...">``. Source order matches reading order; we read
  ``data-src`` because some lazy-loading themes leave the visible
  ``src`` empty on first paint.

Cloudflare-protected but the default ``get_session()`` (curl_cffi
chrome120 impersonation) sails through. The image CDN
(``imgNN.manhwabuddy.com``) checks Referer — set
``image_referer = "https://manhwabuddy.com/"``.
"""

import re
from html import unescape
from typing import Optional

from .base import Provider
from ..core.models import Chapter, MangaInfo
from ..utils.logger import get_logger
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session

logger = get_logger(__name__)


_SLUG_RE = re.compile(r"/manhwa/([^/?#]+)", re.IGNORECASE)
_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
_META_DESC_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]+)"', re.IGNORECASE
)
_TITLE_RE = re.compile(r"<title>(.+?)</title>", re.IGNORECASE | re.DOTALL)
# Series sidebar exposes a ``<li><h5>Status</h5><span>Completed</span></li>``
# pair (no class on the span — the markup is dirt-simple). We anchor
# on the ``<h5>Status</h5>`` label so future markup additions to that
# block don't break us.
_STATUS_RE = re.compile(
    r'<h5[^>]*>\s*Status\s*</h5>\s*<span[^>]*>\s*([^<]+?)\s*</span>',
    re.IGNORECASE,
)
# `<a href="/manhwa/<slug>/chapter-N/" title="<series> - Chapter N">
#    <span class="chapter-name">Chapter N</span>` —
# capture the href + the visible "Chapter N" label. data-date /
# release info lives in a sibling span which we don't need.
_CHAPTER_ITEM_RE = re.compile(
    r'<a\s+href="(/manhwa/[^"]+/chapter-[^"/]+/?)"[^>]*>\s*'
    r'<span[^>]*class="[^"]*chapter-name[^"]*"[^>]*>([^<]+)</span>',
    re.IGNORECASE | re.DOTALL,
)
_CHAPTER_NUM_RE = re.compile(
    r"chapter[-\s]*(\d+(?:\.\d+)?)", re.IGNORECASE
)
# Reader page images. ``data-src`` is the primary attribute because
# the lazy-loader sometimes blanks ``src`` until the IntersectionObserver
# fires. We accept either, in that order.
_READER_IMG_RE = re.compile(
    r'<img[^>]*\bdata-src="([^"]+)"', re.IGNORECASE
)
# Adult-content body class — manhwabuddy uses ``<body class="mybody
# adult-content">`` on NSFW series.
_ADULT_BODY_RE = re.compile(r'<body[^>]*\badult-content\b', re.IGNORECASE)


class ManhwabuddyProvider(Provider):
    """Provider for https://manhwabuddy.com/ ."""

    name = "manhwabuddy"
    label = "manhwabuddy.com"
    domains = ("manhwabuddy.com",)
    image_referer = "https://manhwabuddy.com/"
    example_url = "https://manhwabuddy.com/manhwa/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "manhwabuddy.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # ── HTTP ─────────────────────────────────────────────────────────

    @retry_with_backoff()
    def _fetch_series_page(self, slug: str) -> str:
        url = f"https://manhwabuddy.com/manhwa/{slug}/"
        logger.debug(f"Fetching manhwabuddy series page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://manhwabuddy.com/"}
        )
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_reader_page(self, chapter_url: str) -> str:
        # ``chapter_url`` is absolute (constructed in get_chapters).
        logger.debug(f"Fetching manhwabuddy reader page: {chapter_url}")
        r = get_session().get(
            chapter_url,
            timeout=30,
            headers={"Referer": "https://manhwabuddy.com/"},
        )
        r.raise_for_status()
        return r.text

    # ── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _strip_title(raw: str) -> str:
        """
        ``<title>Read Water Overflow Manhwa [Latest Chapters] - ManhwaBuddy.COM</title>``
        → ``Water Overflow``. Falls back to the trimmed raw text when
        the expected pattern doesn't match (e.g. for chapters with
        non-English series names).
        """
        cleaned = unescape(raw).strip()
        m = re.match(
            r"^\s*Read\s+(.+?)\s+Manhwa\b.*$", cleaned, re.IGNORECASE
        )
        if m:
            return m.group(1).strip()
        # Strip the site-suffix at minimum.
        return re.sub(
            r"\s*-\s*ManhwaBuddy(\.COM)?\s*$", "", cleaned, flags=re.IGNORECASE
        )

    @staticmethod
    def _alts_from_description(desc: str) -> tuple[list[str], str]:
        """
        manhwabuddy puts alt titles slash-delimited at the start of the
        description, e.g. ``"물이 넘쳐요/Super Wet/Dripping Wet. Oh, crazy..!! …"``.
        Split off the first sentence-ish chunk that's all slash-separated
        titles, leave the rest as the actual synopsis.
        """
        text = unescape(desc).strip()
        # Heuristic: the leading alts segment has no full sentences in
        # it. Pick the run up to the first "." that ends a token longer
        # than 3 characters (so "U.S." inside titles doesn't break us).
        head, sep, tail = text.partition(". ")
        if sep and "/" in head and len(head) < 200:
            alts = [a.strip() for a in head.split("/") if a.strip()]
            return alts, tail.strip()
        return [], text

    def _parse_series_metadata(
        self, slug: str, html: str
    ) -> tuple[str, list[str], Optional[str], str, bool, Optional[str]]:
        """Return (title, alt_titles, cover_url, description, is_nsfw, status)."""
        title_m = _TITLE_RE.search(html)
        title = self._strip_title(title_m.group(1)) if title_m else slug

        desc_m = _META_DESC_RE.search(html)
        alts: list[str] = []
        description = ""
        if desc_m:
            alts, description = self._alts_from_description(desc_m.group(1))

        cover: Optional[str] = None
        og = _OG_IMAGE_RE.search(html)
        if og:
            cover = unescape(og.group(1)).strip() or None

        is_nsfw = bool(_ADULT_BODY_RE.search(html))

        status: Optional[str] = None
        status_m = _STATUS_RE.search(html)
        if status_m:
            status = unescape(status_m.group(1)).strip() or None

        return title, alts, cover, description, is_nsfw, status

    def _parse_chapters(
        self, slug: str, html: str
    ) -> list[tuple[str, str, str]]:
        """
        Return [(absolute_url, number_str, display_name), ...] in the
        order they appear on the page (newest first).
        """
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for href, label in _CHAPTER_ITEM_RE.findall(html):
            href = href.strip()
            if href in seen:
                continue
            seen.add(href)
            label = unescape(label).strip()
            # Prefer the visible label for chapter number; fall back to
            # parsing the URL.
            num_match = _CHAPTER_NUM_RE.search(label) or _CHAPTER_NUM_RE.search(href)
            if not num_match:
                logger.debug(f"manhwabuddy: skipping un-numbered chapter {href}")
                continue
            number = num_match.group(1)
            absolute = (
                href if href.startswith("http") else f"https://manhwabuddy.com{href}"
            )
            out.append((absolute, number, label))
        return out

    @staticmethod
    def _extract_reader_image_urls(html: str) -> list[str]:
        urls: list[str] = []
        for match in _READER_IMG_RE.findall(html):
            url = unescape(match).strip()
            if not url:
                continue
            # Skip site-chrome images (logos, app banners, popular-card
            # thumbnails). All real page images live under the
            # ``imgNN.manhwabuddy.com/chapters/...`` host pattern.
            if "/chapters/" not in url:
                continue
            urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_series_page(code)
        title, alts, cover, description, is_nsfw, status = self._parse_series_metadata(
            code, html
        )
        chapters = self._parse_chapters(code, html)
        latest = chapters[0][1] if chapters else None

        return MangaInfo(
            hash_id=code,
            title=title,
            alt_titles=alts,
            slug=code,
            manga_type="manhwa",
            poster_url=cover,
            original_language="ko",
            status=status,
            latest_chapter=latest,
            is_nsfw=is_nsfw,
            description=description,
            source=self.name,
            source_url=f"https://manhwabuddy.com/manhwa/{code}/",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_series_page(code)
        rows = self._parse_chapters(code, html)
        if not rows:
            raise RuntimeError(
                f"manhwabuddy: no chapters found on /manhwa/{code}/ — "
                f"layout may have changed"
            )

        # Page DOM lists newest-first; the pipeline wants oldest-first.
        # We also stash the absolute chapter URL in `volume` so the
        # downloader can re-fetch images after the GUI bridge's lossy
        # chapter-dict serialisation (per CLAUDE.md "volume = per-provider
        # stash field" convention used by toonily, manhwaread, comix…).
        chapters: list[Chapter] = []
        for absolute_url, number, label in reversed(rows):
            chapters.append(
                Chapter(
                    chapter_id=0,  # site doesn't expose a numeric chapter id
                    number=number,
                    title=None,  # label is just "Chapter N" — redundant
                    volume=absolute_url,
                )
            )
        return chapters

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        chapter_url = (chapter.volume or "").strip()
        if not chapter_url:
            raise RuntimeError(
                "manhwabuddy chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        html = self._fetch_reader_page(chapter_url)
        urls = self._extract_reader_image_urls(html)
        if not urls:
            raise RuntimeError(
                f"manhwabuddy: no images parsed from reader page {chapter_url}"
            )
        return urls
