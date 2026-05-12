"""
mangadistrict.com provider — Madara-theme WordPress NSFW-leaning
manhwa aggregator.

Same markup family as webtoonscan but with two important differences:

1. **No FlareSolverr needed.** The site is Cloudflare-fronted but the
   default ``get_session()`` (curl_cffi chrome120 impersonation) passes
   without a JS challenge. Plain HTTP path works end-to-end.
2. **Reader uses ``src``, not ``data-src``.** The Madara theme on this
   site ships images eagerly rather than lazy-loaded, so we read
   ``<img class="wp-manga-chapter-img" src="…">`` directly.

Site shape
~~~~~~~~~~

- Series page ``/series/<slug>/`` — chapters under
  ``<li class="wp-manga-chapter"><a href="…/chapter-N/">``, plus full
  Madara metadata (title in ``<div class="post-title"><h1>``, cover
  via ``og:image``, NSFW flag from the ``adult-content`` body class).
- Reader page ``/series/<slug>/chapter-N/`` — pages are
  ``<img id="image-N" class="wp-manga-chapter-img" src="https://cdn.mangadistrict.com/…">``.
  There's a decoy entry at ``id="image-99999"`` pointing at
  ``/assets/publication/media/…`` (some kind of site-chrome banner);
  we filter it out by URL prefix.

Image CDN ``cdn.mangadistrict.com`` accepts requests without a Referer
header in practice. We set ``image_referer = "https://mangadistrict.com/"``
defensively, matching the rest of our Madara providers.
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


_BASE = "https://mangadistrict.com"
_SLUG_RE = re.compile(r"/series/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    # ``<div class="post-title">`` may have sibling ``<span class=
    # "manga-title-badges">`` elements (Adult / Hot / etc. badges)
    # before the ``<h1>`` carrying the real title — match through
    # any of them with a non-greedy ``.*?``.
    r'<div\s+class="[^"]*post-title[^"]*"[^>]*>.*?<h1[^>]*>(.+?)</h1>',
    re.IGNORECASE | re.DOTALL,
)
_OG_TITLE_RE = re.compile(
    r'<meta\s+property="og:title"\s+content="([^"]+)"', re.IGNORECASE
)
_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
_OG_DESC_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]+)"', re.IGNORECASE
)
_META_DESC_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]+)"', re.IGNORECASE
)
_ADULT_BODY_RE = re.compile(r'<body[^>]*\badult-content\b', re.IGNORECASE)
_CHAPTER_LI_RE = re.compile(
    r'<li[^>]*class="[^"]*wp-manga-chapter[^"]*"[^>]*>\s*'
    r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE | re.DOTALL,
)
_CHAPTER_NUM_FROM_URL_RE = re.compile(
    r"/chapter-(\d+(?:[-.]\d+)?)", re.IGNORECASE
)
_CHAPTER_NUM_FROM_TEXT_RE = re.compile(
    r"chapter\s*(\d+(?:\.\d+)?)", re.IGNORECASE
)
# Reader page images. Madara on mangadistrict ships pages eagerly via
# ``src`` (not the lazy-loaded ``data-src`` you see on webtoonscan/
# manhwabuddy/manhwa18). Accept either to stay forward-compatible
# with theme tweaks.
_READER_IMG_RE = re.compile(
    r'<img[^>]+?(?:data-src|src)="([^"]+\.(?:jpe?g|png|webp|gif))"',
    re.IGNORECASE,
)
_READER_BODY_RE = re.compile(
    r'<div\s+class="reading-content[^"]*"[^>]*>(.+?)'
    r'(?:</div>\s*</div>\s*</div>|<div\s+class="entry-(?:footer|header))',
    re.IGNORECASE | re.DOTALL,
)


class MangadistrictProvider(Provider):
    """Provider for https://mangadistrict.com/ ."""

    name = "mangadistrict"
    label = "mangadistrict.com"
    domains = ("mangadistrict.com",)
    image_referer = "https://mangadistrict.com/"
    example_url = "https://mangadistrict.com/series/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "mangadistrict.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # ── HTTP ─────────────────────────────────────────────────────────

    @retry_with_backoff()
    def _fetch_html(self, path_or_url: str) -> str:
        url = (
            path_or_url
            if path_or_url.startswith("http")
            else f"{_BASE}{path_or_url}"
        )
        logger.debug(f"Fetching mangadistrict page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": f"{_BASE}/"}
        )
        r.raise_for_status()
        return r.text

    # ── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(s: str) -> str:
        return unescape(re.sub(r"<[^>]+>", "", s)).strip()

    def _parse_series_metadata(
        self, slug: str, html: str
    ) -> tuple[str, Optional[str], str, bool]:
        """Return (title, cover_url, description, is_nsfw)."""
        title_m = _TITLE_RE.search(html) or _OG_TITLE_RE.search(html)
        title = self._clean_text(title_m.group(1)) if title_m else slug
        # The og:title on this site ends with the literal hyphen-site
        # name (e.g. "X (Uncensored) - MANGA DISTRICT - Read Scan -
        # Manhwa"); strip the boilerplate so the library shows a clean
        # series name.
        title = re.sub(
            r"\s*[–\-]\s*MANGA DISTRICT[\s\S]*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        cover: Optional[str] = None
        og = _OG_IMAGE_RE.search(html)
        if og:
            cover = unescape(og.group(1)).strip() or None

        description = ""
        for rgx in (_OG_DESC_RE, _META_DESC_RE):
            m = rgx.search(html)
            if m:
                description = unescape(m.group(1)).strip()
                if description:
                    break

        is_nsfw = bool(_ADULT_BODY_RE.search(html))
        return title, cover, description, is_nsfw

    def _parse_chapters(self, html: str) -> list[tuple[str, str, str]]:
        """
        Return ``[(absolute_url, number_str, display_label), ...]`` in
        page order (Madara renders newest-first).
        """
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for href, label in _CHAPTER_LI_RE.findall(html):
            href = href.strip()
            label = self._clean_text(label)
            if href in seen:
                continue
            seen.add(href)
            absolute = href if href.startswith("http") else f"{_BASE}{href}"
            num_m = (
                _CHAPTER_NUM_FROM_URL_RE.search(absolute)
                or _CHAPTER_NUM_FROM_TEXT_RE.search(label)
            )
            if not num_m:
                logger.debug(f"mangadistrict: un-numbered chapter {href!r}, skipping")
                continue
            # "5-5" → "5.5" (Madara writes decimal chapters with a
            # hyphen in the URL).
            number = num_m.group(1).replace("-", ".")
            out.append((absolute, number, label))
        return out

    @staticmethod
    def _extract_reader_images(html: str) -> list[str]:
        # Scope to the reading container so sidebar thumbs and
        # related-series cards don't pollute the result.
        body = html
        body_m = _READER_BODY_RE.search(html)
        if body_m:
            body = body_m.group(1)

        urls: list[str] = []
        seen: set[str] = set()
        for match in _READER_IMG_RE.findall(body):
            url = unescape(match).strip()
            if not url:
                continue
            # Skip site-chrome / WordPress theme assets. The Madara
            # reader on this site mounts a decoy ``id="image-99999"``
            # pointing at /assets/publication/media/… as some kind of
            # default-placeholder banner; that path prefix uniquely
            # identifies non-page images.
            if "/wp-content/" in url or "/assets/publication/media/" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_html(f"/series/{code}/")
        title, cover, description, is_nsfw = self._parse_series_metadata(
            code, html
        )
        chapters = self._parse_chapters(html)
        latest = chapters[0][1] if chapters else None

        return MangaInfo(
            hash_id=code,
            title=title,
            slug=code,
            manga_type="manhwa",
            poster_url=cover,
            original_language="ko",
            status=None,
            latest_chapter=latest,
            is_nsfw=is_nsfw,
            description=description,
            source=self.name,
            source_url=f"{_BASE}/series/{code}/",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_html(f"/series/{code}/")
        rows = self._parse_chapters(html)
        if not rows:
            raise RuntimeError(
                f"mangadistrict: no chapters parsed on /series/{code}/ — "
                f"layout may have changed."
            )

        chapters: list[Chapter] = []
        # Reverse to oldest-first to match the rest of the pipeline.
        for absolute_url, number, _label in reversed(rows):
            chapters.append(
                Chapter(
                    chapter_id=0,
                    number=number,
                    title=None,
                    volume=absolute_url,
                )
            )
        return chapters

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        url = (chapter.volume or "").strip()
        if not url:
            raise RuntimeError(
                "mangadistrict chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        html = self._fetch_html(url)
        urls = self._extract_reader_images(html)
        if not urls:
            raise RuntimeError(
                f"mangadistrict: no images parsed from reader page {url}"
            )
        return urls
