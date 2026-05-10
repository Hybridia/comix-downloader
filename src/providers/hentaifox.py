"""
hentaifox.com provider.

Each gallery is a single chapter (same shape as nhentai / hitomi /
hentaifc / hentairead). Two pages are fetched per gallery:

- ``/gallery/<id>/`` — top-level metadata: title, cover, tag buckets
  (tags / languages / categories / artists / parodies / characters /
  groups), and a set of hidden form inputs that give us everything we
  need to compute image URLs:

      <input id="load_id"  value="3918979" />   image-dir id
      <input id="load_dir" value="004"     />   image-dir prefix

  Combined with the host taken from any thumbnail (``i3.hentaifox.com``
  in this gallery), the canonical image URL is
  ``https://<host>/<load_dir>/<load_id>/<N>.<ext>``.

- ``/g/<id>/1/`` — the reader. Carries an inline
  ``var g_th = $.parseJSON('{"1":"w,1280,1790", ...}')`` whose key is
  the 1-based page index and whose value's first letter encodes the
  extension (``j``=jpg, ``p``=png, ``g``=gif, ``w``=webp — same
  convention nhentai uses). We only need the *first* reader page
  because g_th lists every page in the gallery.

Two HTTP calls per ``get_chapters``; one per ``get_manga_info``.
"""

import json
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


_GALLERY_ID_RE = re.compile(r"/gallery/(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<div class="info">\s*<h1[^>]*>(.+?)</h1>', re.IGNORECASE | re.DOTALL
)
_COVER_RE = re.compile(
    r'<div class="cover">\s*<img[^>]+src="([^"]+)"', re.IGNORECASE | re.DOTALL
)
_LOAD_ID_RE = re.compile(
    r'id="load_id"\s+value="([^"]+)"', re.IGNORECASE
)
_LOAD_DIR_RE = re.compile(
    r'id="load_dir"\s+value="([^"]+)"', re.IGNORECASE
)
_PAGES_RE = re.compile(
    r'<span class="i_text pages">\s*Pages:\s*(\d+)\s*</span>', re.IGNORECASE
)
_THUMB_HOST_RE = re.compile(
    r'data-src="(https?://[^"/]+/[A-Za-z0-9]+/\d+/[^"]+)"', re.IGNORECASE
)
# Each bucket is its own ``<ul class="<bucket>">…</ul>`` immediately
# under ``<div class="info">``. Anchoring on the UL class instead of
# scanning every link in the page keeps the related-gallery cards
# (which echo their own category labels) from polluting the list.
_TAG_UL_RE = re.compile(
    r'<ul class="([a-z]+)">(.*?)</ul>', re.IGNORECASE | re.DOTALL
)
_TAG_NAME_IN_UL_RE = re.compile(
    r"<a [^>]*class=['\"]tag_btn[^'\"]*['\"][^>]*>\s*([^<]+?)\s*(?:<|$)",
    re.IGNORECASE,
)
_GTH_RE = re.compile(
    r"var\s+g_th\s*=\s*\$\.parseJSON\(\s*'(\{.*?\})'\s*\)", re.IGNORECASE | re.DOTALL
)

# letter → file extension. Keys mirror nhentai's convention.
_EXT_BY_LETTER = {"j": "jpg", "p": "png", "g": "gif", "w": "webp", "b": "bmp"}

# UL class names we treat as tag-style metadata vs artist-style. Each
# UL on hentaifox is named with the plural slug for its kind. Anything
# else from the link sweep is ignored to keep noise out of the metadata.
_TAG_BUCKETS = {"tags", "parodies", "characters", "groups", "categories", "languages"}
_ARTIST_BUCKETS = {"artists"}


