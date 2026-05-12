"""
Library Bridge — exposes the persistent download library to QML.

Responsibilities:

- ``listEntries()``      — return everything we've recorded.
- ``updateEntry(url)``   — re-fetch the manga, diff against stored
                            chapter numbers, and hand the *new* chapters
                            to ``DownloadBridge.startDownload`` so the
                            existing pipeline (per-host rate limiter,
                            failure log, library recording) handles them.
- ``removeEntry(url)``   — drop an entry from the library (does NOT
                            touch the on-disk artifacts).
- ``openFolder(url)``    — open the manga's download folder in the OS
                            file manager.

Update probes happen on a worker thread (``UpdateProbeWorker``) because
the provider hits the network and may take several seconds, especially
for sites that need Playwright. The worker emits ``probeFinished`` and
the bridge — back on the GUI thread — either kicks off the download or
emits ``noUpdatesAvailable``.
"""

import sys
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _manga_info_to_dict(manga, manga_code: str) -> dict:
    """Mirror MangaBridge's manga_dict shape so DownloadBridge
    accepts it untouched."""
    return {
        "manga_id": manga.manga_id,
        "hash_id": manga.hash_id,
        "title": manga.title,
        "alt_titles": list(manga.alt_titles or []),
        "manga_type": manga.manga_type or "Unknown",
        "status": manga.status or "Unknown",
        "poster_url": manga.poster_url or "",
        "year": manga.year or 0,
        "rated_avg": manga.rated_avg or 0,
        "follows_total": manga.follows_total or 0,
        "is_nsfw": bool(manga.is_nsfw),
        "description": manga.description or "",
        "latest_chapter": manga.latest_chapter or "",
        "original_language": manga.original_language or "",
        "manga_code": manga_code,
        "source": manga.source,
        "source_url": manga.source_url or "",
        "artists": list(manga.artists or []),
        "tags": list(manga.tags or []),
    }


def _chapter_to_dict(ch) -> dict:
    return {
        "chapter_id": ch.chapter_id,
        "number": str(ch.number),
        "title": ch.title or "",
        "volume": ch.volume or "",
        "group_name": ch.group_name or "Unknown",
        "pages_count": ch.pages_count,
        "image_urls": list(ch.image_urls or []),
        "selected": True,
    }


class RepackWorker(QThread):
    """
    Background worker that packs a manga's image folders into CBZs.
    Idempotent — already-CBZ'd chapters are skipped. Source images
    are NEVER deleted; the user can do that manually if desired.
    """

    # source_url, total_chapters
    started = pyqtSignal(str, int)
    # source_url, done, total
    progress = pyqtSignal(str, int, int)
    # source_url, created, skipped, failed
    completed = pyqtSignal(str, int, int, int)
    # source_url, error_message
    failed = pyqtSignal(str, str)

    def __init__(self, source_url: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.source_url = source_url

    def run(self) -> None:
        try:
            from src.utils.library import shared as _library
            from src.utils.repack import (
                manga_info_from_library_entry,
                repack_manga,
            )

            entry = _library().get_entry(self.source_url)
            if not entry:
                self.failed.emit(
                    self.source_url,
                    "No library entry for this URL — was it removed?",
                )
                return

            download_path = Path(entry.get("download_path") or "downloads")
            folder = entry.get("folder") or ""
            manga_dir = download_path / folder if folder else download_path
            if not manga_dir.is_dir():
                self.failed.emit(
                    self.source_url,
                    f"Folder not found: {manga_dir}",
                )
                return

            manga = manga_info_from_library_entry(entry, manga_dir.name)

            # Forward per-chapter progress as bridge signals. We emit
            # `started` with the total once we get the "start" event so
            # the UI knows how big the job is.
            def _on_progress(_chapter_name: str, done: int, total: int, status: str) -> None:
                if status == "start":
                    self.started.emit(self.source_url, total)
                    return
                self.progress.emit(self.source_url, done, total)

            result = repack_manga(
                manga_dir,
                manga,
                library_entry=entry,
                delete_images=False,
                on_progress=_on_progress,
            )

            # If anything was created (or everything was already CBZ),
            # update the entry's output_format so the Convert button
            # hides on the next Library refresh.
            if result.failed == 0:
                try:
                    _library().set_output_format(self.source_url, "cbz")
                except Exception:
                    pass

            self.completed.emit(
                self.source_url, result.created, result.skipped, result.failed,
            )
        except Exception as exc:
            self.failed.emit(self.source_url, str(exc))


class UpdateProbeWorker(QThread):
    """Fetch the latest chapter list and diff against the library."""

    # source_url, manga_dict, new_chapters (list[dict]), total_remote,
    # total_already_downloaded, error_message_or_empty
    probeFinished = pyqtSignal(str, dict, list, int, int, str)

    def __init__(self, source_url: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.source_url = source_url

    def run(self) -> None:
        try:
            from src.providers import get_provider_for_url, SUPPORTED_SITES_HUMAN
            from src.utils.library import shared as _library

            provider = get_provider_for_url(self.source_url)
            if provider is None:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0,
                    f"Unsupported source URL. Known: {SUPPORTED_SITES_HUMAN}",
                )
                return

            code = provider.extract_code(self.source_url)
            manga = provider.get_manga_info(code)
            if not manga:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0,
                    "Provider returned no manga info; the gallery may have been removed.",
                )
                return

            chapters = provider.get_chapters(code) or []
            known = _library().downloaded_chapter_numbers(self.source_url)

            new_chapters = [c for c in chapters if str(c.number) not in known]
            new_dicts = [_chapter_to_dict(c) for c in new_chapters]
            manga_dict = _manga_info_to_dict(manga, code)

            try:
                _library().mark_checked(self.source_url)
            except Exception:
                pass

            self.probeFinished.emit(
                self.source_url, manga_dict, new_dicts,
                len(chapters), len(chapters) - len(new_chapters), "",
            )

        except Exception as exc:
            self.probeFinished.emit(self.source_url, {}, [], 0, 0, str(exc))


