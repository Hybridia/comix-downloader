"""
Download Bridge - Handles download operations between Python and QML
"""

import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
import threading

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class DownloadWorker(QThread):
    """Background worker for downloading chapters concurrently.

    Each worker is owned by a single download "job". Every signal
    carries a ``job_id`` (an opaque string the bridge generates on
    ``startDownload``) as its first argument so the QML side can route
    progress updates to the right job card when multiple downloads
    run concurrently.
    """

    chapterStarted = pyqtSignal(str, str)  # job_id, chapter_name — fires the moment a worker picks it up
    chapterProgress = pyqtSignal(str, str, int, int)  # job_id, chapter_name, current, total
    chapterComplete = pyqtSignal(str, str, bool, str)  # job_id, chapter_name, success, message
    overallProgress = pyqtSignal(str, int, int)  # job_id, completed, total
    finished = pyqtSignal(str, int, int)  # job_id, successful, failed
    error = pyqtSignal(str, str)  # job_id, message
    # Per-job pause/cancel state — see the threading-event design notes
    # in __init__ for what these mean wrt in-flight chapters.
    jobPaused = pyqtSignal(str, bool)  # job_id, paused
    jobCancelled = pyqtSignal(str)  # job_id

    def __init__(self, job_id: str, manga_dict: dict, chapters: list, config, provider):
        super().__init__()
        self.job_id = job_id
        self.manga_dict = manga_dict
        self.chapters = chapters
        self.config = config
        self._provider = provider
        self._lock = threading.Lock()
        self._completed = 0
        self._successful = 0
        self._failed = 0
        # Per-job pause/cancel events. ``_pause_event`` set ⇒ paused;
        # the chapter worker threads block in a pre-work check between
        # chapters. ``_cancel_event`` set ⇒ no further chapters start
        # and any thread waking from pause exits immediately. Both are
        # job-scoped — the global ``src.core.downloader._cancel_event``
        # stays for "cancel everything" callers (e.g. app shutdown).
        #
        # Semantic note: pause/cancel are "between chapters" only.
        # In-flight chapters complete their image batch before the
        # next chapter would have started. Mid-chapter abort would
        # leave partial files we'd have to clean up; not worth the
        # complexity for the UX gain.
        self._pause_event = threading.Event()
        self._cancel_event = threading.Event()
        # Per-run failure log; populated as chapters fail, written at end.
        # Lazy because we need a MangaInfo to know the output path; the
        # actual instance is built in run() once we have one.
        self._failure_log = None

    # ── pause / resume / cancel ──────────────────────────────────────

    def pause(self) -> None:
        if self._cancel_event.is_set():
            return
        was_set = self._pause_event.is_set()
        self._pause_event.set()
        if not was_set:
            self.jobPaused.emit(self.job_id, True)

    def resume(self) -> None:
        if self._cancel_event.is_set():
            return
        was_set = self._pause_event.is_set()
        self._pause_event.clear()
        if was_set:
            self.jobPaused.emit(self.job_id, False)

    def cancel_job(self) -> None:
        if self._cancel_event.is_set():
            return
        self._cancel_event.set()
        # If paused, unblock the waiting worker threads so they can
        # observe the cancel flag and exit.
        self._pause_event.clear()
        self.jobCancelled.emit(self.job_id)

    def _wait_if_paused(self) -> bool:
        """
        Block while paused, return True if the work should continue or
        False if cancel was requested.
        """
        while self._pause_event.is_set():
            if self._cancel_event.is_set():
                return False
            # Short timeout so cancel still feels responsive while paused.
            self._pause_event.wait(timeout=0.5)
        return not self._cancel_event.is_set()

    def _download_single_chapter(self, chapter_dict, manga, total):
        """Download a single chapter. Called from thread pool."""
        # Pre-work pause/cancel check. Done BEFORE the chapterStarted
        # emit so paused-queued chapters don't briefly flash in the
        # active list. If cancel fires while we're queued, we count
        # the chapter as "completed" (skipped) so overall progress
        # still reaches 100% and the job can finish cleanly.
        if not self._wait_if_paused():
            with self._lock:
                self._completed += 1
                completed = self._completed
            self.overallProgress.emit(self.job_id, completed, total)
            return False, f"Chapter {chapter_dict.get('number', '?')}"

        try:
            from src.core.downloader import ChapterDownloader
            from src.core.models import Chapter

            # Convert dict to Chapter object. Preserve `volume` because
            # some providers (toomics) stash the parent series id there
            # so the chapter can be re-fetched without the provider's
            # in-memory cache.
            chapter = Chapter(
                chapter_id=chapter_dict["chapter_id"],
                number=chapter_dict["number"],
                title=chapter_dict.get("title"),
                volume=chapter_dict.get("volume"),
                group_name=chapter_dict.get("group_name"),
                pages_count=chapter_dict.get("pages_count", 0),
                image_urls=list(chapter_dict.get("image_urls") or []),
            )

            chapter_name = chapter.get_display_name()

            # Tell the UI we've picked this chapter up so it shows in
            # the active list immediately. Without this, mangafire
            # chapters stay invisible during the ~10-30 s VRF / cookie
            # capture before any image downloads start.
            self.chapterStarted.emit(self.job_id, chapter_name)

            # Create a callback for image progress
            def on_image_progress(current, total):
                self.chapterProgress.emit(self.job_id, chapter_name, current, total)

            # Download the chapter using the manga's provider
            ch_downloader = ChapterDownloader(self.config, manga, self._provider)
            success, message = ch_downloader.download_chapter(
                chapter,
                on_image_progress=on_image_progress
            )
            
            # Update progress with thread safety
            with self._lock:
                self._completed += 1
                if success:
                    self._successful += 1
                    # Record into the persistent library so the
                    # "Library → Update" flow knows what's already on
                    # disk. Failures here must never block downloads.
                    try:
                        from src.utils.library import shared as _library
                        _library().record_chapter(
                            manga,
                            chapter,
                            self.config.output_format.value,
                            self.config.download_path,
                            manga_code=self.manga_dict.get("manga_code"),
                            library_url=self.manga_dict.get("library_url") or None,
                        )
                    except Exception as exc:
                        from src.utils.logger import get_logger
                        get_logger(__name__).warning(
                            "library record_chapter failed: %s", exc
                        )
                else:
                    self._failed += 1
                    if self._failure_log is not None:
                        self._failure_log.record(chapter, message or "unknown error")
                completed = self._completed
                successful = self._successful
                failed = self._failed
            
            # Emit signals (Qt handles thread safety for signals)
            self.chapterComplete.emit(self.job_id, chapter_name, success, message)
            self.overallProgress.emit(self.job_id, completed, total)

            return success, chapter_name
            
        except Exception as e:
            chapter_name = f"Chapter {chapter_dict.get('number', '?')}"
            with self._lock:
                self._completed += 1
                self._failed += 1
                if self._failure_log is not None:
                    # Reconstruct a minimal Chapter so the log shape stays
                    # consistent with the success path's records.
                    try:
                        from src.core.models import Chapter as _Chapter
                        self._failure_log.record(
                            _Chapter(
                                chapter_id=chapter_dict.get("chapter_id", 0),
                                number=str(chapter_dict.get("number", "?")),
                                title=chapter_dict.get("title"),
                            ),
                            str(e),
                        )
                    except Exception:
                        pass
                completed = self._completed
            
            self.chapterComplete.emit(self.job_id, chapter_name, False, str(e))
            self.overallProgress.emit(self.job_id, completed, total)
            return False, chapter_name
    
    def run(self):
        try:
            from src.core.models import MangaInfo
            from src.core.failure_log import FailureLog

            # Convert dict back to MangaInfo
            manga = MangaInfo(
                manga_id=self.manga_dict.get("manga_id"),
                hash_id=self.manga_dict.get("hash_id"),
                title=self.manga_dict.get("title", "Unknown"),
                alt_titles=self.manga_dict.get("alt_titles", []),
                manga_type=self.manga_dict.get("manga_type"),
                status=self.manga_dict.get("status"),
                poster_url=self.manga_dict.get("poster_url"),
                year=self.manga_dict.get("year"),
                rated_avg=self.manga_dict.get("rated_avg"),
                follows_total=self.manga_dict.get("follows_total"),
                is_nsfw=self.manga_dict.get("is_nsfw", False),
                description=self.manga_dict.get("description", ""),
                source=self.manga_dict.get("source", "comix"),
                source_url=self.manga_dict.get("source_url", ""),
                artists=self.manga_dict.get("artists", []) or [],
                tags=self.manga_dict.get("tags", []) or [],
            )

            self._failure_log = FailureLog(manga, self.config)

            # Make sure the library has an entry for this manga before any
            # chapter completes, so the Library tab shows it even if every
            # chapter happens to fail. Skipped for library updates
            # (``library_url`` set): the entry already exists, and
            # upserting under an alternative site's URL would split the
            # series into a second entry.
            try:
                from src.utils.library import shared as _library
                if not self.manga_dict.get("library_url"):
                    _library().upsert_manga(
                        manga,
                        self.config.output_format.value,
                        self.config.download_path,
                        manga_code=self.manga_dict.get("manga_code"),
                    )
            except Exception as exc:
                from src.utils.logger import get_logger
                get_logger(__name__).warning(
                    "library upsert_manga failed: %s", exc
                )

            total = len(self.chapters)
            max_workers = self.config.max_chapter_workers

            # Use ThreadPoolExecutor for concurrent downloads
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(self._download_single_chapter, ch, manga, total)
                    for ch in self.chapters
                ]

                # Wait for all to complete
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass  # Errors already handled in _download_single_chapter

            # Persist the failure log (or remove the stale one on a clean run).
            try:
                self._failure_log.write()
            except Exception:
                pass

            self.finished.emit(self.job_id, self._successful, self._failed)

        except Exception as e:
            self.error.emit(self.job_id, str(e))


