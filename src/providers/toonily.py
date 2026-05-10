"""
toonily.com provider — multi-chapter Korean manhwa / webtoon site.

Two URL forms are accepted:

- ``/serie/<slug>/`` — series page (canonical; lists all chapters).
- ``/serie/<slug>/chapter-N/`` — individual reader page; we pick the
  slug out and treat it the same as the canonical form.

Pipeline:

- ``get_manga_info`` / ``get_chapters`` — one HTTP call to the series
  page. The chapter list lives in
  ``<li class="wp-manga-chapter"><a href="/serie/<slug>/chapter-N/">``
  in descending order; we reverse to ascending so chapter 1 downloads
  first. The full chapter URL is stashed in ``Chapter.volume`` so
  ``get_chapter_images`` can fetch it without rebuilding (and so it
  survives the GUI bridge's lossy chapter-dict serialisation).
- ``get_chapter_images`` — fetch the reader page, extract every
  ``<img id="image-<n>" src="https://data.tnlycdn.com/chapters/.../NN.jpg">``
  inside ``<div class="page-break no-gaps">``. There is one img per
  page-break, *not* lazy-loaded — ``src`` is the real URL. We sort
  by the integer index in ``image-<n>`` to be safe against minor
  HTML reordering.

Anti-bot:

- Toonily fronts everything with Cloudflare. Plain ``requests``
  earns a 403; the project's shared ``get_session()`` (curl_cffi
  Chrome-120 impersonation) sails through, same as for the other
  sites in the matrix. No Playwright / FlareSolverr needed at the
  time of writing — if that changes, the fix is the same as
  mangafire (drop a Playwright shim in front).
- The image CDN ``data.tnlycdn.com`` returns 403 without
  ``Referer: https://toonily.com/``. ``image_referer`` handles that.
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


_SLUG_RE = re.compile(r"/serie/([^/?#]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'<div class="post-title"[^>]*>\s*<h1[^>]*>(.+?)</h1>',
    re.IGNORECASE | re.DOTALL,
)
_OG_IMAGE_RE = re.compile(
    r'<meta property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)
_OG_DESC_RE = re.compile(
    r'<meta property="og:description"\s+content="([^"]+)"', re.IGNORECASE
)
# Each chapter is `<li class="wp-manga-chapter ...">  <a href="...">  Chapter N  </a> </li>`.
# The link text is whatever the author named it ("Chapter 35", sometimes
# with extras); we capture both URL and text and pull the chapter
# *number* out of either.
_CHAPTER_LI_RE = re.compile(
    r'<li class="wp-manga-chapter[^"]*">\s*'
    r'(?:<[^>]+>\s*)*'           # tolerate stray spans before the <a>
    r'<a[^>]+href="([^"]+/chapter-[^"/]+/?)"[^>]*>\s*([^<]+?)\s*</a>',
    re.IGNORECASE | re.DOTALL,
)
_CHAPTER_NUM_FROM_URL_RE = re.compile(r"/chapter-([^/]+?)/?$", re.IGNORECASE)
_CHAPTER_NUM_FROM_TEXT_RE = re.compile(r"chapter\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
# `<img id="image-N" src="https://data.tnlycdn.com/chapters/.../NN.jpg">`
# inside <div class="page-break no-gaps">. The `id` is a 0-based index;
# we use it as the canonical sort key.
_IMG_RE = re.compile(
    r'<img[^>]+id=["\']image-(\d+)["\'][^>]+src=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TAG_LINK_RE = re.compile(
    r'<a [^>]*href="https?://toonily\.com/tag/[^"]+"[^>]*>\s*#?\s*([^<]+?)\s*</a>',
    re.IGNORECASE,
)
# `<div class="post-content_item"><div class="summary-heading"><h5>FIELD</h5></div>
#   <div class="summary-content">...</div>`. Captures (heading, content_html).
_META_ITEM_RE = re.compile(
    r'<div class="post-content_item">\s*'
    r'<div class="summary-heading">\s*<h5>([^<]+)</h5>\s*</div>\s*'
    r'<div class="summary-content">(.*?)</div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
# Inner-text inside <a>...</a> — used to harvest writer / artist names
# from the summary blocks.
_INNER_A_RE = re.compile(r'<a[^>]*>\s*([^<]+?)\s*</a>', re.IGNORECASE)


class ToonilyProvider(Provider):
    """Provider for https://toonily.com/ ."""

    name = "toonily"
    label = "toonily.com"
    domains = ("toonily.com",)
    image_referer = "https://toonily.com/"
    example_url = "https://toonily.com/serie/<slug>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "toonily.com" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    @retry_with_backoff()
    def _fetch_series_page(self, slug: str) -> str:
        url = f"https://toonily.com/serie/{slug}/"
        logger.debug(f"Fetching toonily series page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": "https://toonily.com/"}
        )
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_chapter_page(self, chapter_url: str, slug: str) -> str:
        logger.debug(f"Fetching toonily chapter page: {chapter_url}")
        r = get_session().get(
            chapter_url, timeout=30,
            headers={"Referer": f"https://toonily.com/serie/{slug}/"},
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
            "description": "",
            "artists": [],
            "tags": [],
            "status": None,
        }

        title_m = _TITLE_RE.search(html)
        if title_m:
            out["title"] = self._collapse_ws(self._strip_tags(title_m.group(1)))

        og_img = _OG_IMAGE_RE.search(html)
        if og_img:
            cover = og_img.group(1).strip()
            if cover.startswith("http://"):
                cover = "https://" + cover[len("http://"):]
            out["cover_url"] = cover

        og_desc = _OG_DESC_RE.search(html)
        if og_desc:
            out["description"] = unescape(og_desc.group(1)).strip()

        # Tag list (the visible ones below the synopsis).
        seen_tag: set[str] = set()
        for name in _TAG_LINK_RE.findall(html):
            n = self._collapse_ws(unescape(name))
            if n and n.casefold() not in seen_tag:
                out["tags"].append(n)
                seen_tag.add(n.casefold())

        # Structured summary blocks (Alt Name / Writer / Artist / Genre /
        # Status / Publisher). Each one's "value" is sometimes plain
        # text ("Updating") and sometimes a list of <a> links.
        seen_artist: set[str] = set()
        for heading, content_html in _META_ITEM_RE.findall(html):
            heading_l = heading.strip().lower()
            content_text = self._collapse_ws(self._strip_tags(content_html))
            if not content_text or content_text.lower() == "updating":
                continue

            if heading_l.startswith("alt"):
                # Multi-name fields are typically pipe- or comma-separated.
                for piece in re.split(r"\s*[|,;/]\s*", content_text):
                    if piece and piece not in out["alt_titles"]:
                        out["alt_titles"].append(piece)
            elif heading_l.startswith("writer") or heading_l.startswith("artist") or heading_l.startswith("author"):
                names = _INNER_A_RE.findall(content_html)
                if not names:
                    names = [content_text]
                for n in names:
                    n = self._collapse_ws(unescape(n))
                    key = n.casefold()
                    if n and key not in seen_artist:
                        out["artists"].append(n)
                        seen_artist.add(key)
            elif heading_l.startswith("genre"):
                names = _INNER_A_RE.findall(content_html) or [content_text]
                for n in names:
                    n = self._collapse_ws(unescape(n))
                    if n and n.casefold() not in seen_tag:
                        out["tags"].append(n)
                        seen_tag.add(n.casefold())
            elif heading_l.startswith("status"):
                out["status"] = content_text

        return out

    def _parse_chapters(self, html: str) -> list[Tuple[str, str]]:
        """
        Return ``[(chapter_url, chapter_number), ...]`` in ascending
        chapter order. ``chapter_number`` is a string so we don't lose
        sub-chapter precision (e.g. ``"5.1"``).
        """
        seen: set[str] = set()
        items: list[Tuple[str, str, float]] = []
        for url, label in _CHAPTER_LI_RE.findall(html):
            url = unescape(url).strip()
            if url in seen:
                continue
            seen.add(url)

            num_str: Optional[str] = None
            url_m = _CHAPTER_NUM_FROM_URL_RE.search(url)
            if url_m:
                num_str = url_m.group(1)
            if not num_str:
                txt_m = _CHAPTER_NUM_FROM_TEXT_RE.search(label)
                if txt_m:
                    num_str = txt_m.group(1)
            if not num_str:
                continue

            try:
                sort_key = float(num_str)
            except ValueError:
                # Non-numeric chapter (e.g. "prologue"); shove it at
                # the bottom but keep it in the list.
                sort_key = -1.0
            items.append((url, num_str, sort_key))

        items.sort(key=lambda t: t[2])
        return [(u, n) for u, n, _ in items]

    def _parse_image_urls(self, html: str) -> list[str]:
        pairs: list[Tuple[int, str]] = []
        for idx_s, src in _IMG_RE.findall(html):
            try:
                idx = int(idx_s)
            except ValueError:
                continue
            src = unescape(src).strip()
            if not src:
                continue
            # Skip the decorative "Discord server" placeholder
            # (id="image-999"). The real pages have monotonically
            # increasing 0-based indices well below that.
            if "/wp-content/" in src:
                continue
            pairs.append((idx, src))

        if not pairs:
            raise RuntimeError(
                "No images found on the toonily reader page; the layout "
                "may have changed."
            )
        pairs.sort(key=lambda p: p[0])
        return [u for _, u in pairs]

    # --- Provider interface ------------------------------------------

    def _build_manga_info(self, slug: str, meta: dict, chapter_count: int) -> MangaInfo:
        return MangaInfo(
            manga_id=None,
            hash_id=slug,
            title=meta.get("title") or slug,
            alt_titles=meta.get("alt_titles") or [],
            slug=slug,
            manga_type="manhwa",
            poster_url=meta.get("cover_url"),
            original_language="ko",
            status=meta.get("status") or "Unknown",
            final_chapter=str(chapter_count) if chapter_count else None,
            latest_chapter=str(chapter_count) if chapter_count else None,
            is_nsfw=True,
            description=meta.get("description") or "",
            source=self.name,
            source_url=f"https://toonily.com/serie/{slug}/",
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
        chapter_pairs = self._parse_chapters(html)
        out: list[Chapter] = []
        for chapter_url, num_str in chapter_pairs:
            try:
                cid = int(float(num_str)) if num_str.replace(".", "").isdigit() else 0
            except (TypeError, ValueError):
                cid = 0
            out.append(Chapter(
                chapter_id=cid,
                number=num_str,
                title=None,
                # Stash the absolute reader URL so get_chapter_images
                # works even after the GUI bridge round-trips the dict
                # (which drops everything except the explicit fields).
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
                "toonily chapter is missing both image_urls and the "
                "reader URL needed to fetch them."
            )
        # Best-effort slug recovery for the Referer header — toonily
        # checks it and 403s otherwise.
        slug_m = _SLUG_RE.search(chapter_url)
        slug = slug_m.group(1) if slug_m else ""
        html = self._fetch_chapter_page(chapter_url, slug)
        return self._parse_image_urls(html)
