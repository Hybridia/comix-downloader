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

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# On-disk chapter discovery lives in ``src/utils/chapters.py`` (shared
# with the update checker + source detection). The underscore aliases
# are kept because ``scripts/missing_chapters.py`` and friends import
# them from here.
from src.utils.chapters import (  # noqa: E402
    FILENAME_CHAPTER_RE as _FILENAME_CHAPTER_RE,
    chapter_numbers_on_disk as _chapter_numbers_on_disk,
    max_chapter as _max_chapter,
    norm_chapter_number as _norm_chapter_number,
)


from src.utils.update_check import (  # noqa: E402
    chapter_to_dict as _chapter_to_dict,
    manga_info_to_dict as _manga_info_to_dict,
)

# Results of the last "Check for Updates" run, kept so the review list
# survives an app restart (a full-library check can take a while).
# Gitignored — it's a list of the user's series.
_PENDING_PATH = Path(__file__).resolve().parents[2] / "pending_updates.json"


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


class StatusCheckWorker(QThread):
    """
    Lightweight probe that ONLY refreshes the library's status_auto
    for a single entry. Calls ``provider.get_manga_info()`` (which
    carries the ``status`` field) and stamps ``mark_checked`` —
    deliberately does NOT fetch the chapter list or dispatch any
    download, unlike ``UpdateProbeWorker``.

    Used by ``LibraryBridge.checkStatusAll()`` so the user can refresh
    completion badges across the library without re-downloading
    chapters they're missing.
    """

    # url, normalized_status, raw_status, error_message_or_empty
    finished_one = pyqtSignal(str, str, str, str)

    def __init__(self, source_url: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.source_url = source_url

    def run(self) -> None:
        try:
            from src.providers import get_provider_for_url, SUPPORTED_SITES_HUMAN
            from src.utils.library import (
                shared as _library, normalize_status,
            )

            provider = get_provider_for_url(self.source_url)
            if provider is None:
                self.finished_one.emit(
                    self.source_url, "", "",
                    f"Unsupported source URL. Known: {SUPPORTED_SITES_HUMAN}",
                )
                return

            code = provider.extract_code(self.source_url)
            manga = provider.get_manga_info(code)
            if not manga:
                self.finished_one.emit(
                    self.source_url, "", "",
                    "Provider returned no manga info; the gallery may have been removed.",
                )
                return

            raw = getattr(manga, "status", None) or ""
            try:
                _library().mark_checked(
                    self.source_url, manga_status=raw,
                )
            except Exception:
                pass

            self.finished_one.emit(
                self.source_url, normalize_status(raw), raw, "",
            )

        except Exception as exc:
            self.finished_one.emit(self.source_url, "", "", str(exc))


class UpdateProbeWorker(QThread):
    """
    Probe a library entry for new chapters.

    Update model — *as of 2026-05-15 rework*:

    - **Ground truth = files on disk**, not ``library.chapters``.
      We scan ``download_path / folder`` for ``.cbz`` files and use
      those filenames as the "what I have" set. Normalised so that
      ``Chapter_62.5.cbz`` (iCloud's dot convention) and
      ``chapter-62-5`` (Madara's hyphen convention) compare equal.
    - **Empty / missing folder ⇒ no Update.** A library entry whose
      target folder has zero CBZs (e.g. an old in-app download the
      user abandoned) silently reports "no updates" — re-downloading
      a hundred chapters into ``./downloads/`` was the bug we just
      fixed.
    - **Cross-site fallback**: if the primary site returns no
      chapters whose normalised number is missing from disk, walk
      ``entry["alternative_sources"]`` (already sorted by chapter
      count desc by the enricher). The first alt whose ``max_chapter``
      strictly exceeds the on-disk max wins — we use ITS chapter list
      to compute the new-chapters diff, and the download bridge ends
      up pointing at the alt's provider/url.

    The worker still emits the same ``probeFinished`` signal shape;
    the LibraryBridge dispatches new chapters via ``startDownload``
    just like before.
    """

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

            # Look up the library entry for the on-disk path + alts.
            entry = _library().get_entry(self.source_url) or {}

            on_disk_folder = self._on_disk_folder(entry)
            on_disk_chapters = (
                _chapter_numbers_on_disk(on_disk_folder)
                if on_disk_folder
                else set()
            )

            # Guard: empty target folder ⇒ no update. Library entries
            # for series the user has abandoned (no CBZs anywhere)
            # don't get to re-download.
            if not on_disk_chapters:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0, "",
                )
                return

            on_disk_max = _max_chapter(on_disk_chapters)

            # ── Primary probe ────────────────────────────────────────
            primary_provider = get_provider_for_url(self.source_url)
            if primary_provider is None:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0,
                    f"Unsupported source URL. Known: {SUPPORTED_SITES_HUMAN}",
                )
                return

            try:
                primary_code = primary_provider.extract_code(self.source_url)
                primary_manga = primary_provider.get_manga_info(primary_code)
            except Exception as exc:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0,
                    f"Primary probe failed: {exc}",
                )
                return

            if not primary_manga:
                self.probeFinished.emit(
                    self.source_url, {}, [], 0, 0,
                    "Provider returned no manga info; the gallery may have been removed.",
                )
                return

            try:
                _library().mark_checked(
                    self.source_url,
                    manga_status=getattr(primary_manga, "status", None),
                )
            except Exception:
                pass

            primary_chapters = primary_provider.get_chapters(primary_code) or []
            new_chapters = self._diff_against_disk(
                primary_chapters, on_disk_chapters,
            )

            # ── Cross-site fallback ──────────────────────────────────
            # Only when the primary site has nothing new for us AND
            # the entry has alternative sources to try. We pick the
            # first alt whose recorded max chapter clearly exceeds
            # what's on disk (avoids re-probing every alt for nothing).
            picked_alt_url: Optional[str] = None
            if not new_chapters:
                for alt in entry.get("alternative_sources") or []:
                    alt_max = float(alt.get("chapter_count") or 0)
                    if alt_max <= on_disk_max:
                        continue
                    alt_url = alt.get("url")
                    if not alt_url or alt_url == self.source_url:
                        continue
                    alt_prov = get_provider_for_url(alt_url)
                    if alt_prov is None:
                        continue
                    try:
                        alt_code = alt_prov.extract_code(alt_url)
                        alt_chapters = alt_prov.get_chapters(alt_code) or []
                    except Exception:
                        continue
                    candidates = self._diff_against_disk(
                        alt_chapters, on_disk_chapters,
                    )
                    if candidates:
                        new_chapters = candidates
                        picked_alt_url = alt_url
                        # Re-fetch manga info on the alt provider so
                        # the download dispatch points at the right
                        # site. Cheaper than re-probing the chapter
                        # list since we just fetched it above.
                        try:
                            alt_manga = alt_prov.get_manga_info(alt_code)
                            if alt_manga:
                                primary_manga = alt_manga
                                primary_provider = alt_prov
                                primary_code = alt_code
                        except Exception:
                            pass
                        break

            new_dicts = [_chapter_to_dict(c) for c in new_chapters]
            manga_dict = _manga_info_to_dict(primary_manga, primary_code)

            # If we fell back to an alt, the manga_dict's source_url
            # is the alt's — which is what we want so the downloader
            # uses the right provider / referer / etc.
            self.probeFinished.emit(
                self.source_url, manga_dict, new_dicts,
                len(primary_chapters) if not picked_alt_url else len(new_chapters) + len(on_disk_chapters),
                len(on_disk_chapters),
                "",
            )

        except Exception as exc:
            self.probeFinished.emit(self.source_url, {}, [], 0, 0, str(exc))

    @staticmethod
    def _on_disk_folder(entry: dict) -> Optional[Path]:
        """
        Compute the folder this library entry's chapters live in.
        For iCloud-imported entries that's the iCloud subfolder; for
        in-app downloads it's ``./downloads/<safe_title>/``. Returns
        ``None`` if the entry is malformed.
        """
        if not entry:
            return None
        dp = entry.get("download_path") or ""
        folder = entry.get("folder") or ""
        if not dp or not folder:
            return None
        return Path(dp) / folder

    @staticmethod
    def _diff_against_disk(chapters: list, on_disk: set[str]) -> list:
        """
        Filter ``chapters`` (a list of Chapter objects from a
        provider) to only those whose normalised number is NOT in
        the on-disk set.
        """
        out = []
        for ch in chapters:
            n = _norm_chapter_number(getattr(ch, "number", ""))
            if n and n not in on_disk:
                out.append(ch)
        return out