class LibraryBridge(QObject):
    """QObject exposed to QML as ``LibraryBridge``."""

    entriesChanged = pyqtSignal()
    updateStarted = pyqtSignal(str, str, int)            # url, title, new_chapter_count
    noUpdatesAvailable = pyqtSignal(str, str)            # url, title
    updateFailed = pyqtSignal(str, str)                  # url, error_message
    repackStarted = pyqtSignal(str, int)                 # url, total_chapters
    repackProgress = pyqtSignal(str, int, int)           # url, done, total
    repackFinished = pyqtSignal(str, int, int, int)      # url, created, skipped, failed
    repackFailed = pyqtSignal(str, str)                  # url, error_message

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Set after construction by main.py — we can't import the
        # download bridge at module top because it's a sibling.
        self._download_bridge = None
        # Hold worker references so QThread isn't garbage-collected
        # mid-run.
        self._workers: list[UpdateProbeWorker] = []
        self._repack_workers: list[RepackWorker] = []

    def attach_download_bridge(self, download_bridge) -> None:
        """Wire the DownloadBridge so update probes can launch downloads."""
        self._download_bridge = download_bridge

    # --- QML slots ---------------------------------------------------

    @pyqtSlot(result="QVariant")
    def listEntries(self) -> list:
        from src.utils.library import shared as _library
        # Return entries newest-first by last_updated_at so the GUI
        # naturally surfaces the most-recently-touched manga at the top.
        entries = _library().list_entries()
        entries.sort(
            key=lambda e: e.get("last_updated_at") or e.get("added_at") or "",
            reverse=True,
        )
        # Annotate with a chapter count for QML convenience.
        for e in entries:
            e["chapter_count"] = len(e.get("chapters", {}) or {})
        return entries

    @pyqtSlot(str)
    def removeEntry(self, source_url: str) -> None:
        from src.utils.library import shared as _library
        if _library().remove_entry(source_url):
            self.entriesChanged.emit()

    @pyqtSlot(str)
    def openFolder(self, source_url: str) -> None:
        """Reveal the manga's download folder in the OS file manager."""
        from src.utils.library import shared as _library
        entry = _library().get_entry(source_url)
        if not entry:
            return
        download_path = Path(entry.get("download_path") or "downloads")
        folder = entry.get("folder") or ""
        target = download_path / folder if folder else download_path
        if not target.exists():
            target = download_path  # fall back to the parent
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception:
            pass

    @pyqtSlot(str)
    def convertToCbz(self, source_url: str) -> None:
        """
        Pack every chapter folder of this manga into a sibling .cbz.
        Runs on a worker thread so the UI stays responsive. Source
        image folders are kept intact; user can clean them up manually
        if they want to reclaim space.
        """
        worker = RepackWorker(source_url, self)
        worker.started.connect(self.repackStarted.emit)
        worker.progress.connect(self.repackProgress.emit)
        worker.completed.connect(self._on_repack_completed)
        worker.failed.connect(self.repackFailed.emit)
        worker.finished.connect(lambda w=worker: self._reap_repack(w))
        self._repack_workers.append(worker)
        worker.start()

    def _on_repack_completed(
        self, source_url: str, created: int, skipped: int, failed: int
    ) -> None:
        self.repackFinished.emit(source_url, created, skipped, failed)
        # If we updated the output_format, refresh the list so the UI
        # hides the Convert button + shows the new format badge.
        if failed == 0:
            self.entriesChanged.emit()

    def _reap_repack(self, worker: "RepackWorker") -> None:
        try:
            self._repack_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    @pyqtSlot(str)
    def updateEntry(self, source_url: str) -> None:
        """
        Probe the source for new chapters and, if any are found, hand
        them to DownloadBridge for the standard download pipeline.
        """
        worker = UpdateProbeWorker(source_url, self)
        worker.probeFinished.connect(self._on_probe_finished)
        worker.finished.connect(lambda w=worker: self._reap(w))
        self._workers.append(worker)
        worker.start()

    # --- Internal ----------------------------------------------------

    def _reap(self, worker: UpdateProbeWorker) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _on_probe_finished(
        self,
        source_url: str,
        manga_dict: dict,
        new_chapters: list,
        total_remote: int,
        total_known: int,
        error: str,
    ) -> None:
        if error:
            self.updateFailed.emit(source_url, error)
            return

        title = (manga_dict or {}).get("title", "Unknown")

        if not new_chapters:
            self.noUpdatesAvailable.emit(source_url, title)
            return

        if self._download_bridge is None:
            self.updateFailed.emit(
                source_url,
                "Internal: DownloadBridge not wired into LibraryBridge.",
            )
            return

        # Reuse the format the user originally chose for this manga.
        from src.utils.library import shared as _library
        entry = _library().get_entry(source_url) or {}
        fmt = entry.get("output_format") or "cbz"

        self.updateStarted.emit(source_url, title, len(new_chapters))
        self._download_bridge.startDownload(manga_dict, new_chapters, fmt, "Any")
