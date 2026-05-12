"""
webtoonscan.com provider — Madara-themed WordPress manhwa aggregator
fronted by aggressive Cloudflare protection.

**Cloudflare requires FlareSolverr.** curl_cffi (every browser
impersonation we have) fails the "Just a moment…" JS challenge with a
permanent HTTP 403, and Playwright's bundled Chromium — even with
stealth patches (``--disable-blink-features=AutomationControlled``,
``navigator.webdriver`` spoofing, viewport + locale + timezone) sits
on the challenge indefinitely without ever minting ``cf_clearance``.
The site fingerprints headless browsers more aggressively than
mangafire.to does. So we explicitly ``force_flare=True`` on every
fetch and let :class:`SessionManager` route through FlareSolverr.

To use this provider the user MUST have FlareSolverr running on
``http://localhost:8191/v1`` (configurable in ``config.json`` →
``flaresolverr_url``). Any FlareSolverr deployment works — binary
release, Docker image, npm install — they all expose the same REST
API.

Pipeline
--------

The site uses a vanilla Madara theme — same markup family as toonily,
manhwaread, and the dozen other WordPress-manga sites:

- Series page ``/manhwa/<slug>/`` — embeds title, cover (``og:image``
  is the simplest source), description, and the full chapter list as
  ``<li class="wp-manga-chapter"><a href=".../chapter-N/">…</a>``.
- Reader page ``/manhwa/<slug>/chapter-N/`` — every page is a
  ``<img class="wp-manga-chapter-img"`` with the real URL in
  ``data-src`` (lazy-loader populates ``src`` on scroll). Some
  installs use ``id="image-N"`` instead; we accept either.

Image CDN: looks like ``cdn.webtoonscan.com`` or similar — set
``image_referer = "https://webtoonscan.com/"`` defensively. If the
CDN turns out to NOT be CF-protected, image downloads can use the
default rate-limited session without FlareSolverr.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Optional

from .base import Provider
from ..core.models import Chapter, MangaInfo
from ..utils.logger import get_logger
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session

logger = get_logger(__name__)


_BASE = "https://webtoonscan.com"
_SLUG_RE = re.compile(r"/manhwa/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<div\s+class="post-title[^"]*"[^>]*>\s*<h1[^>]*>(.+?)</h1>',
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
# Madara chapter list. The wrapper is `<li class="wp-manga-chapter ...">
# <a href="https://.../manhwa/<slug>/chapter-N/">chapter N</a></li>`.
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
# Reader page images. The Madara reader puts pages inside
# `<div class="page-break no-gaps">` wrappers. We prefer `data-src`
# (set by the lazy-loader before scroll fires) over `src` (which can
# be a 1×1 placeholder). Accept either; the chapter downloader will
# error out cleanly if we end up with placeholder URLs.
_READER_IMG_RE = re.compile(
    r'<img[^>]+?(?:data-src|src)="([^"]+\.(?:jpe?g|png|webp|gif))"',
    re.IGNORECASE,
)
# Pull only images inside the reading container (avoid sidebar
# thumbnails). Madara wraps with `<div class="reading-content">`.
_READER_BODY_RE = re.compile(
    r'<div\s+class="reading-content[^"]*"[^>]*>(.+?)(?:</div>\s*</div>\s*</div>|<div\s+class="entry-(?:footer|header))',
    re.IGNORECASE | re.DOTALL,
)


class WebtoonscanProvider(Provider):
    """Provider for https://webtoonscan.com/ ."""

    name = "webtoonscan"
    label = "webtoonscan.com"
    domains = ("webtoonscan.com",)
    image_referer = "https://webtoonscan.com/"
    example_url = "https://webtoonscan.com/manhwa/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "webtoonscan.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # ── HTTP (FlareSolverr is mandatory; see module docstring) ───────

    @retry_with_backoff()
    def _fetch_html(self, path_or_url: str) -> str:
        url = (
            path_or_url
            if path_or_url.startswith("http")
            else f"{_BASE}{path_or_url}"
        )
        logger.debug(f"Fetching webtoonscan HTML: {url}")
        r = get_session().get(
            url,
            timeout=90,  # FS round-trips add ~5-15s on top of the bare fetch
            force_flare=True,
            headers={"Referer": f"{_BASE}/"},
        )
        r.raise_for_status()
        if "Just a moment" in r.text[:1000] or "Attention Required" in r.text[:1000]:
            raise RuntimeError(
                "webtoonscan: got a Cloudflare challenge page even after "
                "the FlareSolverr round-trip — is FlareSolverr actually "
                f"running at {get_session().flaresolverr_url}? "
                "Start it the same way you do for mangafire."
            )
        return r.text

    # ── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(s: str) -> str:
        return unescape(re.sub(r"<[^>]+>", "", s)).strip()

    def _parse_series_metadata(
        self, slug: str, html: str
    ) -> tuple[str, Optional[str], str]:
        """Return (title, cover_url, description)."""
        title_m = _TITLE_RE.search(html) or _OG_TITLE_RE.search(html)
        title = self._clean_text(title_m.group(1)) if title_m else slug

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

        return title, cover, description

    def _parse_chapters(self, html: str) -> list[tuple[str, str, str]]:
        """
        Return [(absolute_url, number_str, display_label), …] in page
        order (Madara renders newest-first).
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
            num_m = _CHAPTER_NUM_FROM_URL_RE.search(absolute) or _CHAPTER_NUM_FROM_TEXT_RE.search(label)
            if not num_m:
                logger.debug(f"webtoonscan: un-numbered chapter {href!r}, skipping")
                continue
            # Some series have "chapter-5-5" for 5.5; normalise.
            number = num_m.group(1).replace("-", ".")
            out.append((absolute, number, label))
        return out

    def _extract_reader_images(self, html: str) -> list[str]:
        # Narrow to the reading container if we can find it — keeps
        # sidebar thumbs / recommendation cards out of the result.
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
            # Skip site-chrome / 1×1 placeholders. Real pages live on a
            # CDN; chrome lives under /wp-content/.
            if "/wp-content/themes/" in url or "/wp-content/plugins/" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_html(f"/manhwa/{code}/")
        title, cover, description = self._parse_series_metadata(code, html)
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
            description=description,
            source=self.name,
            source_url=f"{_BASE}/manhwa/{code}/",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_html(f"/manhwa/{code}/")
        rows = self._parse_chapters(html)
        if not rows:
            raise RuntimeError(
                f"webtoonscan: no chapters parsed on /manhwa/{code}/ — "
                f"layout may have changed, or the Madara selectors need "
                f"adjusting. Run scripts/webtoonscan_test.py for details."
            )
        chapters: list[Chapter] = []
        # Reverse to give the pipeline oldest-first order.
        for absolute_url, number, _label in reversed(rows):
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
        url = (chapter.volume or "").strip()
        if not url:
            raise RuntimeError(
                "webtoonscan chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        html = self._fetch_html(url)
        urls = self._extract_reader_images(html)
        if not urls:
            raise RuntimeError(
                f"webtoonscan: no images parsed from reader page {url}"
            )
        return urls
