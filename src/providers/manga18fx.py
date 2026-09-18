"""
manga18fx.com provider — Madara-derived WordPress NSFW manhwa
aggregator. Plain server-rendered HTML; no Cloudflare challenge, no
auth, no FlareSolverr/Playwright. Default ``get_session()`` (curl_cffi
chrome120) sails through.

Despite the similar name this is unrelated to ``manhwa18.com`` /
``manhwa18.net`` — different operator, different markup.

Site shape
~~~~~~~~~~

- Series page ``/manga/<slug>`` — Madara summary sidebar (title in
  ``<div class="post-title"><h1>``, cover via ``og:image``, status +
  alternative names in ``summary-heading``/``summary-content`` blocks).
  The chapter list does NOT use the stock ``<li class="wp-manga-chapter">``
  markup; chapters are bare ``<a class="chapter-name … mycover"
  href="/manga/<slug>/chapter-N">`` anchors, newest-first.
- Reader page ``/manga/<slug>/chapter-N`` — pages are
  ``<img class="loading pN" data-src="https://imgNN.manga18fx.com/uploads/<id>/<ch>/<page>-<key>.jpg">``.
  Every real page URL lives under ``/uploads/``; the related-manga
  cards at the bottom of the page use ``/webtoon/`` and site chrome
  uses ``/images/``, so a ``/uploads/`` path filter isolates the
  chapter cleanly.

Image CDN ``imgNN.manga18fx.com`` serves without a Referer header in
practice. We set ``image_referer = "https://manga18fx.com/"``
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


_BASE = "https://manga18fx.com"
_SLUG_RE = re.compile(r"/manga/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
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


def _summary_block_re(heading: str) -> re.Pattern:
    """
    Build a regex for a Madara summary row keyed on its ``<h5>`` heading
    label (e.g. "Status", "Alternative"). The value div may carry inline
    styles (``style="text-align: right"`` on this site), so match
    ``[^>]*`` after the class.
    """
    return re.compile(
        r'<div[^>]*class="[^"]*summary-heading[^"]*"[^>]*>\s*'
        r'<h5[^>]*>\s*' + heading + r':?\s*</h5>\s*</div>\s*'
        r'<div[^>]*class="[^"]*summary-content[^"]*"[^>]*>\s*(.+?)\s*</div>',
        re.IGNORECASE | re.DOTALL,
    )


_STATUS_RE = _summary_block_re("Status")
_ALT_RE = _summary_block_re("Alternative")
# Chapters: bare anchors with the ``chapter-name`` class, newest-first.
_CHAPTER_RE = re.compile(
    r'<a\s+class="chapter-name[^"]*"\s+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
_CHAPTER_NUM_FROM_URL_RE = re.compile(
    r"/chapter-(\d+(?:[-.]\d+)?)", re.IGNORECASE
)
_CHAPTER_NUM_FROM_TEXT_RE = re.compile(
    r"chapter\s*(\d+(?:\.\d+)?)", re.IGNORECASE
)
# Reader page images. Pages are lazy-loaded via ``data-src`` (``src``
# mirrors it on first paint); accept either. Every real page URL lives
# under ``/uploads/`` — the ``/uploads/`` filter in _extract_reader_images
# is what isolates the chapter from decoys and site chrome.
_READER_IMG_RE = re.compile(
    r'<img[^>]+?(?:data-src|src)="([^"]+\.(?:jpe?g|png|webp|gif))"',
    re.IGNORECASE,
)


class Manga18fxProvider(Provider):
    """Provider for https://manga18fx.com/ ."""

    name = "manga18fx"
    label = "manga18fx.com"
    domains = ("manga18fx.com",)
    image_referer = "https://manga18fx.com/"
    example_url = "https://manga18fx.com/manga/<slug>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "manga18fx.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find manga slug in URL: {url}")
        return m.group(1)

    # ── HTTP ─────────────────────────────────────────────────────────

    @retry_with_backoff()
    def _fetch_html(self, path_or_url: str) -> str:
        url = (
            path_or_url
            if path_or_url.startswith("http")
            else f"{_BASE}{path_or_url}"
        )
        logger.debug(f"Fetching manga18fx page: {url}")
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
    ) -> tuple[str, Optional[str], str, list[str], Optional[str]]:
        """Return (title, cover_url, description, alt_titles, status)."""
        title_m = _TITLE_RE.search(html) or _OG_TITLE_RE.search(html)
        title = self._clean_text(title_m.group(1)) if title_m else slug
        # og:title fallback carries "Read <name> Manhwa - Manga18fx"
        # boilerplate; strip it so the library shows a clean name.
        title = re.sub(r"^\s*Read\s+", "", title, flags=re.IGNORECASE)
        title = re.sub(
            r"\s*[–\-]\s*Manga18fx\s*$", "", title, flags=re.IGNORECASE
        )
        title = re.sub(
            r"\s+(?:Manhwa|Manga|Webtoon)\s*$", "", title, flags=re.IGNORECASE
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

        alt_titles: list[str] = []
        alt_m = _ALT_RE.search(html)
        if alt_m:
            raw = self._clean_text(alt_m.group(1))
            alt_titles = [
                a.strip()
                for a in re.split(r"\s*[/,]\s*", raw)
                if a.strip()
            ]

        status: Optional[str] = None
        status_m = _STATUS_RE.search(html)
        if status_m:
            status = self._clean_text(status_m.group(1)) or None

        return title, cover, description, alt_titles, status

    def _parse_chapters(self, html: str) -> list[tuple[str, str, str]]:
        """
        Return ``[(absolute_url, number_str, display_label), ...]`` in
        page order (newest-first, as the site renders them).
        """
        out: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for href, label in _CHAPTER_RE.findall(html):
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
                logger.debug(f"manga18fx: un-numbered chapter {href!r}, skipping")
                continue
            # "176-5" → "176.5" (decimal chapters use a hyphen in the URL).
            number = num_m.group(1).replace("-", ".")
            out.append((absolute, number, label))
        return out

    @staticmethod
    def _extract_reader_images(html: str) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for match in _READER_IMG_RE.findall(html):
            url = unescape(match).strip()
            # Real chapter pages all live under /uploads/. Related-manga
            # cards use /webtoon/ and site chrome uses /images/.
            if "/uploads/" not in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_html(f"/manga/{code}")
        title, cover, description, alt_titles, status = (
            self._parse_series_metadata(code, html)
        )
        chapters = self._parse_chapters(html)
        latest = chapters[0][1] if chapters else None

        return MangaInfo(
            hash_id=code,
            title=title,
            slug=code,
            alt_titles=alt_titles,
            manga_type="manhwa",
            poster_url=cover,
            original_language="ko",
            status=status,
            latest_chapter=latest,
            is_nsfw=True,
            description=description,
            source=self.name,
            source_url=f"{_BASE}/manga/{code}",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_html(f"/manga/{code}")
        rows = self._parse_chapters(html)
        if not rows:
            raise RuntimeError(
                f"manga18fx: no chapters parsed on /manga/{code} — "
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
                "manga18fx chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        html = self._fetch_html(url)
        urls = self._extract_reader_images(html)
        if not urls:
            raise RuntimeError(
                f"manga18fx: no images parsed from reader page {url}"
            )
        return urls
