"""
Manga API Bridge - Exposes manga fetching to QML
"""

import sys
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QThread

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class FetchWorker(QThread):
    """Background worker for fetching manga data."""
    
    finished = pyqtSignal(dict)
    chaptersLoaded = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
    
    def run(self):
        try:
            # Import here to avoid circular imports
            from src.providers import get_provider_for_url, SUPPORTED_SITES_HUMAN

            provider = get_provider_for_url(self.url)
            if provider is None:
                self.error.emit(
                    f"Unsupported URL. Supported: {SUPPORTED_SITES_HUMAN}"
                )
                return

            # Extract manga code
            manga_code = provider.extract_code(self.url)

            # Fetch manga info
            manga = provider.get_manga_info(manga_code)
            if not manga:
                self.error.emit("Could not fetch manga information")
                return

            # Convert to dict for QML
            manga_dict = {
                "manga_id": manga.manga_id,
                "hash_id": manga.hash_id,
                "title": manga.title,
                "alt_titles": manga.alt_titles or [],
                "manga_type": manga.manga_type or "Unknown",
                "status": manga.status or "Unknown",
                "poster_url": manga.poster_url or "",
                "year": manga.year or 0,
                "rated_avg": manga.rated_avg or 0,
                "follows_total": manga.follows_total or 0,
                "is_nsfw": manga.is_nsfw,
                "description": manga.description or "",
                "latest_chapter": manga.latest_chapter or "",
                "original_language": manga.original_language or "",
                "manga_code": manga_code,
                "source": manga.source,
                "source_url": manga.source_url or "",
                "artists": manga.artists or [],
                "tags": manga.tags or [],
            }

            self.finished.emit(manga_dict)

            # Fetch chapters
            chapters = provider.get_chapters(manga_code)
            chapters_list = []
            for ch in chapters:
                chapters_list.append({
                    "chapter_id": ch.chapter_id,
                    "number": str(ch.number),
                    "title": ch.title or "",
                    "volume": ch.volume or "",
                    "group_name": ch.group_name or "Unknown",
                    "pages_count": ch.pages_count,
                    "image_urls": ch.image_urls or [],
                    "selected": False,
                })

            self.chaptersLoaded.emit(chapters_list)

        except Exception as e:
            self.error.emit(str(e))


class MangaBridge(QObject):
    """Bridge between Python manga API and QML."""
    
    # Signals to QML
    mangaLoaded = pyqtSignal('QVariant')
    chaptersLoaded = pyqtSignal('QVariant')
    errorOccurred = pyqtSignal(str)
    loadingChanged = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._manga = None
        self._chapters = []
        self._manga_code = ""
    
    @pyqtSlot(result="QVariant")
    def supportedSites(self) -> list:
        """
        Return a static description of every registered provider so the
        URL input can show "what works." Each entry:
        ``{name, label, domains, example_url, auth_required}``.
        """
        from src.providers import list_providers
        out: list[dict] = []
        for cls in list_providers():
            out.append({
                "name": getattr(cls, "name", ""),
                "label": getattr(cls, "label", ""),
                "domains": list(getattr(cls, "domains", ()) or ()),
                "example_url": getattr(cls, "example_url", "") or "",
                # Toomics is the only one currently behind a paywall;
                # surface it so the GUI can mark the chip.
                "auth_required": getattr(cls, "name", "") == "toomics",
            })
        return out

    @pyqtSlot(str, result=str)
    def classifyUrl(self, url: str) -> str:
        """
        Return the provider ``name`` that would handle this URL, or
        empty string. Used by the URL input to live-validate as the
        user types — no network round-trip.
        """
        from src.providers import get_provider_for_url
        provider = get_provider_for_url(url)
        return getattr(provider, "name", "") if provider else ""

    @pyqtSlot(str)
    def fetchManga(self, url: str):
        """Fetch manga info and chapters from URL."""
        from src.providers import get_provider_for_url, SUPPORTED_SITES_HUMAN
        if not url or get_provider_for_url(url) is None:
            self.errorOccurred.emit(
                f"Please enter a supported URL ({SUPPORTED_SITES_HUMAN})"
            )
            return
        
        self.loadingChanged.emit(True)
        
        # Create and start worker thread
        self._worker = FetchWorker(url)
        self._worker.finished.connect(self._on_manga_loaded)
        self._worker.chaptersLoaded.connect(self._on_chapters_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.start()
    
    def _on_manga_loaded(self, manga: dict):
        self._manga = manga
        self._manga_code = manga.get("manga_code", "")
        self.mangaLoaded.emit(manga)
    
    def _on_chapters_loaded(self, chapters: list):
        self._chapters = chapters
        self.chaptersLoaded.emit(chapters)
        self.loadingChanged.emit(False)
    
    def _on_error(self, error: str):
        self.loadingChanged.emit(False)
        self.errorOccurred.emit(error)
    
    @property
    def manga(self):
        return self._manga
    
    @property
    def chapters(self):
        return self._chapters
    
    @property
    def manga_code(self):
        return self._manga_code
