"""
manhwaread.com provider — multi-chapter manhwa site running the same
WordPress "mangomic" theme as hentairead.com (so the markup is very
similar, just configured for chapters instead of single galleries).

Pipeline:

- ``/manhwa/<slug>/`` — series page. Gives title, alt titles, cover,
  numeric ``manga_id`` (from the bookmark button's ``data-manga-id``),
  tags / authors / artists, and the full chapter list as
  ``<a class="chapter-item" href="/manhwa/<slug>/chapter-NN/"
  data-id="<chapter_id>">…<span class="chapter-item__name">Chapter NN
  </span>…</a>``.
- ``/manhwa/<slug>/chapter-NN/`` — reader. Carries an inline
  ``var chapterData = {"data":"<base64>","base":"https://manread.xyz/<manga_id>"};``.
  ``data`` is base64-encoded JSON: a list of ``{"src":"<chapter_id>/mr_NNN.jpg","w":...,"h":...}``.
  Image URLs are ``<base>/<src>``.

  The base64 + JSON shape is the mangomic theme's standard chapter
  payload; if the site adds a sibling field (e.g. for thumbs), we'll
  still pick the canonical one because we read the literal
  ``chapterData`` assignment.

The image CDN (``manread.xyz``) does *not* require a Referer header
in practice, but we set ``image_referer = "https://manhwaread.com/"``
defensively — same as the other mangomic-themed sites.
"""

import base64
import json
import re
from html import unescape
from typing import Optional

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


_SLUG_RE = re.compile(r"/manhwa/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<div class="manga-titles[^"]*">\s*<h1[^>]*>(.+?)</h1>'
    r'(?:\s*<h2[^>]*>(.+?)</h2>)?',
    re.IGNORECASE | re.DOTALL,
)
_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
_OG_DESC_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]+)"', re.IGNORECASE
)
_MANGA_ID_RE = re.compile(r'data-manga-id="(\d+)"', re.IGNORECASE)
# Each chapter is `<a href="/manhwa/<slug>/chapter-NN/" class="chapter-item" data-id="N">
#   <span class="flex flex-col"><span class="text-gray-50 chapter-item__name">Chapter NN</span></span>
#   <span class="chapter-item__date ml-auto text-gray-500 text-sm">DD/MM/YYYY</span>
# </a>`. We capture the URL, the data-id, and the visible chapter name.
_CHAPTER_ITEM_RE = re.compile(
    r'<a[^>]+href="([^"]+/chapter-[^"/]+/?)"[^>]*\bclass="chapter-item"[^>]*'
    r'(?:\s+data-id="(\d+)")?[^>]*>'
    r'(?:.*?<span[^>]*class="[^"]*chapter-item__name[^"]*"[^>]*>(.*?)</span>)?',
    re.IGNORECASE | re.DOTALL,
)
# Some chapters have suffix slugs like ``chapter-52-the-end``; we only
# want the leading numeric (or N.M decimal) portion.
_CHAPTER_NUM_FROM_URL_RE = re.compile(
    r"/chapter-(\d+(?:\.\d+)?)", re.IGNORECASE
)
_CHAPTER_NUM_FROM_TEXT_RE = re.compile(
    r"chapter\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE
)
# `<a href="/<kind>/<slug>/" rel="tag" class="..."><span class="pl-2 pr-3 ...">NAME</span>...`
# inside the metadata column. Same DOM as hentairead.
_META_TAG_RE = re.compile(
    r'<a\s+href="/(tag|author|artist|genre|category)/[^"]+"\s+rel="tag"[^>]*>\s*'
    r'<span[^>]*class="[^"]*pl-2[^"]*"[^>]*>([^<]+?)</span>',
    re.IGNORECASE,
)
# `var chapterData = {"data":"<b64>","base":"<url>"};` — the assignment
# always uses double quotes (it's JSON inside a JS literal) so we can
# regex-extract without parsing the surrounding script.
_CHAPTER_DATA_RE = re.compile(
    r'var\s+chapterData\s*=\s*'
    r'\{\s*"data"\s*:\s*"([^"]+)"\s*,\s*"base"\s*:\s*"([^"]+)"\s*\}',
    re.IGNORECASE | re.DOTALL,
)


