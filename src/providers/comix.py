"""
comix.to provider — adapter over :mod:`src.api.comix`.

We cache the slug we learn during ``get_manga_info`` so a subsequent
``get_chapters`` / ``get_chapter_images`` call can build the right
chapter reader URL even after the GUI bridge serialisation drops most
fields. (The bridge re-instantiates the provider for downloads and
re-runs ``extract_code(source_url)`` on it; we extract the slug there
too.)
"""

from typing import Optional
from urllib.parse import urlparse

from ..api.comix import ComixAPI
from ..core.models import Chapter, MangaInfo
from .base import Provider


class ComixProvider(Provider):
    """Provider for https://comix.to/."""

    name = "comix"
    label = "Comix.to"
    domains = ("comix.to",)
    image_referer = "https://comix.to/"
    example_url = "https://comix.to/title/<hid>-<slug>"

    def __init__(self) -> None:
        # Cached slug per hid. Populated from extract_code, get_manga_info,
        # or any other entry point that gives us a URL with the slug.
        self._slug_cache: dict[str, str] = {}

    @classmethod
    def matches(cls, url: str) -> bool:
        return "comix.to" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        code = ComixAPI.extract_manga_code(url)
        slug = self._slug_from_url(url)
        if slug:
            self._slug_cache[code] = slug
        return code

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        info = ComixAPI.get_manga_info(code)
        if info is not None:
            info.source = self.name
            if info.slug:
                self._slug_cache[code] = info.slug
            if not info.source_url and info.hash_id and info.slug:
                info.source_url = f"https://comix.to/title/{info.hash_id}-{info.slug}"
        return info

    def get_chapters(self, code: str) -> list[Chapter]:
        slug = self._slug_cache.get(code, "")
        if not slug:
            # Lookup-and-cache; a bare get_chapters call (no prior info
            # fetch) needs the slug to build chapter reader URLs that
            # the Playwright fallback navigates to.
            info = ComixAPI.get_manga_info(code)
            if info and info.slug:
                slug = info.slug
                self._slug_cache[code] = slug
        return ComixAPI.get_all_chapters(code, slug)

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        # chapter.volume holds the reader URL (set by get_all_chapters).
        # If a caller hand-built a Chapter without it, we still try the
        # fast path — it just can't fall back to Playwright.
        return ComixAPI.get_chapter_images(
            chapter.chapter_id, chapter_url=chapter.volume or ""
        )

    @staticmethod
    def _slug_from_url(url: str) -> Optional[str]:
        try:
            path = urlparse(url).path
        except Exception:
            return None
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or parts[0] != "title":
            return None
        last = parts[1]
        if "-" not in last:
            return None
        return last.split("-", 1)[1] or None
