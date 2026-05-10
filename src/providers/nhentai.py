"""
nhentai.to provider.

Galleries on nhentai.to expose enough on a single HTML page to build the
download set: title, page count, tags/artists, the CDN media id, and per
page thumbnails (from which we infer real page extensions).

A "gallery" maps onto our model as a manga with exactly one chapter.
"""

import json
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Map nhentai's compact extension codes to real extensions, just in case
# the mirror exposes them in JSON-style markup.
_EXT_CODE_MAP = {"j": "jpg", "p": "png", "w": "webp", "g": "gif"}
_GALLERY_RE = re.compile(r"/g/(\d+)", re.IGNORECASE)
_MEDIA_ID_RE = re.compile(r"/galleries/(\d+)/", re.IGNORECASE)
_THUMB_RE = re.compile(
    r"/galleries/(\d+)/(\d+)t\.(jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)
_PAGE_THUMB_PATH_RE = re.compile(
    r"/g/\d+/(\d+)/?", re.IGNORECASE
)


class NhentaiProvider(Provider):
    """Provider for https://nhentai.to/ (and compatible mirrors)."""

    name = "nhentai"
    label = "nhentai.to"
    domains = ("nhentai.to",)
    image_referer = "https://nhentai.to/"
    example_url = "https://nhentai.to/g/<id>/"

    @classmethod
    def matches(cls, url: str) -> bool:
        u = (url or "").lower()
        return "nhentai.to" in u or "nhentai.net" in u

    def extract_code(self, url: str) -> str:
        m = _GALLERY_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find gallery id in URL: {url}")
        return m.group(1)

    @retry_with_backoff()
    def _fetch_gallery_page(self, code: str) -> str:
        url = f"https://nhentai.to/g/{code}/"
        logger.debug(f"Fetching nhentai gallery page: {url}")
        response = get_session().get(
            url,
            timeout=30,
            headers={"Referer": "https://nhentai.to/"},
        )
        response.raise_for_status()
        return response.text

    def _parse_gallery(self, code: str, html: str) -> Tuple[MangaInfo, list[str]]:
        """Return (MangaInfo, ordered list of full-resolution image URLs)."""
        try:
            from bs4 import BeautifulSoup  # local import keeps base deps small
        except ImportError as e:
            raise RuntimeError(
                "beautifulsoup4 is required for nhentai support. "
                "Install with: pip install beautifulsoup4"
            ) from e

        soup = BeautifulSoup(html, "html.parser")

        # --- title ----------------------------------------------------
        title_en, title_jp = self._extract_titles(soup)
        # Strip the bracketed artist prefix from the english title for the
        # display name; keep the original as alt.
        display_title = re.sub(r"^\s*\[[^\]]+\]\s*", "", title_en).strip() or title_en

        # --- media id + per-page extensions ---------------------------
        # Inline gallery JSON is authoritative when present (one entry per
        # page with the real extension code). Thumbnail scraping is a
        # fallback for sites/galleries that don't ship the JSON, but it
        # misses lazy-loaded thumbnails and forces us to guess extensions.
        media_id: Optional[int] = None
        page_exts: dict[int, str] = {}
        gallery_json = self._extract_gallery_json(html)

        if gallery_json:
            mid = gallery_json.get("media_id")
            try:
                media_id = int(mid) if mid is not None else None
            except (TypeError, ValueError):
                media_id = None
            pages = (gallery_json.get("images") or {}).get("pages") or []
            for i, p in enumerate(pages, 1):
                code_t = (p or {}).get("t", "j")
                page_exts[i] = _EXT_CODE_MAP.get(code_t, "jpg")
            logger.debug(
                f"nhentai gallery JSON: media_id={media_id}, pages={len(page_exts)}"
            )

        if not media_id or not page_exts:
            # Fallback: scan thumbnails / cover URL.
            scraped_mid, scraped_exts = self._extract_pages(soup, html)
            media_id = media_id or scraped_mid
            for k, v in scraped_exts.items():
                page_exts.setdefault(k, v)

        if not media_id:
            raise RuntimeError("Failed to find media id on gallery page")

        # --- num pages ------------------------------------------------
        num_pages = (
            len(page_exts)
            if page_exts and max(page_exts.keys()) == len(page_exts)
            else (max(page_exts.keys()) if page_exts else 0)
        )
        if not num_pages:
            num_pages = self._extract_num_pages(soup)
        if not num_pages:
            raise RuntimeError("Could not determine page count")

        # Build URLs. Pages we don't have an explicit ext for fall back to
        # 'jpg' (most common); the image downloader still tries other
        # extensions on 404 as a final safety net.
        ordered_urls: list[str] = []
        for i in range(1, num_pages + 1):
            ext = page_exts.get(i, "jpg")
            ordered_urls.append(
                f"https://zrocdn.xyz/galleries/{media_id}/{i}.{ext}"
            )

        # --- tags / artists / categories ------------------------------
        tags, artists = self._extract_tags(soup)

        cover_url = self._extract_cover(soup, media_id)

        manga = MangaInfo(
            manga_id=int(code) if code.isdigit() else None,
            hash_id=str(media_id),
            title=display_title,
            alt_titles=[t for t in (title_jp, title_en) if t and t != display_title],
            slug=str(code),
            manga_type="doujinshi",
            poster_url=cover_url,
            original_language="en",
            status="complete",
            final_chapter="1",
            latest_chapter="1",
            is_nsfw=True,
            description=(
                f"nhentai gallery #{code} ({num_pages} pages)."
                + (f" Artists: {', '.join(artists)}." if artists else "")
            ),
            source=self.name,
            source_url=f"https://nhentai.to/g/{code}/",
            artists=artists,
            tags=tags,
            genres=tags,
        )
        return manga, ordered_urls

    @staticmethod
    def _extract_gallery_json(raw_html: str) -> Optional[dict]:
        """
        Try to recover the inline gallery JSON. nhentai ships a payload
        like ``window._gallery = JSON.parse("…")`` with one entry per
        page including the file extension code. We try a few patterns
        in decreasing specificity.
        """
        # 1) JSON.parse("…") form (string is JSON-encoded twice).
        m = re.search(
            r"""(?:window\.)?_?gallery\s*=\s*JSON\.parse\(\s*(['"])(.+?)\1\s*\)""",
            raw_html,
            re.DOTALL,
        )
        if m:
            inner = m.group(2)
            for candidate in (inner, inner.encode().decode("unicode_escape")):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "media_id" in parsed:
                        return parsed
                except Exception:
                    continue

        # 2) Bare object form: gallery = {...};
        m = re.search(
            r"""(?:window\.)?_?gallery\s*=\s*(\{.+?\})\s*;""",
            raw_html,
            re.DOTALL,
        )
        if m:
            try:
                parsed = json.loads(m.group(1))
                if isinstance(parsed, dict) and "media_id" in parsed:
                    return parsed
            except Exception:
                pass

        # 3) Last-ditch: locate any balanced object that mentions
        #    "media_id" AND "pages". Useful when the markup is minified
        #    or the assignment expression varies.
        for hit in re.finditer(r'"media_id"\s*:', raw_html):
            start = raw_html.rfind("{", 0, hit.start())
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(raw_html)):
                c = raw_html[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        snippet = raw_html[start : i + 1]
                        if '"pages"' not in snippet:
                            break
                        try:
                            parsed = json.loads(snippet)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            pass
                        break
        return None

    @staticmethod
    def _extract_titles(soup) -> Tuple[str, str]:
        """Return (english/pretty title, japanese/original title)."""
        title_en = ""
        title_jp = ""
        info = soup.find(id="info") or soup
        h1 = info.find("h1")
        h2 = info.find("h2")
        if h1 and h1.get_text(strip=True):
            title_en = h1.get_text(strip=True)
        if h2 and h2.get_text(strip=True):
            title_jp = h2.get_text(strip=True)
        if not title_en:
            # Fallback to <title>
            t = soup.find("title")
            if t:
                title_en = re.sub(r"\s*[-|»].*$", "", t.get_text(strip=True))
        return title_en or "Unknown Gallery", title_jp

    @staticmethod
    def _extract_num_pages(soup) -> int:
        # Look for "Pages: N" tag block.
        for section in soup.find_all(["div", "section"]):
            text = section.get_text(" ", strip=True)
            m = re.search(r"\bPages?\s*[:\-]?\s*(\d+)", text)
            if m:
                return int(m.group(1))
        # Fallback to the "1 of N" indicator
        m = re.search(r"\b1\s+of\s+(\d+)", soup.get_text(" ", strip=True))
        return int(m.group(1)) if m else 0

    def _extract_pages(self, soup, raw_html: str) -> Tuple[Optional[int], dict[int, str]]:
        """Return (media_id, {page_number: extension}) by scanning thumbnails."""
        page_exts: dict[int, str] = {}
        media_id: Optional[int] = None

        # Scan every src/data-src in the document for thumbnail patterns
        # like /galleries/<media_id>/<n>t.<ext>
        candidates: list[str] = []
        for tag in soup.find_all(["img", "a", "source"]):
            for attr in ("src", "data-src", "data-lazy-src", "href"):
                val = tag.get(attr)
                if val:
                    candidates.append(val)

        # Fall back to a regex sweep over the raw HTML, in case the markup
        # layout is unfamiliar.
        for m in _THUMB_RE.finditer(raw_html):
            candidates.append(m.group(0))

        for val in candidates:
            m = _THUMB_RE.search(val)
            if not m:
                continue
            mid = int(m.group(1))
            page_n = int(m.group(2))
            ext = m.group(3).lower()
            if ext == "jpeg":
                ext = "jpg"
            media_id = media_id or mid
            # Once we've locked a media_id, ignore stragglers from other galleries
            if mid != media_id:
                continue
            page_exts[page_n] = ext

        if media_id is None:
            # Cover URL also encodes the media id
            for m in _MEDIA_ID_RE.finditer(raw_html):
                media_id = int(m.group(1))
                break

        return media_id, page_exts

    @staticmethod
    def _extract_cover(soup, media_id: int) -> str:
        cover_el = soup.find(id="cover")
        if cover_el:
            img = cover_el.find("img")
            if img:
                src = img.get("data-src") or img.get("src")
                if src and src.startswith("http"):
                    return src
        return f"https://zrocdn.xyz/galleries/{media_id}/cover.webp"

    @staticmethod
    def _extract_tags(soup) -> Tuple[list[str], list[str]]:
        tags: list[str] = []
        artists: list[str] = []
        # nhentai-style tag anchors: <a class="tag" href="/tag/..."><span class="name">foo</span>...</a>
        for a in soup.find_all("a", class_="tag"):
            href = a.get("href", "")
            name_span = a.find(class_="name")
            name = name_span.get_text(strip=True) if name_span else a.get_text(strip=True)
            name = re.sub(r"\s*\(\d+,?\d*\)\s*$", "", name).strip()
            if not name:
                continue
            if "/artist/" in href:
                artists.append(name)
            elif "/tag/" in href or "/category/" in href or "/parody/" in href or "/group/" in href:
                tags.append(name)
        # Deduplicate while preserving order
        return list(dict.fromkeys(tags)), list(dict.fromkeys(artists))

    # --- Provider interface ------------------------------------------

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        html = self._fetch_gallery_page(code)
        manga, _ = self._parse_gallery(code, html)
        return manga

    def get_chapters(self, code: str) -> list[Chapter]:
        html = self._fetch_gallery_page(code)
        manga, image_urls = self._parse_gallery(code, html)
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
        # Re-derive from gallery if cache was lost (e.g., deserialized chapter)
        html = self._fetch_gallery_page(str(chapter.chapter_id))
        _, urls = self._parse_gallery(str(chapter.chapter_id), html)
        return urls