class ManhwareadProvider(Provider):
    """Provider for https://manhwaread.com/ ."""

    name = "manhwaread"
    label = "manhwaread.com"
    domains = ("manhwaread.com",)
    image_referer = "https://manhwaread.com/"
    example_url = "https://manhwaread.com/manhwa/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "manhwaread.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    @retry_with_backoff()
    def _fetch_series_page(self, slug: str) -> str:
        url = f"https://manhwaread.com/manhwa/{slug}/"
        logger.debug(f"Fetching manhwaread series page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://manhwaread.com/"}
        )
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_chapter_page(self, chapter_url: str, slug: str) -> str:
        logger.debug(f"Fetching manhwaread chapter page: {chapter_url}")
        r = get_session().get(
            chapter_url, timeout=30,
            headers={"Referer": f"https://manhwaread.com/manhwa/{slug}/"},
        )
        r.raise_for_status()
        return r.text

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _strip_tags(s: str) -> str:
        return unescape(re.sub(r"<[^>]+>", " ", s)).strip()

    @staticmethod
    def _collapse_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def _parse_metadata(self, html: str, slug: str) -> dict:
        out: dict = {
            "title": "Unknown",
            "alt_titles": [],
            "cover_url": None,
            "manga_id": None,
            "description": "",
            "artists": [],
            "tags": [],
        }

        title_m = _TITLE_RE.search(html)
        if title_m:
            out["title"] = self._collapse_ws(self._strip_tags(title_m.group(1)))
            alt_raw = title_m.group(2) or ""
            if alt_raw:
                cleaned = self._collapse_ws(self._strip_tags(alt_raw))
                for piece in cleaned.split("|"):
                    piece = piece.strip()
                    if piece:
                        out["alt_titles"].append(piece)

        og_img = _OG_IMAGE_RE.search(html)
        if og_img:
            cover = og_img.group(1).strip()
            if cover.startswith("http://"):
                cover = "https://" + cover[len("http://"):]
            out["cover_url"] = cover

        og_desc = _OG_DESC_RE.search(html)
        if og_desc:
            out["description"] = unescape(og_desc.group(1)).strip()

        mid_m = _MANGA_ID_RE.search(html)
        if mid_m:
            try:
                out["manga_id"] = int(mid_m.group(1))
            except ValueError:
                pass

        seen_tag: set[str] = set()
        seen_artist: set[str] = set()
        for kind, raw_name in _META_TAG_RE.findall(html):
            kind_l = kind.lower()
            name = self._collapse_ws(unescape(raw_name))
            if not name:
                continue
            key = name.casefold()
            if kind_l in {"author", "artist"}:
                if key not in seen_artist:
                    out["artists"].append(name)
                    seen_artist.add(key)
            else:
                if key not in seen_tag:
                    out["tags"].append(name)
                    seen_tag.add(key)

        return out

    def _parse_chapters(self, html: str) -> list[tuple[str, str, Optional[int]]]:
        """
        Return ``[(absolute_chapter_url, number_str, data_id), ...]`` in
        ascending chapter order. ``number_str`` is the visible chapter
        number ("1", "1.5", …); we keep it stringy so sub-chapter
        precision is preserved.
        """
        seen: set[str] = set()
        items: list[tuple[str, str, Optional[int], float]] = []
        for url, data_id, raw_label in _CHAPTER_ITEM_RE.findall(html):
            url = unescape(url).strip()
            if url.startswith("/"):
                url = "https://manhwaread.com" + url
            if url in seen:
                continue
            seen.add(url)

            num_str: Optional[str] = None
            url_m = _CHAPTER_NUM_FROM_URL_RE.search(url)
            if url_m:
                num_str = url_m.group(1)
            if not num_str and raw_label:
                txt = self._collapse_ws(self._strip_tags(raw_label))
                txt_m = _CHAPTER_NUM_FROM_TEXT_RE.search(txt)
                if txt_m:
                    num_str = txt_m.group(1)
            if not num_str:
                continue

            # URLs sometimes use zero-padded numbers ("chapter-01");
            # strip the padding for the user-visible label so it lines
            # up with what the site itself shows.
            display_num = num_str.lstrip("0") or "0"

            try:
                sort_key = float(display_num)
            except ValueError:
                sort_key = -1.0
            try:
                did = int(data_id) if data_id else None
            except ValueError:
                did = None

            items.append((url, display_num, did, sort_key))

        items.sort(key=lambda t: t[3])
        return [(u, n, d) for u, n, d, _ in items]

    def _decode_chapter_data(self, html: str) -> tuple[str, list[str]]:
        """
        Extract ``chapterData.base`` and the per-page src list from
        the reader page. Returns ``(base, [src, src, ...])`` in page
        order. Raises ``RuntimeError`` if the blob is missing or
        malformed.
        """
        m = _CHAPTER_DATA_RE.search(html)
        if not m:
            raise RuntimeError(
                "manhwaread: no chapterData blob on reader page; the layout may "
                "have changed."
            )
        b64, base = m.group(1).strip(), m.group(2).strip()
        # The site emits the b64 unpadded; Python's b64decode is strict.
        b64 += "=" * (-len(b64) % 4)
        try:
            decoded = base64.b64decode(b64).decode("utf-8")
            entries = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"manhwaread: failed to decode chapterData.data — {exc}"
            ) from exc
        if not isinstance(entries, list):
            raise RuntimeError(
                "manhwaread: chapterData.data did not decode to a list."
            )
        srcs: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            src = entry.get("src")
            if isinstance(src, str) and src:
                srcs.append(src.lstrip("/"))
        if not srcs:
            raise RuntimeError(
                "manhwaread: chapterData.data was empty after decoding."
            )
        return base.rstrip("/"), srcs

    # --- Provider interface ------------------------------------------

    def _build_manga_info(self, slug: str, meta: dict, chapter_count: int) -> MangaInfo:
        return MangaInfo(
            manga_id=meta.get("manga_id"),
            hash_id=str(meta.get("manga_id") or slug),
            title=meta.get("title") or slug,
            alt_titles=meta.get("alt_titles") or [],
            slug=slug,
            manga_type="manhwa",
            poster_url=meta.get("cover_url"),
            original_language="ko",
            status=None,
            final_chapter=str(chapter_count) if chapter_count else None,
            latest_chapter=str(chapter_count) if chapter_count else None,
            is_nsfw=True,
            description=meta.get("description") or "",
            source=self.name,
            source_url=f"https://manhwaread.com/manhwa/{slug}/",
            artists=meta.get("artists") or [],
            tags=meta.get("tags") or [],
            genres=meta.get("tags") or [],
        )

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_series_page(code)
        meta = self._parse_metadata(html, code)
        chapters = self._parse_chapters(html)
        return self._build_manga_info(code, meta, len(chapters))

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_series_page(code)
        out: list[Chapter] = []
        for chapter_url, num_str, data_id in self._parse_chapters(html):
            try:
                cid = int(data_id) if data_id is not None else int(float(num_str))
            except (TypeError, ValueError):
                cid = 0
            out.append(Chapter(
                chapter_id=cid,
                number=num_str,
                title=None,
                # Stash the absolute reader URL so get_chapter_images
                # works after the GUI bridge's lossy chapter-dict
                # serialisation drops everything but the explicit fields.
                volume=chapter_url,
                votes=None,
                group_name=None,
                pages_count=0,
                image_urls=[],
            ))
        return out

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        chapter_url = (chapter.volume or "").strip()
        if not chapter_url:
            raise RuntimeError(
                "manhwaread chapter is missing both image_urls and the "
                "reader URL needed to fetch them."
            )
        slug_m = _SLUG_RE.search(chapter_url)
        slug = slug_m.group(1) if slug_m else ""
        html = self._fetch_chapter_page(chapter_url, slug)
        base, srcs = self._decode_chapter_data(html)
        return [f"{base}/{src}" for src in srcs]
