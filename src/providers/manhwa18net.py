"""
manhwa18.net provider — Inertia.js-backed NSFW manhwa site.

Distinct from manhwa18.com (different site, different stack). The .net
site is a Laravel + Inertia.js SPA: every page embeds its full props
as JSON in ``<div id="app" data-page="...">``. Two endpoints cover
everything we need:

- **Series page** ``https://www.manhwa18.net/manga/<slug>`` — props
  carry the manga record AND the complete chapter list in a single
  fetch. Chapter slugs vary: recent chapters are ``chapter-N``,
  older imports are ``chap-NN-<id>`` with an appended numeric id.
  We use ``chapter.slug`` verbatim to build the reader URL.
- **Reader page** ``https://www.manhwa18.net/manga/<slug>/<chapter-slug>``
  — ``props.chapterContent`` is an HTML string with
  ``<img src="..." loading="lazy"/>`` tags in reading order. Images
  come from ``min.manhwa18.net`` and require Referer = the .net domain.

No Cloudflare challenge in practice — the default ``get_session()``
(curl_cffi chrome120 impersonation) gets through cleanly. Site is
explicitly 18+, so ``is_nsfw`` is hard-set to True. Site uses an
integer ``status_id`` whose mapping isn't documented; we leave
``status`` as None and let the library's manual override pick it up.
"""

import html as html_module
import json
import re
from html import unescape
from typing import Optional

from .base import Provider
from ..core.models import Chapter, MangaInfo
from ..utils.logger import get_logger
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session

logger = get_logger(__name__)


_BASE = "https://www.manhwa18.net"
_SLUG_RE = re.compile(r"/manga/([^/?#]+)", re.IGNORECASE)
_DATA_PAGE_RE = re.compile(
    r'<div\s+id="app"\s+data-page="([^"]+)"', re.IGNORECASE
)
# Reader-page <img> tags: ``<img src="..." loading="lazy"/>``. We accept
# either ``src`` or ``data-src`` so a future lazy-loader switch
# doesn't break us.
_READER_IMG_RE = re.compile(
    r'<img[^>]+(?:data-src|src)="([^"]+)"', re.IGNORECASE
)
# Matches "Chapter 306", "chap 12", "chap-01-361", "chapter-62.5", etc.
_CHAPTER_NUM_RE = re.compile(
    r"chap(?:ter)?[-_\s]*(\d+(?:\.\d+)?)", re.IGNORECASE
)


def _parse_data_page(html: str) -> dict:
    """Extract and JSON-parse the Inertia.js data-page payload."""
    m = _DATA_PAGE_RE.search(html)
    if not m:
        raise RuntimeError(
            'manhwa18net: could not find <div id="app" data-page=...> '
            "— Inertia layout may have changed"
        )
    raw = html_module.unescape(m.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"manhwa18net: invalid JSON in data-page: {e}"
        ) from e


