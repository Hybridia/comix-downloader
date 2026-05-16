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
import re
import sys
import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---- On-disk chapter discovery -----------------------------------------
#
# These helpers exist because the library.json "chapters" dict is
# advisory only — what's actually ON DISK in the user's iCloud (or
# wherever ``download_path/folder`` points) is the ground truth for
# what they have. The Update flow uses this to compute the diff
# against a site's chapter list, with format normalisation so that
# ``Chapter_62.5.cbz`` (iCloud's dot convention) and ``chapter-62-5``
# (Madara's hyphen convention) count as the same chapter.

# Match "Chapter 62", "Chapter_62", "ch 62.5", "Chapter_68_1.cbz", "Chapter_82-5",
# "Chapter 4.1". The fraction separator can be ``.``, ``-``, or ``_`` —
# users encode sub-chapters all three ways in filenames (``68.5`` /
# ``68-5`` / ``68_5``). The normaliser below collapses them.
_FILENAME_CHAPTER_RE = re.compile(
    r"(?:chapter|chap|episode|ep|ch)[_\s\.\-]*(\d+(?:[-._]\d+)?)",
    re.IGNORECASE,
)


def _norm_chapter_number(n: str) -> str:
    """
    Canonicalise a chapter-number string for cross-site comparison.

    - Collapses fraction separators (``62-5`` ⇄ ``62.5`` ⇄ ``62_5``)
      so the same chapter compares equal regardless of which site's
      or filename's convention it came from. Three separators are in
      common use:
        * dot — comix and most providers' canonical
        * hyphen — Madara URL slugs (``chapter-62-5``)
        * underscore — some iCloud filenames (``Chapter_62_5.cbz``)
          where the user replaced reserved chars manually
    - Strips leading zeros from the integer part (``007`` → ``7``)
      so padded filenames compare equal to unpadded site numbers.
    """
    s = str(n).replace("-", ".").replace("_", ".")
    if "." in s:
        head, tail = s.split(".", 1)
        try:
            head = str(int(head))
        except ValueError:
            pass
        return f"{head}.{tail}" if tail else head
    try:
        return str(int(s))
    except ValueError:
        return s


def _chapter_numbers_on_disk(folder: Path) -> set[str]:
    """
    Return the set of normalised chapter numbers found as ``.cbz``
    files directly under ``folder``. Empty set if the folder doesn't
    exist or contains nothing recognisable.

    Doesn't recurse — chapters are flat in every format we support.
    """
    out: set[str] = set()
    try:
        if not folder.is_dir():
            return out
    except OSError:
        return out
    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() != ".cbz":
                continue
            m = _FILENAME_CHAPTER_RE.search(entry.stem)
            if m:
                out.add(_norm_chapter_number(m.group(1)))
    except OSError:
        pass
    return out


def _max_chapter(numbers: set[str]) -> float:
    """Largest numerically-parseable chapter number, or -1 if none."""
    best = -1.0
    for n in numbers:
        try:
            best = max(best, float(n))
        except ValueError:
            continue
    return best


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

        self.updateStarted.emit(source_url, title, len(new_chapters))
        self._download_bridge.startDownload(manga_dict, new_chapters, fmt, "Any")
