"""
Shared base for sites on the Madara WordPress theme (wp-manga).

Subclasses only declare where the site lives; parsing is common:

- Series page ``<base><series_path>/<slug>/`` — title in
  ``<div class="post-title"><h1>`` (badges like HOT / 18+ sit in spans
  inside or before the h1), cover via ``og:image``, description via
  ``og:description``, status + alternative names in
  ``summary-heading`` / ``summary-content`` rows.
- Chapter list ``<li class="wp-manga-chapter"><a href=".../chapter-N/">``,
  newest-first. Some installs render it inline; others load it with a
  POST to ``<series url>ajax/chapters/`` (``ajax_chapters = True``).
- Reader ``<img class="wp-manga-chapter-img" data-src=" https://… ">``
  inside ``<div class="reading-content">`` (note the stray spaces
  inside the attribute on some installs).

Cloudflare human checks are handled by ``get_session()`` (FlareSolverr,
auto-started), so a challenged site needs no special code here.
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


_OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+)"', re.I)
_OG_IMAGE_RE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"', re.I)
_OG_DESC_RE = re.compile(r'<meta\s+property="og:description"\s+content="([^"]+)"', re.I)
_POST_TITLE_RE = re.compile(
    r'<div\s+class="[^"]*post-title[^"]*"[^>]*>.*?<h1[^>]*>(.+?)</h1>', re.I | re.S
)
_CHAPTER_LI_RE = re.compile(
    r'<li\s+class="wp-manga-chapter[^"]*"[^>]*>\s*<a\s+href="([^"]+)"', re.I
)
_CHAPTER_NUM_RE = re.compile(r"/chapter-(\d+(?:[-.]\d+)?)", re.I)
_CHAPTER_IMG_RE = re.compile(
    r'<img[^>]*?(?:data-src|src)="\s*([^"]+?)\s*"[^>]*class="[^"]*wp-manga-chapter-img', re.I
)
_CHAPTER_IMG_RE_CLASS_FIRST = re.compile(
    r'<img[^>]*class="[^"]*wp-manga-chapter-img[^"]*"[^>]*?(?:data-src|src)="\s*([^"]+?)\s*"', re.I
)


def summary_value(html: str, heading: str) -> Optional[str]:
    """Value of a Madara ``summary-heading`` row (``<h5>Status</h5>``)."""
    m = re.search(
        r'summary-heading[^"]*"[^>]*>\s*<h5[^>]*>\s*' + heading + r'\s*:?\s*</h5>\s*</div>\s*'
        r'<div[^>]*class="[^"]*summary-content[^"]*"[^>]*>(.*?)</div>',
        html, re.I | re.S,
    )
    if not m:
        return None
    return clean_text(m.group(1)) or None


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def split_alt_titles(raw: Optional[str], title: str = "") -> list[str]:
    """Split "A / B, C; D"; drop the main title and placeholder numbers."""
    if not raw:
        return []
    out = []
    for piece in re.split(r"\s*[/,;]\s*", raw):
        piece = piece.strip()
        if piece and not piece.isdigit() and piece.lower() != title.lower() and piece not in out:
            out.append(piece)
    return out


def chapter_number(url: str, label: str = "") -> Optional[str]:
    """"chapter-26-5" → "26.5"; falls back to "Chapter 26.5" in the label."""
    m = _CHAPTER_NUM_RE.search(url) or re.search(r"chapter\s*(\d+(?:\.\d+)?)", label, re.I)
    return m.group(1).replace("-", ".") if m else None


class MadaraProvider(Provider):
    """Base class — subclasses set the class attributes below."""

    base_url: str = ""           # "https://www.toongod.org"
    series_path: str = "/manga/"  # path segment before the slug
    ajax_chapters: bool = False  # chapter list needs POST ajax/chapters/
    title_suffixes: tuple[str, ...] = ()  # og:title boilerplate to strip

    @classmethod
    def matches(cls, url: str) -> bool:
        host = re.sub(r"^https?://", "", (url or "").lower()).split("/")[0]
        return any(host == d or host.endswith("." + d) for d in cls.domains)

    def extract_code(self, url: str) -> str:
        m = re.search(re.escape(self.series_path) + r"([^/?#]+)", url or "")
        if not m:
            raise ValueError(f"Could not find the series slug in URL: {url}")
        return m.group(1)

    def series_url(self, code: str) -> str:
        return f"{self.base_url}{self.series_path}{code}/"

    # ── HTTP ─────────────────────────────────────────────────────────

    @retry_with_backoff()
    def _fetch(self, url: str) -> str:
        r = get_session().get(url, timeout=30, headers={"Referer": f"{self.base_url}/"})
        r.raise_for_status()
        return r.text

    @retry_with_backoff()
    def _fetch_ajax_chapters(self, code: str) -> str:
        url = self.series_url(code)
        r = get_session().post(
            url + "ajax/chapters/",
            timeout=30,
            headers={"Referer": url, "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()
        return r.text

    # ── Parsing (overridable per engine) ─────────────────────────────

    def _parse_title(self, html: str, code: str) -> str:
        m = _POST_TITLE_RE.search(html)
        if m:
            # Drop badge spans ("18+", "HOT") before taking the text.
            title = clean_text(re.sub(r"<span[^>]*>.*?</span>", "", m.group(1), flags=re.S))
            if title:
                return title
        m = _OG_TITLE_RE.search(html)
        if m:
            title = clean_text(m.group(1))
            for suffix in self.title_suffixes:
                title = re.sub(suffix, "", title, flags=re.I).strip()
            return title
        return code

    def _parse_metadata(self, html: str, code: str) -> dict:
        title = self._parse_title(html, code)
        og_img = _OG_IMAGE_RE.search(html)
        og_desc = _OG_DESC_RE.search(html)
        return {
            "title": title,
            "cover": unescape(og_img.group(1)).strip() if og_img else None,
            "description": clean_text(og_desc.group(1)) if og_desc else "",
            "alt_titles": split_alt_titles(summary_value(html, "Alternative"), title),
            "status": summary_value(html, "Status"),
        }

    def _parse_chapter_rows(self, html: str, code: str) -> list[tuple[str, str]]:
        """``[(absolute_url, number), ...]`` in page order (newest-first)."""
        rows, seen = [], set()
        for href in _CHAPTER_LI_RE.findall(html):
            url = unescape(href).strip()
            if not url.startswith("http"):
                url = self.base_url + url
            number = chapter_number(url)
            if url in seen or number is None:
                continue
            seen.add(url)
            rows.append((url, number))
        return rows

    def _extract_images(self, html: str) -> list[str]:
        start = html.find("reading-content")
        scope = html[start:] if start >= 0 else html
        urls: list[str] = []
        for m in sorted(
            list(_CHAPTER_IMG_RE.finditer(scope)) + list(_CHAPTER_IMG_RE_CLASS_FIRST.finditer(scope)),
            key=lambda m: m.start(),
        ):
            url = unescape(m.group(1)).strip()
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http") and url not in urls:
                urls.append(url)
        return urls

    # ── Provider interface ───────────────────────────────────────────

    def _chapter_rows(self, code: str, html: str) -> list[tuple[str, str]]:
        rows = self._parse_chapter_rows(html, code)
        if not rows and self.ajax_chapters:
            rows = self._parse_chapter_rows(self._fetch_ajax_chapters(code), code)
        return rows

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch(self.series_url(code))
        meta = self._parse_metadata(html, code)
        rows = self._chapter_rows(code, html)
        return MangaInfo(
            hash_id=code,
            title=meta["title"],
            slug=code,
            alt_titles=meta["alt_titles"],
            manga_type="manhwa",
            poster_url=meta["cover"],
            original_language="ko",
            status=meta["status"],
            latest_chapter=rows[0][1] if rows else None,
            is_nsfw=True,
            description=meta["description"],
            source=self.name,
            source_url=self.series_url(code),
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        rows = self._chapter_rows(code, self._fetch(self.series_url(code)))
        if not rows:
            raise RuntimeError(f"{self.label}: no chapters found for {code} — layout may have changed.")
        # Oldest-first like the rest of the pipeline; the reader URL rides
        # in Chapter.volume (per-provider stash convention).
        return [Chapter(chapter_id=0, number=n, title=None, volume=u) for u, n in reversed(rows)]

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        url = (chapter.volume or "").strip()
        if not url:
            raise RuntimeError(f"{self.label} chapter is missing its reader URL (Chapter.volume)")
        urls = self._extract_images(self._fetch(url))
        if not urls:
            raise RuntimeError(f"{self.label}: no images found on {url}")
        return urls