class Manhwa18NetProvider(Provider):
    """Provider for https://www.manhwa18.net/ (Inertia.js SPA)."""

    name = "manhwa18net"
    label = "manhwa18.net"
    domains = ("manhwa18.net", "www.manhwa18.net")
    image_referer = "https://www.manhwa18.net/"
    example_url = "https://www.manhwa18.net/manga/<slug>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "manhwa18.net" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find series slug in URL: {url}")
        return m.group(1)

    # ── HTTP ─────────────────────────────────────────────────────────

    @retry_with_backoff()
    def _fetch_series_page(self, slug: str) -> dict:
        url = f"{_BASE}/manga/{slug}"
        logger.debug(f"Fetching manhwa18net series page: {url}")
        r = get_session().get(
            url, timeout=30, headers={"Referer": _BASE + "/"}
        )
        r.raise_for_status()
        return _parse_data_page(r.text)

    @retry_with_backoff()
    def _fetch_reader_page(self, chapter_url: str) -> dict:
        logger.debug(f"Fetching manhwa18net reader page: {chapter_url}")
        r = get_session().get(
            chapter_url, timeout=30, headers={"Referer": _BASE + "/"}
        )
        r.raise_for_status()
        return _parse_data_page(r.text)

    # ── Provider interface ───────────────────────────────────────────

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        props = self._fetch_series_page(code).get("props", {}) or {}
        manga = props.get("manga", {}) or {}

        title = (manga.get("name") or code).strip()
        alts: list[str] = []
        other = (manga.get("other_name") or "").strip()
        if other and other.lower() != title.lower():
            alts.append(other)

        cover = manga.get("cover_url") or manga.get("thumb_url") or None

        # ``pilot`` is the synopsis, served as HTML — strip tags + decode
        # entities so the library shows clean text.
        description = unescape(
            re.sub(r"<[^>]+>", "", manga.get("pilot") or "")
        ).strip()

        chapters_data = props.get("chapters") or []
        latest: Optional[str] = None
        if chapters_data:
            num_match = _CHAPTER_NUM_RE.search(
                chapters_data[0].get("name") or ""
            )
            if num_match:
                latest = num_match.group(1)

        artists = [
            a.get("name") for a in (manga.get("artists") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        tags = [
            g.get("name") for g in (manga.get("genres") or [])
            if isinstance(g, dict) and g.get("name")
        ]

        return MangaInfo(
            hash_id=str(manga.get("id") or code),
            title=title,
            alt_titles=alts,
            slug=code,
            manga_type="manhwa",
            poster_url=cover,
            original_language="ko",
            status=None,  # status_id is an int with no public mapping
            latest_chapter=latest,
            is_nsfw=True,  # site is explicitly 18+
            description=description,
            artists=artists,
            tags=tags,
            source=self.name,
            source_url=f"{_BASE}/manga/{code}",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        props = self._fetch_series_page(code).get("props", {}) or {}
        chapters_data = props.get("chapters") or []
        if not chapters_data:
            raise RuntimeError(
                f"manhwa18net: no chapters found for /manga/{code} — "
                f"props.chapters was empty"
            )

        # JSON lists newest-first; pipeline wants oldest-first.
        # Stash the absolute reader URL in ``volume`` per the project
        # convention (toonily / manhwabuddy / manhwaread / comix all do
        # the same), so get_chapter_images works after the GUI bridge's
        # lossy chapter-dict serialisation.
        chapters: list[Chapter] = []
        for ch in reversed(chapters_data):
            slug = (ch.get("slug") or "").strip()
            name = (ch.get("name") or "").strip()
            if not slug:
                continue
            num_match = _CHAPTER_NUM_RE.search(name) \
                or _CHAPTER_NUM_RE.search(slug)
            if not num_match:
                logger.debug(
                    f"manhwa18net: skipping un-numbered chapter {slug!r}"
                )
                continue
            number = num_match.group(1).lstrip("0") or "0"
            # Drop redundant "Chapter N" titles — display would just
            # duplicate the chapter number.
            title = name if name and not re.fullmatch(
                rf"chap(?:ter)?\s*0*{re.escape(number)}", name,
                flags=re.IGNORECASE,
            ) else None
            chapters.append(
                Chapter(
                    chapter_id=int(ch.get("id") or 0),
                    number=number,
                    title=title,
                    volume=f"{_BASE}/manga/{code}/{slug}",
                )
            )
        return chapters

    @staticmethod
    def _extract_reader_image_urls(chapter_content: str) -> list[str]:
        # chapterContent is a dedicated field containing only the
        # chapter's <img> tags — no site chrome, no ad banners — so we
        # don't host-filter. The image CDN host varies per chapter age:
        # recent chapters land on ``min.manhwa18.net``, older imports
        # come from ``cdn.pornwa.us`` (and historically others), so any
        # host-prefix filter would mis-drop old content.
        urls: list[str] = []
        for src in _READER_IMG_RE.findall(chapter_content or ""):
            url = unescape(src).strip()
            if not url or not url.lower().startswith(("http://", "https://")):
                continue
            urls.append(url)
        return urls

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        chapter_url = (chapter.volume or "").strip()
        if not chapter_url:
            raise RuntimeError(
                "manhwa18net chapter is missing the reader URL "
                "(Chapter.volume was empty)"
            )
        props = self._fetch_reader_page(chapter_url).get("props", {}) or {}
        content = props.get("chapterContent") or ""
        urls = self._extract_reader_image_urls(content)
        if not urls:
            raise RuntimeError(
                f"manhwa18net: no images parsed from reader page "
                f"{chapter_url}"
            )
        return urls