class HentaifoxProvider(Provider):
    """Provider for https://hentaifox.com/ ."""

    name = "hentaifox"
    label = "hentaifox.com"
    domains = ("hentaifox.com",)
    image_referer = "https://hentaifox.com/"
    example_url = "https://hentaifox.com/gallery/<id>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "hentaifox.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _GALLERY_ID_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find gallery id in URL: {url}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    @retry_with_backoff()
    def _fetch_gallery_page(self, code: str) -> str:
        url = f"https://hentaifox.com/gallery/{code}/"
        logger.debug(f"Fetching hentaifox gallery page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://hentaifox.com/"}
        )
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_reader_page(self, code: str, page: int = 1) -> str:
        url = f"https://hentaifox.com/g/{code}/{page}/"
        logger.debug(f"Fetching hentaifox reader page: {url}")
        r = get_session().get(
            url, timeout=30,
            headers={"Referer": f"https://hentaifox.com/gallery/{code}/"},
        )
        r.raise_for_status()
        return r.text

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _host_load_from_url(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Pull (host, load_dir, load_id) from a thumbnail / cover URL like
        ``https://i3.hentaifox.com/004/3918979/1t.jpg``. Returns
        ``(None, None, None)`` if the URL doesn't match the expected
        ``<host>/<dir>/<id>/<file>`` shape.
        """
        try:
            p = urlparse(url)
            parts = [seg for seg in (p.path or "").split("/") if seg]
            if len(parts) >= 3 and p.netloc:
                return p.netloc, parts[0], parts[1]
        except Exception:
            pass
        return None, None, None

    def _parse_metadata(self, html: str) -> dict:
        """
        Extract everything we can from the gallery page HTML. Returns a
        dict — callers pluck what they need so a missing field never
        forces a None-check at every call site.
        """
        out: dict = {
            "title": "Unknown Gallery",
            "cover_url": None,
            "load_id": None,
            "load_dir": None,
            "host": None,
            "num_pages": 0,
            "artists": [],
            "tags": [],
        }

        title_m = _TITLE_RE.search(html)
        if title_m:
            out["title"] = re.sub(
                r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
            )

        cover_m = _COVER_RE.search(html)
        if cover_m:
            out["cover_url"] = cover_m.group(1).strip()

        load_id_m = _LOAD_ID_RE.search(html)
        if load_id_m:
            out["load_id"] = load_id_m.group(1).strip()

        load_dir_m = _LOAD_DIR_RE.search(html)
        if load_dir_m:
            out["load_dir"] = load_dir_m.group(1).strip()

        pages_m = _PAGES_RE.search(html)
        if pages_m:
            out["num_pages"] = int(pages_m.group(1))

        # Host needs to come from a real thumbnail — hentaifox shards
        # across i.hentaifox.com, i2.hentaifox.com, i3.hentaifox.com,
        # etc., and the choice is per-gallery not per-deploy.
        thumb_m = _THUMB_HOST_RE.search(html)
        if thumb_m:
            host, ldir, lid = self._host_load_from_url(thumb_m.group(1))
            if host:
                out["host"] = host
            # Fall back to the thumbnail-derived dir/id when the hidden
            # inputs aren't present (e.g. layout changes).
            if ldir and not out["load_dir"]:
                out["load_dir"] = ldir
            if lid and not out["load_id"]:
                out["load_id"] = lid

        # Bucket every tag_btn link by the UL class it lives under.
        # Case-insensitive de-dupe within a bucket so the rare gallery
        # that lists "Doujinshi" and "doujinshi" doesn't double up.
        seen_tag: set[str] = set()
        seen_artist: set[str] = set()
        for ul_class, ul_inner in _TAG_UL_RE.findall(html):
            ul_class_l = ul_class.lower()
            if ul_class_l not in _TAG_BUCKETS and ul_class_l not in _ARTIST_BUCKETS:
                continue
            for name_m in _TAG_NAME_IN_UL_RE.findall(ul_inner):
                name = unescape(name_m).strip()
                if not name:
                    continue
                key = name.casefold()
                if ul_class_l in _ARTIST_BUCKETS:
                    if key not in seen_artist:
                        out["artists"].append(name)
                        seen_artist.add(key)
                else:
                    if key not in seen_tag:
                        out["tags"].append(name)
                        seen_tag.add(key)

        return out

    @staticmethod
    def _parse_gth(reader_html: str) -> dict[int, str]:
        """
        Parse the ``g_th`` JSON blob into ``{page_index: extension}``.
        Returns an empty dict if the blob is missing or malformed —
        callers default to ``webp`` and let the image downloader's
        extension-fallback handle the rest.
        """
        m = _GTH_RE.search(reader_html)
        if not m:
            return {}
        try:
            # The JSON lives inside a single-quoted JS string literal.
            # The values themselves are double-quoted JSON, so no
            # unescape gymnastics needed.
            parsed = json.loads(m.group(1))
        except json.JSONDecodeError:
            return {}
        out: dict[int, str] = {}
        for k, v in parsed.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            if not isinstance(v, str) or not v:
                continue
            letter = v[0].lower()
            ext = _EXT_BY_LETTER.get(letter, "webp")
            out[idx] = ext
        return out

    # --- Provider interface ------------------------------------------

    def _build_manga_info(
        self, code: str, meta: dict, num_pages_fallback: int = 0
    ) -> MangaInfo:
        num_pages = meta.get("num_pages") or num_pages_fallback
        artists = meta.get("artists") or []
        tags = meta.get("tags") or []
        cover = meta.get("cover_url")
        if cover and cover.startswith("http://"):
            cover = "https://" + cover[len("http://"):]

        return MangaInfo(
            manga_id=int(code) if code.isdigit() else None,
            hash_id=code,
            title=meta.get("title", "Unknown Gallery"),
            alt_titles=[],
            slug=code,
            manga_type="doujinshi",
            poster_url=cover,
            original_language="en",
            status="complete",
            final_chapter="1",
            latest_chapter="1",
            is_nsfw=True,
            description=(
                f"hentaifox gallery #{code}"
                + (f" ({num_pages} pages)." if num_pages else ".")
                + (f" Artists: {', '.join(artists)}." if artists else "")
            ),
            source=self.name,
            source_url=f"https://hentaifox.com/gallery/{code}/",
            artists=artists,
            tags=tags,
            genres=tags,
        )

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        meta = self._parse_metadata(self._fetch_gallery_page(code))
        return self._build_manga_info(code, meta)

    def _build_image_urls(self, meta: dict, gth: dict[int, str]) -> list[str]:
        host = meta.get("host")
        load_dir = meta.get("load_dir")
        load_id = meta.get("load_id")
        num_pages = meta.get("num_pages") or 0
        if not (host and load_dir and load_id):
            raise RuntimeError(
                "hentaifox: could not determine image-dir parameters "
                "(load_id / load_dir / host) from the gallery page."
            )
        if not num_pages and gth:
            num_pages = max(gth.keys())
        if num_pages <= 0:
            raise RuntimeError(
                "hentaifox: gallery reports zero pages; the layout may have changed."
            )
        return [
            f"https://{host}/{load_dir}/{load_id}/{i}.{gth.get(i, 'webp')}"
            for i in range(1, num_pages + 1)
        ]

    def get_chapters(self, code: str) -> list[Chapter]:
        gallery_html = self._fetch_gallery_page(code)
        meta = self._parse_metadata(gallery_html)
        try:
            reader_html = self._fetch_reader_page(code, 1)
            gth = self._parse_gth(reader_html)
        except Exception as exc:
            logger.warning(
                "hentaifox: could not fetch g_th from reader page (%s); "
                "defaulting all pages to .webp", exc,
            )
            gth = {}

        image_urls = self._build_image_urls(meta, gth)
        manga = self._build_manga_info(code, meta, len(image_urls))

        chapter = Chapter(
            chapter_id=int(code) if code.isdigit() else 0,
            number="1",
            title=manga.title,
            volume=code,
            votes=None,
            group_name=", ".join(manga.artists) if manga.artists else None,
            pages_count=len(image_urls),
            image_urls=image_urls,
        )
        return [chapter]

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        # Fallback: the GUI's lossy chapter-dict serialization stashes
        # the gallery code in `volume`.
        code = chapter.volume or str(chapter.chapter_id or "")
        if not code:
            raise RuntimeError(
                "hentaifox chapter is missing both image_urls and the "
                "gallery code needed to re-fetch them."
            )
        gallery_html = self._fetch_gallery_page(code)
        meta = self._parse_metadata(gallery_html)
        try:
            gth = self._parse_gth(self._fetch_reader_page(code, 1))
        except Exception:
            gth = {}
        return self._build_image_urls(meta, gth)
