"""
hentairead.com provider.

A "gallery" is a single chapter (same shape as nhentai / hitomi /
hentaifc). The gallery URL looks like
``https://hentairead.com/hentai/<slug>/``; we use the slug as the
canonical code.

Single round trip: the gallery page contains everything we need —

- Title (``<h1>`` inside ``div.manga-titles``) and alt titles
  (``<h2>`` immediately after; multi-language alts are pipe-delimited).
- Cover URL (``<meta property="og:image">``).
- Numeric gallery id (``data-clipboard-text="#NNNNNN"``).
- Artists / tags / parodies (``<a href=".../artist|tag|parody/...">``).
- Page count and **per-page preview thumbnails**, each emitted as
  ``<img alt="Page N" src="https://hencover.xyz/preview/<gid>/<cid>/hr_NNNN.jpg">``
  inside a ``<li class="chapter-image-item" data-page="N">``.

The full image lives at ``https://henread.xyz/<gid>/<cid>/hr_NNNN.jpg``
— same path minus the ``preview/`` segment, on a different host. We
verify the transformation by checking that the preview URL begins with
``hencover.xyz/preview/`` and only swap host + drop ``preview/`` when
it does (so any future CDN change just falls back to the preview URL).
"""

import re
from html import unescape
from typing import Optional, Tuple

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


_SLUG_RE = re.compile(r"/hentai/([^/?#]+)/?", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<div class="manga-titles[^"]*">\s*<h1[^>]*>(.+?)</h1>'
    r'(?:\s*<h2[^>]*>(.+?)</h2>)?',
    re.IGNORECASE | re.DOTALL,
)
_GALLERY_ID_RE = re.compile(r'data-clipboard-text="#(\d+)"')
_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
# Per-page preview thumb on the gallery page. We capture the page index
# (data-page) and the preview URL so we can both order pages correctly
# and derive the full-resolution URL.
_PAGE_THUMB_RE = re.compile(
    r'<li[^>]*class="[^"]*chapter-image-item[^"]*"[^>]*data-page="(\d+)"[^>]*>'
    r'\s*<a[^>]*>\s*<img[^>]+src="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_TAG_LINK_RE = re.compile(
    r'href="https?://hentairead\.com/(artist|tag|parody|character)/[^"]+"'
    r'[^>]*>\s*(?:<span[^>]*>)?\s*([^<]+?)\s*(?:</span>)?\s*<',
    re.IGNORECASE,
)
_PAGES_META_RE = re.compile(
    r'>Pages:</div>\s*<div>\s*<span[^>]*>\s*<span[^>]*>\s*(\d+)\s*</span>',
    re.IGNORECASE | re.DOTALL,
)