class UpdateCheckWorker(QThread):
    """
    Runs ``check_entry`` over a list of library entries, one at a time
    (politeness — and Playwright providers can't run in parallel).
    Never downloads: results go back to the bridge for the user to
    review in the Updates view.
    """

    # done (1-based), total, library_url, title
    progress = pyqtSignal(int, int, str, str)
    # library_url, result dict
    resultReady = pyqtSignal(str, dict)

    def __init__(self, urls: list[str], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.urls = urls
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        from src.utils.library import shared as _library
        from src.utils.update_check import check_entry

        total = len(self.urls)
        for i, url in enumerate(self.urls):
            if self._cancel:
                break
            entry = _library().get_entry(url) or {}
            self.progress.emit(i + 1, total, url, entry.get("title") or url)
            try:
                result = check_entry(entry, cancelled=lambda: self._cancel)
            except Exception as exc:
                result = {"library_url": url, "title": entry.get("title") or url,
                          "sources": [], "recommended": -1, "error": str(exc)}
            self.resultReady.emit(url, result)


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
    # Bulk "Update All" lifecycle. Probes run sequentially (one at a
    # time) to be polite to providers; downloads that result from them
    # are kicked off as soon as each probe lands, so retrieval runs in
    # parallel with the remaining probes via the normal DownloadBridge.
    updateAllStarted = pyqtSignal(int, int)              # total, skipped_completed
    updateAllProgress = pyqtSignal(int, int, str, str)   # done, total, current_url, current_title
    updateAllFinished = pyqtSignal(int, int, int, int)   # with_updates, up_to_date, failed, skipped_completed
    # Bulk "Check Status All" — like Update All but never triggers
    # downloads. Lightweight (manga info only, no chapter list).
    statusCheckAllStarted = pyqtSignal(int)              # total
    statusCheckAllProgress = pyqtSignal(int, int, str, str)  # done, total, url, title
    statusCheckAllFinished = pyqtSignal(int, int, int, int)  # completed, ongoing, unknown, failed
    # "Check for Updates" — probe-only; results wait in the Updates
    # view until the user approves them (``applyUpdates``).
    updateCheckStarted = pyqtSignal(int, int)            # total, skipped_completed
    updateCheckProgress = pyqtSignal(int, int, str, str)  # done, total, url, title
    updateCheckFinished = pyqtSignal(int, int, int, int, int)  # with_updates, up_to_date, failed, skipped_completed, no_files
    pendingUpdatesChanged = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Set after construction by main.py — we can't import the
        # download bridge at module top because it's a sibling.
        self._download_bridge = None
        # Hold worker references so QThread isn't garbage-collected
        # mid-run.
        self._workers: list[UpdateProbeWorker] = []
        self._repack_workers: list[RepackWorker] = []
        # Bulk "Update All" state. Idle when _bulk_urls is empty.
        self._bulk_urls: list[str] = []
        self._bulk_idx: int = 0
        # Tally: [with_updates, up_to_date, failed, skipped_completed]
        self._bulk_stats: list[int] = [0, 0, 0, 0]
        self._bulk_cancel: bool = False
        # Bulk "Check Status All" state. Independent of Update All so
        # both could run in parallel in principle — but the QML drives
        # them mutually exclusively to avoid hammering providers.
        self._status_urls: list[str] = []
        self._status_idx: int = 0
        # Tally: [completed, ongoing, unknown, failed]
        self._status_stats: list[int] = [0, 0, 0, 0]
        self._status_cancel: bool = False
        self._status_workers: list[StatusCheckWorker] = []
        # "Check for Updates" state. ``_pending`` maps library_url →
        # check result (only entries that HAVE updates are kept).
        self._check_worker: Optional[UpdateCheckWorker] = None
        # Tally: [with_updates, up_to_date, failed, skipped_completed, no_files]
        self._check_stats: list[int] = [0, 0, 0, 0, 0]
        self._pending: dict[str, dict] = {}
        self._pending_checked_at: str = ""
        self._load_pending()

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
    def openWebsite(self, source_url: str) -> None:
        """
        Open the comic's source page in the user's default browser.

        Uses ``webbrowser.open`` for portability (cross-platform,
        respects user defaults). We pass the URL straight from the
        library entry — the library normalises it on insert so it's
        always an absolute https:// URL.
        """
        if not source_url:
            return
        try:
            import webbrowser
            webbrowser.open(source_url)
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

    @pyqtSlot(str, str, bool)
    def setStatus(self, source_url: str, status: str, manual: bool) -> None:
        """
        Update an entry's status. ``manual=True`` flags the value as a
        user override so the auto-tracker won't replace it on the next
        probe; pass ``manual=False`` to clear the override (the next
        probe will re-sync from the provider).

        Accepts any user-typed string; the library normalises it.
        ``""`` clears the status entirely.
        """
        from src.utils.library import shared as _library
        if _library().set_status(source_url, status, manual=manual):
            self.entriesChanged.emit()

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

    @pyqtSlot()
    def updateAll(self) -> None:
        """
        Probe every library entry for new chapters, one at a time.
        Entries with a "completed" or "cancelled" status are skipped
        (the site won't have new chapters for them) — both auto-tracked
        status and a user "Mark as completed" override count here.

        Each non-skipped probe still goes through the normal per-entry
        handler, so per-card status messages, download dispatch, and
        last_checked_at bookkeeping behave exactly as a manual update.
        """
        if self._bulk_urls:
            # A bulk run is already in flight — second click is a no-op.
            return

        from src.utils.library import shared as _library
        from src.utils.library import is_finished_status

        entries = _library().list_entries()
        urls: list[str] = []
        skipped = 0
        for e in entries:
            url = e.get("source_url")
            if not url:
                continue
            if is_finished_status(e.get("status") or ""):
                skipped += 1
                continue
            urls.append(url)

        # Always emit a started/finished pair so the GUI can show a
        # summary (even when everything is completed and there's
        # nothing to probe).
        self.updateAllStarted.emit(len(urls), skipped)

        if not urls:
            self._bulk_stats = [0, 0, 0, skipped]
            self.updateAllFinished.emit(*self._bulk_stats)
            return

        self._bulk_urls = urls
        self._bulk_idx = 0
        self._bulk_stats = [0, 0, 0, skipped]
        self._bulk_cancel = False
        self._run_next_bulk()

    @pyqtSlot()
    def cancelUpdateAll(self) -> None:
        """Stop after the in-flight probe finishes."""
        if self._bulk_urls:
            self._bulk_cancel = True

    @pyqtSlot()
    def checkStatusAll(self) -> None:
        """
        Probe every library entry's status WITHOUT triggering any
        downloads. Lighter than ``updateAll()`` — fetches manga info
        only, skips the chapter list / diff / download pipeline.

        Use this to refresh "Completed / Ongoing" badges across the
        library after marking some manually, without committing to
        re-fetching any chapters you might be missing.
        """
        if self._status_urls:
            # Already running.
            return

        from src.utils.library import shared as _library
        entries = _library().list_entries()
        urls = [e.get("source_url") for e in entries if e.get("source_url")]

        if not urls:
            self.statusCheckAllFinished.emit(0, 0, 0, 0)
            return

        self._status_urls = urls
        self._status_idx = 0
        self._status_stats = [0, 0, 0, 0]
        self._status_cancel = False
        self.statusCheckAllStarted.emit(len(urls))
        self._run_next_status_check()

    @pyqtSlot()
    def cancelCheckStatusAll(self) -> None:
        """Stop after the in-flight status probe finishes."""
        if self._status_urls:
            self._status_cancel = True

    def _run_next_status_check(self) -> None:
        if self._status_cancel or self._status_idx >= len(self._status_urls):
            self.statusCheckAllFinished.emit(*self._status_stats)
            self._status_urls = []
            self._status_idx = 0
            self._status_cancel = False
            return

        url = self._status_urls[self._status_idx]

        # Friendly title for the header banner — pulled from the
        # library cache, same trick as updateAll.
        from src.utils.library import shared as _library
        entry = _library().get_entry(url) or {}
        title = entry.get("title") or url
        self.statusCheckAllProgress.emit(
            self._status_idx + 1, len(self._status_urls), url, title,
        )

        worker = StatusCheckWorker(url, self)
        worker.finished_one.connect(self._on_status_check_one_finished)
        worker.finished.connect(lambda w=worker: self._reap_status(w))
        self._status_workers.append(worker)
        worker.start()

    def _on_status_check_one_finished(
        self, url: str, normalized: str, raw: str, error: str,
    ) -> None:
        # Bucket the result for the summary.
        if error:
            self._status_stats[3] += 1
        elif normalized in ("completed", "cancelled"):
            self._status_stats[0] += 1
        elif normalized == "ongoing":
            self._status_stats[1] += 1
        else:
            # hiatus / unknown / "" — still counts as "checked but
            # nothing actionable for the skip-on-Update-All purpose."
            self._status_stats[2] += 1

        # Refresh the cached entries view so the badge updates
        # immediately. (One emit per probe, like the Update All
        # flow — cheap enough at this scale.)
        self.entriesChanged.emit()

        self._status_idx += 1
        self._run_next_status_check()

    def _reap_status(self, worker: "StatusCheckWorker") -> None:
        try:
            self._status_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _run_next_bulk(self) -> None:
        if self._bulk_cancel or self._bulk_idx >= len(self._bulk_urls):
            # Finished (cleanly or cancelled). Emit summary and reset.
            self.updateAllFinished.emit(*self._bulk_stats)
            self._bulk_urls = []
            self._bulk_idx = 0
            self._bulk_cancel = False
            return

        url = self._bulk_urls[self._bulk_idx]

        # Use the cached library title so the header can show
        # "Checking 7 of 47: <title>" while the probe is running.
        from src.utils.library import shared as _library
        entry = _library().get_entry(url) or {}
        title = entry.get("title") or url
        self.updateAllProgress.emit(
            self._bulk_idx + 1, len(self._bulk_urls), url, title,
        )

        worker = UpdateProbeWorker(url, self)
        worker.probeFinished.connect(self._on_bulk_probe_finished)
        worker.finished.connect(lambda w=worker: self._reap(w))
        self._workers.append(worker)
        worker.start()

    def _on_bulk_probe_finished(
        self,
        source_url: str,
        manga_dict: dict,
        new_chapters: list,
        total_remote: int,
        total_known: int,
        error: str,
    ) -> None:
        # Tally results for the header summary.
        if error:
            self._bulk_stats[2] += 1
        elif new_chapters:
            self._bulk_stats[0] += 1
        else:
            self._bulk_stats[1] += 1
        # Forward to the normal per-entry handler — same per-card
        # status messages + download dispatch as a manual Update click.
        self._on_probe_finished(
            source_url, manga_dict, new_chapters, total_remote, total_known, error,
        )
        # Advance to the next URL.
        self._bulk_idx += 1
        self._run_next_bulk()

    # --- Check for Updates (review before download) -----------------

    @pyqtSlot()
    def checkForUpdates(self) -> None:
        """
        Probe every followed series for new chapters WITHOUT
        downloading. Results land in the Updates view; nothing is
        fetched until ``applyUpdates``. Completed / cancelled series are
        skipped, same as Update All.
        """
        if self._check_worker is not None:
            return

        from src.utils.library import shared as _library, is_finished_status

        urls, skipped = [], 0
        entries = sorted(_library().list_entries(),
                         key=lambda e: (e.get("title") or "").lower())
        for e in entries:
            url = e.get("source_url")
            if not url:
                continue
            if is_finished_status(e.get("status") or ""):
                skipped += 1
                continue
            urls.append(url)

        self._start_check(urls, skipped)

    @pyqtSlot("QVariant")
    def checkForUpdatesFor(self, urls) -> None:
        """
        Check only the series the user ticked in the Library. Unlike
        ``checkForUpdates`` this does NOT skip completed series —
        ticking one is an explicit request to look anyway.
        """
        if self._check_worker is not None:
            return
        if hasattr(urls, "toVariant"):
            urls = urls.toVariant()
        from src.utils.library import shared as _library
        wanted = {str(u) for u in urls or [] if u}
        ordered = [
            e["source_url"]
            for e in sorted(_library().list_entries(),
                            key=lambda e: (e.get("title") or "").lower())
            if e.get("source_url") in wanted
        ]
        self._start_check(ordered, 0)

    def _start_check(self, urls: list[str], skipped: int) -> None:
        self._check_stats = [0, 0, 0, skipped, 0]
        self.updateCheckStarted.emit(len(urls), skipped)
        if not urls:
            self.updateCheckFinished.emit(*self._check_stats)
            return

        worker = UpdateCheckWorker(urls, self)
        worker.progress.connect(self.updateCheckProgress.emit)
        worker.resultReady.connect(self._on_check_result)
        worker.finished.connect(self._on_check_finished)
        self._check_worker = worker
        worker.start()

    @pyqtSlot()
    def cancelCheckForUpdates(self) -> None:
        """Stop after the series currently being checked."""
        if self._check_worker is not None:
            self._check_worker.cancel()

    @pyqtSlot(result=bool)
    def isCheckingForUpdates(self) -> bool:
        return self._check_worker is not None

    @pyqtSlot(result="QVariant")
    def pendingUpdates(self) -> list:
        """
        Series with new chapters, for the review list. The per-source
        ``manga`` dicts stay Python-side (QML never needs them).
        """
        out = []
        for r in sorted(self._pending.values(),
                        key=lambda r: (r.get("title") or "").lower()):
            light = dict(r)
            light["sources"] = [
                {k: v for k, v in src.items() if k != "manga"}
                for src in r.get("sources") or []
            ]
            out.append(light)
        return out

    @pyqtSlot(result=str)
    def pendingCheckedAt(self) -> str:
        return self._pending_checked_at

    @pyqtSlot(str)
    def dismissUpdate(self, library_url: str) -> None:
        """Drop a series from the review list (until the next check)."""
        if self._pending.pop(library_url, None) is not None:
            self._save_pending()
            self.pendingUpdatesChanged.emit()

    @pyqtSlot("QVariant", result=int)
    def applyUpdates(self, selection) -> int:
        """
        Download what the user approved. ``selection`` is a list of
        ``{library_url, source_index, numbers: [normalised numbers]}``.
        Each series becomes one normal download job (rate limiter,
        failure log, library recording all apply), filed under the
        existing library entry even when the chosen site is an
        alternative. Returns the number of chapters queued.
        """
        if hasattr(selection, "toVariant"):
            selection = selection.toVariant()
        if self._download_bridge is None:
            return 0

        from src.utils.chapters import chapter_numbers_on_disk
        from src.utils.library import shared as _library
        from src.utils.update_check import entry_folder

        queued = 0
        for sel in selection or []:
            url = sel.get("library_url") or ""
            result = self._pending.get(url)
            if not result:
                continue
            sources = result.get("sources") or []
            idx = int(sel.get("source_index", -1))
            if not (0 <= idx < len(sources)) or not sources[idx].get("manga"):
                continue
            src = sources[idx]
            wanted = {str(n) for n in sel.get("numbers") or []}

            # Re-read disk: chapters moved into iCloud since the check
            # shouldn't be fetched again.
            entry = _library().get_entry(url) or {}
            folder = entry_folder(entry)
            have = chapter_numbers_on_disk(folder) if folder else set()

            chapters = [
                c for c in (src.get("newer") or []) + (src.get("gaps") or [])
                if c.get("norm") in wanted and c.get("norm") not in have
            ]
            if not chapters:
                continue

            manga_dict = dict(src["manga"], library_url=url)
            fmt = entry.get("output_format") or "cbz"
            self.updateStarted.emit(url, result.get("title") or "", len(chapters))
            self._download_bridge.startDownload(manga_dict, chapters, fmt, "Any")
            queued += len(chapters)
            self._pending.pop(url, None)

        if queued:
            self._save_pending()
            self.pendingUpdatesChanged.emit()
        return queued

    def _on_check_result(self, url: str, result: dict) -> None:
        from src.utils.update_check import has_updates

        if has_updates(result):
            self._check_stats[0] += 1
            self._pending[url] = result
        else:
            if result.get("error"):
                self._check_stats[2] += 1
            elif not result.get("on_disk_count"):
                # No parseable CBZ chapters (folder gone, image folders,
                # per-volume files) — nothing to diff against.
                self._check_stats[4] += 1
            else:
                self._check_stats[1] += 1
            self._pending.pop(url, None)
        self._pending_checked_at = result.get("checked_at") or self._pending_checked_at
        self._save_pending()
        self.pendingUpdatesChanged.emit()
        # Status badges / last-checked stamps may have moved.
        self.entriesChanged.emit()

    def _on_check_finished(self) -> None:
        worker, self._check_worker = self._check_worker, None
        if worker is not None:
            worker.deleteLater()
        self.updateCheckFinished.emit(*self._check_stats)

    def _load_pending(self) -> None:
        import json
        try:
            raw = json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
            self._pending = dict(raw.get("items") or {})
            self._pending_checked_at = raw.get("checked_at") or ""
        except (OSError, ValueError, AttributeError):
            self._pending, self._pending_checked_at = {}, ""

    def _save_pending(self) -> None:
        import json
        try:
            tmp = _PENDING_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(
                {"checked_at": self._pending_checked_at, "items": self._pending},
                indent=1, ensure_ascii=False,
            ), encoding="utf-8")
            os.replace(tmp, _PENDING_PATH)
        except OSError:
            pass

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

        # A successful probe updates last_checked_at and may flip
        # status_auto. Refresh the cached entries view so the card
        # picks up the new badge / timestamp. (Bulk-run probes also
        # land here via _on_bulk_probe_finished, so this single signal
        # is enough for both paths.)
        self.entriesChanged.emit()

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

        # File the chapters under THIS entry even when the probe fell
        # back to an alternative site.
        manga_dict = dict(manga_dict, library_url=source_url)
        self.updateStarted.emit(source_url, title, len(new_chapters))
        self._download_bridge.startDownload(manga_dict, new_chapters, fmt, "Any")
