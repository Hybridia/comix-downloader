"""
Provider base class. Each site implements these methods so the CLI/GUI/
download pipeline can stay site-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Optional
from ..core.models import MangaInfo, Chapter


class Provider(ABC):
    """Abstract base class for a manga source provider."""

    # Short identifier used in MangaInfo.source and folder paths
    name: str = "base"
    # Human-readable label shown in CLI/GUI
    label: str = "Base"
    # Domains this provider answers to (router uses these as hints)
    domains: tuple[str, ...] = ()
    # Referer header to send when fetching images from this site
    image_referer: str = ""
    # Example URL used by the GUI to show what a valid URL looks like
    # for this provider. Empty string is allowed but discouraged.
    example_url: str = ""

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """Return True if `url` should be handled by this provider."""

    @abstractmethod
    def extract_code(self, url: str) -> str:
        """Extract the canonical id (manga code / gallery id) from a URL."""

    @abstractmethod
    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        """Fetch top-level manga / gallery metadata."""

    @abstractmethod
    def get_chapters(self, code: str) -> list[Chapter]:
        """Return all chapters for a manga / gallery in ascending order."""

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        """
        Return image URLs for a chapter. Default uses pre-cached urls if
        the provider attached them when listing chapters; subclasses with
        a separate per-chapter API endpoint should override.
        """
        if chapter.image_urls:
            return list(chapter.image_urls)
        raise NotImplementedError(
            f"{type(self).__name__} must implement get_chapter_images"
        )

    def chapter_request_headers(self) -> dict:
        """Headers to attach when fetching images for this provider."""
        if self.image_referer:
            return {"Referer": self.image_referer}
        return {}
