"""
hentaifc.com provider.

Each gallery has two relevant pages:

- ``/e/{id}``      — landing page with title, alt name, page count,
  artists / parodies / tags (when present), and a thumbnail strip whose
  first item we use as the cover.
- ``/e/{id}/c0``   — reader page. Image URLs are not in the markup;
  they're encoded as a JS array of space-separated decimal char-codes
  (rotating variable name, decoded via ``String.fromCharCode``). We
  decode it in-process to recover the real CDN URLs.

A "gallery" maps to a single chapter in our model (same shape as
nhentai / hitomi).
"""

import re
from html import unescape
from typing import Optional, Tuple
from urllib.parse import urlparse

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


_GALLERY_ID_RE = re.compile(r"/e/(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*heading[^"]*"[^>]*>(.+?)</h1>', re.IGNORECASE | re.DOTALL
)
_THUMB_RE = re.compile(
    r'<img[^>]+data-src="(https?://[^"]+/\d+\.(?:jpg|jpeg|png|webp|gif))"',
    re.IGNORECASE,
)
_META_ROW_RE = re.compile(
    r'd-cell label">([^<]+)</div>\s*<div class="d-cell value">([\s\S]*?)</div>',
    re.IGNORECASE,
)
# Any `var X = [ '...', '...', ... ];` literal — we don't trust the name
# (it appears to rotate per request).
_ARRAY_RE = re.compile(
    r"var\s+([A-Za-z_]\w*)\s*=\s*(\[[\s\S]*?\])\s*;",
)
_ARRAY_ITEM_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


class HentaiFCProvider(Provider):
    """Provider for https://hentaifc.com/ ."""

    name = "hentaifc"
    label = "hentaifc.com"
    domains = ("hentaifc.com",)
    image_referer = "https://hentaifc.com/"
    example_url = "https://hentaifc.com/e/<id>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "hentaifc.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _GALLERY_ID_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find gallery id in URL: {url}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    @retry_with_backoff()
    def _fetch_gallery_page(self, code: str) -> str:
        url = f"https://hentaifc.com/e/{code}"
        logger.debug(f"Fetching hentaifc gallery page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://hentaifc.com/"}
        )
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_reader_page(self, code: str) -> str:
        url = f"https://hentaifc.com/e/{code}/c0"
        logger.debug(f"Fetching hentaifc reader page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": f"https://hentaifc.com/e/{code}"}
        )
        r.raise_for_status()
        return r.text

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _decode_charcodes(s: str) -> str:
        try:
            return "".join(chr(int(tok)) for tok in s.split() if tok)
        except ValueError:
            return ""

    def _extract_image_urls(self, reader_html: str) -> list[str]:
        """
        Find the encoded image-URL array on the reader page and decode it.

        The reader emits something like
        ``var ytaw=['104 116 116 …', '104 116 116 …', …];`` and a tiny
        JS function decodes each entry by ``String.fromCharCode``-ing
        the space-separated decimals. The variable name appears to
        rotate, so we scan every ``var X = [...]`` array literal in
        the page and accept the first one whose decoded entries look
        like absolute image URLs.
        """
        for arr_match in _ARRAY_RE.finditer(reader_html):
            items = _ARRAY_ITEM_RE.findall(arr_match.group(2))
            if len(items) < 2:
                continue
            first = self._decode_charcodes(items[0])
            if not first.startswith(("http://", "https://")):
                continue
            decoded = [self._decode_charcodes(it) for it in items]
            decoded = [u for u in decoded if u.startswith(("http://", "https://"))]
            if decoded:
                logger.debug(
                    f"hentaifc: decoded {len(decoded)} image URLs from "
                    f"`var {arr_match.group(1)}`"
                )
                return decoded
        raise RuntimeError(
            "Could not locate the encoded image-URL array on the reader page"
        )

    def _parse_metadata(
        self, html: str
    ) -> Tuple[str, list[str], int, Optional[str], list[str], list[str]]:
        """
        Return (title, alt_titles, num_pages, cover_url, artists, tags).
        Tags include parodies + plain tags (we don't need to distinguish
        them downstream).
        """
        title_m = _TITLE_RE.search(html)
        title = unescape(title_m.group(1).strip()) if title_m else "Unknown Gallery"
        title = re.sub(r"\s+", " ", title)

        # Sidebar metadata rows (label / value pairs).
        alt_titles: list[str] = []
        num_pages = 0
        for m in _META_ROW_RE.finditer(html):
            label = m.group(1).strip().rstrip(":").lower()
            raw_val = m.group(2)
            text = unescape(re.sub(r"<[^>]+>", " ", raw_val)).strip()
            text = re.sub(r"\s+", " ", text)
            if label.startswith("alt"):
                if text:
                    alt_titles.append(text)
            elif label == "pages":
                mnum = re.search(r"\d+", text)
                if mnum:
                    num_pages = int(mnum.group(0))

        # Cover = first thumbnail's src on the gallery page.
        cover_url: Optional[str] = None
        thumb = _THUMB_RE.search(html)
        if thumb:
            cover_url = thumb.group(1)
            # The site serves thumbnails over plain HTTP; upgrade so the
            # GUI's image cache doesn't reject them.
            if cover_url.startswith("http://"):
                cover_url = "https://" + cover_url[len("http://"):]

        # Artists / parodies / tags via /artist|parody|tag/ links.
        def _collect(kind: str) -> list[str]:
            out: list[str] = []
            for m in re.finditer(
                rf'href="https?://hentaifc\.com/{kind}/[^"]+"[^>]*>([^<]+)<',
                html,
            ):
                name = unescape(m.group(1)).strip()
                if name and name not in out:
                    out.append(name)
            return out

        artists = _collect("artist")
        tags = _collect("tag") + _collect("parody")

        return title, alt_titles, num_pages, cover_url, artists, tags

    # --- Provider interface ------------------------------------------

    def _build_manga_info(
        self, code: str, gallery_html: str, num_pages_fallback: int = 0
    ) -> MangaInfo:
        title, alts, num_pages, cover, artists, tags = self._parse_metadata(
            gallery_html
        )
        if not num_pages:
            num_pages = num_pages_fallback

        return MangaInfo(
            manga_id=int(code) if code.isdigit() else None,
            hash_id=code,
            title=title,
            alt_titles=alts,
            slug=code,
            manga_type="doujinshi",
            poster_url=cover,
            original_language="en",
            status="complete",
            final_chapter="1",
            latest_chapter="1",
            is_nsfw=True,
            description=(
                f"hentaifc gallery #{code}"
                + (f" ({num_pages} pages)." if num_pages else ".")
                + (f" Artists: {', '.join(artists)}." if artists else "")
            ),
            source=self.name,
            source_url=f"https://hentaifc.com/e/{code}",
            artists=artists,
            tags=tags,
            genres=tags,
        )

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        return self._build_manga_info(code, self._fetch_gallery_page(code))

    def get_chapters(self, code: str) -> list[Chapter]:
        gallery_html = self._fetch_gallery_page(code)
        reader_html = self._fetch_reader_page(code)
        image_urls = self._extract_image_urls(reader_html)
        manga = self._build_manga_info(code, gallery_html, len(image_urls))

        chapter = Chapter(
            chapter_id=int(code) if code.isdigit() else 0,
            number="1",
            title=manga.title,
            volume=None,
            votes=None,
            group_name=", ".join(manga.artists) if manga.artists else None,
            pages_count=len(image_urls),
            image_urls=image_urls,
        )
        return [chapter]

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        return self._extract_image_urls(
            self._fetch_reader_page(str(chapter.chapter_id))
        )