class DownloadBridge(QObject):
    """Bridge for download operations exposed to QML.

    Multiple downloads can run concurrently — each gets its own
    ``DownloadWorker`` and a unique ``job_id``. All per-job signals
    forward the worker's ``job_id`` as their first argument so the
    QML side can route updates to the right job card.
    """

    # `downloadStarted` is the legacy "switch tab + reset panel" trigger.
    # `jobStarted` carries the new per-job metadata that the multi-job
    # progress panel needs to instantiate a card.
    downloadStarted = pyqtSignal()
    jobStarted = pyqtSignal(str, str, str, int)  # job_id, manga_title, poster_url, total_chapters
    chapterStarted = pyqtSignal(str, str)  # job_id, chapter_name
    chapterProgress = pyqtSignal(str, str, int, int)  # job_id, chapter_name, current, total
    chapterComplete = pyqtSignal(str, str, bool, str)  # job_id, chapter_name, success, message
    overallProgress = pyqtSignal(str, int, int)  # job_id, completed, total
    downloadFinished = pyqtSignal(str, int, int)  # job_id, successful, failed
    errorOccurred = pyqtSignal(str)  # human-readable; not job-scoped (e.g. "no chapters selected")
    jobError = pyqtSignal(str, str)  # job_id, message — failures inside an active worker
    jobPaused = pyqtSignal(str, bool)  # job_id, paused — UI flips card status badge
    jobCancelled = pyqtSignal(str)  # job_id — UI marks card as Cancelled
    # Fires when a job dispatched by the Library (manga_dict carries
    # ``library_url``) ends, so the Library card can drop its
    # "Downloading N new chapters…" line. failed == -1 means the
    # worker errored out before finishing.
    libraryJobFinished = pyqtSignal(str, int, int)  # library_url, successful, failed

    def __init__(self, parent=None):
        super().__init__(parent)
        # job_id -> DownloadWorker. Workers self-evict via the
        # finished/error handlers below so this stays bounded.
        self._workers: dict[str, "DownloadWorker"] = {}
        self._next_job_seq = 0
        self._workers_lock = threading.Lock()
        # Import here to avoid circular imports
        from src.utils.config import ConfigManager
        self._config_manager = ConfigManager()

    def _make_job_id(self, manga: dict) -> str:
        """Stable, unique-per-process job id derived from manga + a seq."""
        import time as _time
        with self._workers_lock:
            self._next_job_seq += 1
            seq = self._next_job_seq
        title = (manga or {}).get("title", "manga") or "manga"
        slug = "".join(c if c.isalnum() else "_" for c in title)[:32]
        return f"{int(_time.time() * 1000)}-{seq}-{slug}"

    def _on_job_finished(self, job_id: str, successful: int, failed: int) -> None:
        with self._workers_lock:
            worker = self._workers.pop(job_id, None)
        url = worker.manga_dict.get("library_url") if worker else None
        if url:
            self.libraryJobFinished.emit(url, successful, failed)

    def _on_job_error(self, job_id: str, _message: str) -> None:
        with self._workers_lock:
            worker = self._workers.pop(job_id, None)
        url = worker.manga_dict.get("library_url") if worker else None
        if url:
            self.libraryJobFinished.emit(url, 0, -1)
    
    @pyqtSlot('QVariant', 'QVariant', str, str)
    def startDownload(self, manga: dict, chapters, format_type: str, scanlator: str):
        """
        Start downloading selected chapters concurrently.
        
        Args:
            manga: Manga info dict
            chapters: List of selected chapter dicts (QJSValue from QML)
            format_type: Output format (images/pdf/cbz)
            scanlator: Preferred scanlator or empty for any
        """
        # Convert QJSValue to Python list
        if hasattr(chapters, 'toVariant'):
            chapters = chapters.toVariant()
        if not isinstance(chapters, list):
            chapters = list(chapters) if chapters else []
        
        if not chapters:
            self.errorOccurred.emit("No chapters selected")
            return
        
        # Import here to avoid circular imports
        from src.core.models import OutputFormat
        from src.providers import list_providers
        from src.core.downloader import reset_cancel

        # Pick the provider matching the manga's source
        source = (manga or {}).get("source", "comix")
        provider = None
        for cls in list_providers():
            if getattr(cls, "name", None) == source:
                provider = cls()
                break
        if provider is None:
            self.errorOccurred.emit(f"Unknown source '{source}' for download")
            return

        # Re-prime any provider-side state cached from `extract_code`
        # (e.g. the toomics provider's parent toon id). This is the same
        # call MangaBridge made when fetching the listing; re-running it
        # on the fresh provider instance restores that cache.
        source_url = (manga or {}).get("source_url") or ""
        if source_url:
            try:
                provider.extract_code(source_url)
            except Exception:
                pass

        reset_cancel()

        # Get config and update format
        config = self._config_manager.get_download_config()
        config.output_format = OutputFormat(format_type)
        
        # Filter by scanlator preference if specified
        if scanlator and scanlator != "Any":
            filtered = []
            seen_numbers = set()
            # Prioritize chapters from preferred scanlator
            for ch in chapters:
                if ch.get("group_name") == scanlator and ch["number"] not in seen_numbers:
                    filtered.append(ch)
                    seen_numbers.add(ch["number"])
            # Add remaining chapters for numbers not covered
            for ch in chapters:
                if ch["number"] not in seen_numbers:
                    filtered.append(ch)
                    seen_numbers.add(ch["number"])
            chapters = filtered
        else:
            # Get unique chapters by number
            seen = set()
            unique = []
            for ch in chapters:
                if ch["number"] not in seen:
                    unique.append(ch)
                    seen.add(ch["number"])
            chapters = unique
        
        # `downloadStarted` no longer resets the whole panel — with
        # multiple jobs in flight, that would clobber other in-progress
        # downloads. The QML side now uses it only to switch tabs;
        # `jobStarted` is what tells the panel to create a card.
        self.downloadStarted.emit()

        job_id = self._make_job_id(manga)
        self.jobStarted.emit(
            job_id,
            (manga or {}).get("title", "Unknown"),
            (manga or {}).get("poster_url", "") or "",
            len(chapters),
        )

        # Create and start worker with concurrent downloads
        worker = DownloadWorker(job_id, manga, chapters, config, provider)
        worker.chapterStarted.connect(self.chapterStarted.emit)
        worker.chapterProgress.connect(self.chapterProgress.emit)
        worker.chapterComplete.connect(self.chapterComplete.emit)
        worker.overallProgress.connect(self.overallProgress.emit)
        worker.finished.connect(self.downloadFinished.emit)
        worker.error.connect(self.jobError.emit)
        worker.jobPaused.connect(self.jobPaused.emit)
        worker.jobCancelled.connect(self.jobCancelled.emit)
        # Self-evict from the workers dict on finish/error so we don't
        # leak references to completed QThreads.
        worker.finished.connect(self._on_job_finished)
        worker.error.connect(self._on_job_error)
        with self._workers_lock:
            self._workers[job_id] = worker
        worker.start()
    
    @pyqtSlot(str)
    def pauseJob(self, job_id: str) -> None:
        """Pause one job — stops scheduling new chapters; in-flight finish."""
        with self._workers_lock:
            worker = self._workers.get(job_id)
        if worker is not None and worker.isRunning():
            worker.pause()

    @pyqtSlot(str)
    def resumeJob(self, job_id: str) -> None:
        """Resume a paused job."""
        with self._workers_lock:
            worker = self._workers.get(job_id)
        if worker is not None and worker.isRunning():
            worker.resume()

    @pyqtSlot(str)
    def cancelJob(self, job_id: str) -> None:
        """Cancel one job — no new chapters start; in-flight finish normally."""
        with self._workers_lock:
            worker = self._workers.get(job_id)
        if worker is not None and worker.isRunning():
            worker.cancel_job()

    @pyqtSlot()
    def cancelDownload(self):
        """Cancel every in-progress download.

        The cancel signal in :mod:`src.core.downloader` is process-wide
        (a module-level ``threading.Event``), so per-job cancellation
        would require plumbing — and there's no UI today that asks for
        it. Cancel-all matches the existing single-worker behaviour
        when only one download is active.
        """
        from src.core.downloader import cancel_downloads
        try:
            cancel_downloads()
        except Exception:
            pass
        with self._workers_lock:
            workers = list(self._workers.values())
        for w in workers:
            if w.isRunning():
                w.terminate()
                w.wait()
        with self._workers_lock:
            self._workers.clear()