class HentaireadProvider(Provider):
    """Provider for https://hentairead.com/ ."""

    name = "hentairead"
    label = "hentairead.com"
    domains = ("hentairead.com",)
    image_referer = "https://hentairead.com/"
    example_url = "https://hentairead.com/hentai/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "hentairead.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find gallery slug in URL: {url}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    @retry_with_backoff()
    def _fetch_gallery_page(self, slug: str) -> str:
        url = f"https://hentairead.com/hentai/{slug}/"
        logger.debug(f"Fetching hentairead gallery page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://hentairead.com/"}
        )
        r.raise_for_status()
        return r.text

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _preview_to_full(url: str) -> str:
        """
        Transform a hencover.xyz preview URL into the full-resolution
        henread.xyz URL. Falls back to the input if the URL doesn't
        match the known preview pattern (so a future CDN change at
        worst yields the thumbnail rather than failing entirely).
        """
        prefix = "https://hencover.xyz/preview/"
        if url.startswith(prefix):
            return "https://henread.xyz/" + url[len(prefix):]
        # Some galleries serve the same path over plain HTTP.
        if url.startswith("http://hencover.xyz/preview/"):
            return "https://henread.xyz/" + url[len("http://hencover.xyz/preview/"):]
        return url

    def _extract_image_urls(self, html: str) -> list[str]:
        """Return full-resolution image URLs in page order."""
        pairs: list[Tuple[int, str]] = []
        for m in _PAGE_THUMB_RE.finditer(html):
            try:
                idx = int(m.group(1))
            except ValueError:
                continue
            preview = unescape(m.group(2)).strip()
            if not preview:
                continue
            pairs.append((idx, self._preview_to_full(preview)))
        if not pairs:
            raise RuntimeError(
                "Could not locate any per-page thumbnails on the gallery page; "
                "hentairead may have changed its layout."
            )
        pairs.sort(key=lambda p: p[0])
        return [u for _, u in pairs]

    def _parse_metadata(
        self, html: str
    ) -> Tuple[str, list[str], int, Optional[str], Optional[str], list[str], list[str]]:
        """
        Return (title, alt_titles, num_pages, cover_url, gallery_id,
        artists, tags). ``gallery_id`` is the numeric ``#NNNNNN``
        identifier shown on the page (string form), or None if absent.
        """
        title_m = _TITLE_RE.search(html)
        if title_m:
            title = unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
            title = re.sub(r"\s+", " ", title)
            alts_raw = title_m.group(2) or ""
        else:
            title = "Unknown Gallery"
            alts_raw = ""

        alt_titles: list[str] = []
        if alts_raw:
            cleaned = unescape(re.sub(r"<[^>]+>", "", alts_raw)).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            for piece in cleaned.split("|"):
                piece = piece.strip()
                if piece:
                    alt_titles.append(piece)

        cover_url: Optional[str] = None
        og = _OG_IMAGE_RE.search(html)
        if og:
            cover_url = og.group(1).strip() or None
            if cover_url and cover_url.startswith("http://"):
                cover_url = "https://" + cover_url[len("http://"):]

        gid_m = _GALLERY_ID_RE.search(html)
        gallery_id = gid_m.group(1) if gid_m else None

        num_pages = 0
        pages_m = _PAGES_META_RE.search(html)
        if pages_m:
            num_pages = int(pages_m.group(1))

        artists: list[str] = []
        tags: list[str] = []
        for kind, name in _TAG_LINK_RE.findall(html):
            name = unescape(name).strip()
            if not name:
                continue
            if kind.lower() == "artist":
                if name not in artists:
                    artists.append(name)
            else:
                if name not in tags:
                    tags.append(name)

        return title, alt_titles, num_pages, cover_url, gallery_id, artists, tags

    # --- Provider interface ------------------------------------------

    def _build_manga_info(
        self,
        slug: str,
        html: str,
        num_pages_fallback: int = 0,
    ) -> Tuple[MangaInfo, int]:
        title, alts, num_pages, cover, gid, artists, tags = self._parse_metadata(html)
        if not num_pages:
            num_pages = num_pages_fallback

        manga_id: Optional[int] = int(gid) if gid and gid.isdigit() else None

        info = MangaInfo(
            manga_id=manga_id,
            hash_id=gid or slug,
            title=title,
            alt_titles=alts,
            slug=slug,
            manga_type="doujinshi",
            poster_url=cover,
            original_language="en",
            status="complete",
            final_chapter="1",
            latest_chapter="1",
            is_nsfw=True,
            description=(
                f"hentairead gallery {('#' + gid) if gid else slug}"
                + (f" ({num_pages} pages)." if num_pages else ".")
                + (f" Artists: {', '.join(artists)}." if artists else "")
            ),
            source=self.name,
            source_url=f"https://hentairead.com/hentai/{slug}/",
            artists=artists,
            tags=tags,
            genres=tags,
        )
        return info, num_pages

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        info, _ = self._build_manga_info(code, self._fetch_gallery_page(code))
        return info

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_gallery_page(code)
        image_urls = self._extract_image_urls(html)
        info, _ = self._build_manga_info(code, html, len(image_urls))

        chapter = Chapter(
            chapter_id=info.manga_id or 0,
            number="1",
            title=info.title,
            volume=code,
            votes=None,
            group_name=", ".join(info.artists) if info.artists else None,
            pages_count=len(image_urls),
            image_urls=image_urls,
        )
        return [chapter]

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        # Fallback: re-fetch the gallery page using the slug we stashed
        # in `volume` at chapter-construction time.
        slug = chapter.volume or ""
        if not slug:
            raise RuntimeError(
                "hentairead chapter is missing both image_urls and the slug "
                "needed to re-fetch them."
            )
        return self._extract_image_urls(self._fetch_gallery_page(slug))
