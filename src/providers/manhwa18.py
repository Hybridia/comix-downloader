"""
manhwa18.com provider — NSFW-leaning Laravel-based manhwa site.

Friendly compared to most of our matrix: plain HTML, no JS rendering,
no AJAX, no obfuscation, no FlareSolverr round-trip. Cloudflare-fronted
but the default ``get_session()`` (curl_cffi chrome120 impersonation)
passes the bot check without any extra plumbing.

Site shape
~~~~~~~~~~

- Series page ``/manga/<slug>`` — embeds the full chapter list as
  ``<a href=".../chap-N-<id>" title="chap N"><li><div class="chapter-name">
  chap N</div><div class="chapter-time">VIEWS - DATE</div></li></a>``.
  Same chapter number can appear multiple times (different scanlation
  groups → different ``-<id>`` suffix). We surface every entry; the
  download bridge dedups by number for users who don't pick a scanlator.

- Reader page ``/manga/<slug>/chap-N-<id>`` — every page is a single
  ``<img class="lazy" data-src="https://cdn.manhwa18.com/f/files/<date>/<random>.jpg">``.
  ``data-src`` is the real URL; the visible ``src`` is blank until the
  lazy-load JS fires (we don't need to evaluate JS — the URL is right
  there in the attribute).

Metadata
~~~~~~~~

- Title: ``<title>`` → strip ``"Manga "`` prefix and ``" - MyManga"`` suffix.
- Cover: ``<meta property="og:image">``.
- Alt titles / description: not exposed in obvious markup; we leave
  alts empty and pull description from ``meta[name=description]``.

Image CDN ``cdn.manhwa18.com`` accepts requests without a Referer in
practice, but we set ``image_referer = "https://www.manhwa18.com/"``
defensively.
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


_BASE = "https://www.manhwa18.com"
_SLUG_RE = re.compile(r"/manga/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title>(.+?)</title>", re.IGNORECASE | re.DOTALL)
_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
_META_DESC_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]+)"', re.IGNORECASE
)
# `<a href="...chap-N-<id>" title="chap N"><li><div class="chapter-name">chap N</div>`
# (early chapters use bare /<num> instead of /chap-<num>-<id> — accept
# either by matching the URL tail as anything looking chapter-ish).
_CHAPTER_LINK_RE = re.compile(
    r'<a\s+href="([^"]+/manga/[^"]+/(?:chap-[^"/]+|\d+))"\s+title="([^"]+)"\s*>\s*'
    r'<li[^>]*>\s*<div[^>]*class="[^"]*chapter-name[^"]*"[^>]*>\s*([^<]+)\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
# `chap 145`, `chap 5.5`, `chap-12`, `chap 147 end` — first numeric run.
_CHAPTER_NUM_RE = re.compile(
    r"chap[\s-]*(\d+(?:\.\d+)?)", re.IGNORECASE
)
# Reader page images. Source order is reading order.
_READER_IMG_RE = re.compile(
    r'<img[^>]+class="[^"]*lazy[^"]*"[^>]+data-src="([^"]+)"',
    re.IGNORECASE,
)


class Manhwa18Provider(Provider):
    """Provider for https://www.manhwa18.com/ ."""

    name = "manhwa18"
    label = "manhwa18.com"
    domains = ("manhwa18.com", "www.manhwa18.com")
    image_referer = "https://www.manhwa18.com/"
    example_url = "https://www.manhwa18.com/manga/<slug>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "manhwa18.com" in (url or "").lower()

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
        logger.debug(f"Fetching manhwa18 page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": f"{_BASE}/"}
        )
        r.raise_for_status()
        return r.text

    # ── Parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _strip_title(raw: str) -> str:
        """
        ``" Manga Stepmother friends (magicmanscan) - MyManga"`` →
        ``"Stepmother friends (magicmanscan)"``. Falls back to a
        light cleanup when the expected wrapper isn't present.
        """
        cleaned = unescape(raw).strip()
        m = re.match(r"^\s*Manga\s+(.+?)\s*-\s*MyManga\s*$", cleaned, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Strip the site suffix at minimum.
        return re.sub(r"\s*-\s*MyManga\s*$", "", cleaned, flags=re.IGNORECASE)

    def _parse_series_metadata(
        self, slug: str, html: str
    ) -> tuple[str, Optional[str], str]:
        """Return (title, cover_url, description)."""
        title_m = _TITLE_RE.search(html)
        title = self._strip_title(title_m.group(1)) if title_m else slug

        cover: Optional[str] = None
        og = _OG_IMAGE_RE.search(html)
        if og:
            cover = unescape(og.group(1)).strip() or None

        description = ""
        desc_m = _META_DESC_RE.search(html)
        if desc_m:
            description = unescape(desc_m.group(1)).strip()

        return title, cover, description

    def _parse_chapters(self, html: str) -> list[tuple[str, str, str]]:
        """
        Return ``[(absolute_url, number_str, display_label), ...]`` in
        page order (newest-first).
        """
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for href, attr_title, label in _CHAPTER_LINK_RE.findall(html):
            href = href.strip()
            if href in seen:
                continue
            seen.add(href)
            label = unescape(label).strip()
            attr_title = unescape(attr_title).strip()
            absolute = href if href.startswith("http") else f"{_BASE}{href}"
            num_m = (
                _CHAPTER_NUM_RE.search(label)
                or _CHAPTER_NUM_RE.search(attr_title)
                or _CHAPTER_NUM_RE.search(href)
            )
            if not num_m:
                logger.debug(f"manhwa18: un-numbered chapter {href!r}, skipping")
                continue
            number = num_m.group(1)
            out.append((absolute, number, label))
        return out

    @staticmethod
    def _extract_reader_images(html: str) -> list[str]:
        """
        Extract reader page images. Source order = reading order.

        The CDN host varies by chapter age — older chapters live on
        ``cdn.manhwa18.com``, mid-2022+ chapters on ``cdn.pornwa.us``
        (with an occasional ``//`` typo in the path, which HTTP clients
        normalise), recent ones on ``cdn.pornwa.club``. We don't filter
        by host — every ``<img class="…lazy…" data-src="…">`` inside
        the reader is a page image, and there are no decoy lazy-loaded
        chrome elements on the site.
        """
        urls: list[str] = []
        seen: set[str] = set()
        for src in _READER_IMG_RE.findall(html):
            url = unescape(src).strip()
            if not url or not url.startswith("http"):
                continue
            # Collapse accidental ``//`` in the path (cdn.pornwa.us
            # serves some chapters with that typo). Don't touch the
            # `://` after the scheme.
            scheme, _, rest = url.partition("://")
            rest = re.sub(r"/{2,}", "/", rest)
            url = f"{scheme}://{rest}" if scheme else url
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_html(f"/manga/{code}")
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
            is_nsfw=True,  # site explicitly hosts 18+ content
            description=description,
            source=self.name,
            source_url=f"{_BASE}/manga/{code}",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_html(f"/manga/{code}")
        rows = self._parse_chapters(html)
        if not rows:
            raise RuntimeError(
                f"manhwa18: no chapters parsed on /manga/{code} — "
                f"layout may have changed."
            )

        chapters: list[Chapter] = []
        # DOM order is newest-first; pipeline wants oldest-first.
        for absolute_url, number, _label in reversed(rows):
            chapters.append(
                Chapter(
                    chapter_id=0,  # site doesn't expose a stable numeric id we control
                    number=number,
                    title=None,
                    # Stash the reader URL — same convention as
                    # toonily / manhwabuddy / manhwaread / comix.
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
                "manhwa18 chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        html = self._fetch_html(url)
        urls = self._extract_reader_images(html)
        if not urls:
            raise RuntimeError(
                f"manhwa18: no images parsed from reader page {url}"
            )
        return urls
