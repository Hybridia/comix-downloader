"""
"Copy to iCloud" view: chapters waiting in the downloads folder that
aren't in the series' iCloud folder yet, and the copy itself.

The logic lives in ``src/utils/icloud_push.py`` (MyDex uses it too); this
bridge only scans the Library and runs scans / copies off the UI thread.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

import time

from src.utils.icloud_push import copy_chapters, pending_for_entry
from src.utils.icloud_status import summarize_details, upload_details
from src.utils.update_check import ICLOUD_ROOT


def scan_pending(entries: list[dict], downloads_root: Optional[Path] = None,
                 icloud_root: Path = ICLOUD_ROOT) -> list[dict]:
    """One row per iCloud target folder (duplicate Library entries for one
    series collapse), sorted by title."""
    rows: dict[str, dict] = {}
    for e in entries:
        try:
            p = pending_for_entry(e, downloads_root=downloads_root, icloud_root=icloud_root, entries=entries)
        except Exception:
            continue
        if not p["chapters"]:
            continue
        key = str(p["target"])
        row = rows.setdefault(key, {"key": key, "title": e.get("title") or p["target"].name,
                                    "target": p["target"].name, "target_exists": p["target_exists"],
                                    "poster_url": e.get("poster_url") or "", "chapters": []})
        have = {c["number"] for c in row["chapters"]}
        for c in p["chapters"]:
            if c["number"] not in have:
                path = Path(c["path"])
                row["chapters"].append({"number": c["number"], "path": str(path),
                                        "size": path.stat().st_size if path.exists() else 0})
    from src.utils.chapters import chapter_float
    for row in rows.values():
        row["chapters"].sort(key=lambda c: chapter_float(c["number"]) or 0)
    return sorted(rows.values(), key=lambda r: r["title"].lower())


class _ScanWorker(QThread):
    done = pyqtSignal(list)

    def __init__(self, downloads_root, icloud_root):
        super().__init__()
        self.downloads_root, self.icloud_root = downloads_root, icloud_root

    def run(self):
        from src.utils.library import shared
        try:
            rows = scan_pending(shared().list_entries(), self.downloads_root, self.icloud_root)
        except Exception:
            rows = []
        self.done.emit(rows)


class _CopyWorker(QThread):
    """Copy, then wait until macOS has uploaded the copies to iCloud."""
    progress = pyqtSignal(int, int, str)
    upload = pyqtSignal(dict)
    done = pyqtSignal(dict)

    def __init__(self, items: list[dict], icloud_root: Path, status_fn, poll_seconds: float,
                 upload_timeout: float):
        super().__init__()
        self.items, self.icloud_root = items, icloud_root
        self.status_fn, self.poll_seconds, self.upload_timeout = status_fn, poll_seconds, upload_timeout

    def _wait_for_upload(self, files: list[Path]) -> str:
        """'' when all are uploaded, else the tail of the final message.
        An upload error isn't final — iCloud retries by itself — so keep
        waiting until the timeout."""
        end = time.monotonic() + self.upload_timeout
        while True:
            s = summarize_details(self.status_fn(files))
            reason = max(s["reasons"], key=s["reasons"].get) if s["reasons"] else ""
            self.upload.emit({**s, "reason": reason})
            if s["pending"] == 0:
                return ""
            if time.monotonic() > end:
                why = f"iCloud says “{reason}” and keeps retrying by itself" if reason else "iCloud is still working on it"
                n = s["pending"]
                return f", but {n} {'is' if n == 1 else 'are'}n't uploaded yet — {why}"

    def run(self):
        total = sum(len(it.get("paths") or []) for it in self.items)
        copied, skipped, failed, n = 0, 0, [], 0
        landed: list[Path] = []
        for it in self.items:
            target = Path(it["key"])
            for p in it.get("paths") or []:
                n += 1
                self.progress.emit(n, total, Path(p).name)
                try:
                    r = copy_chapters([Path(p)], target, icloud_root=self.icloud_root)
                    landed += [target / name for name in r["copied"]]
                    copied += len(r["copied"])
                    skipped += len(r["skipped"])
                    failed += [name for name, _ in r["failed"]]
                except Exception as exc:
                    failed.append(f"{Path(p).name} ({exc})")
        msg = f"Copied {copied} chapter{'s' if copied != 1 else ''} to iCloud"
        if skipped:
            msg += f", {skipped} already there"
        if failed:
            msg += "; failed: " + ", ".join(failed)
        problem = self._wait_for_upload(landed) if landed else ""
        if landed and not problem:
            msg += f" — {'all ' if copied > 1 else ''}uploaded to iCloud ✓"
        elif problem:
            msg += problem
        msg += ". The downloads copies stay until you remove them."
        self.done.emit({"copied": copied, "skipped": skipped, "failed": len(failed) + bool(problem),
                        "message": msg})


class IcloudBridge(QObject):
    pendingReady = pyqtSignal("QVariantList")
    copyProgress = pyqtSignal(int, int, str)
    uploadProgress = pyqtSignal("QVariantMap")
    copyFinished = pyqtSignal("QVariantMap")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icloud_root: Path = ICLOUD_ROOT       # tests point these at temp folders
        self.downloads_root: Optional[Path] = None  # None = config download_path
        self.status_fn = upload_details              # macOS: upload state + bytes per file
        self.poll_seconds = 3.0
        self.upload_timeout = 2 * 3600.0
        self._scan: Optional[_ScanWorker] = None
        self._copy: Optional[_CopyWorker] = None

    @pyqtSlot()
    def scan(self):
        if self._scan and self._scan.isRunning():
            return
        self._scan = _ScanWorker(self.downloads_root, self.icloud_root)
        self._scan.done.connect(self.pendingReady.emit)
        self._scan.start()

    @pyqtSlot("QVariantList")
    def copy(self, items):
        if self._copy and self._copy.isRunning():
            return
        items = [dict(it) for it in items]
        self._copy = _CopyWorker(items, self.icloud_root, self.status_fn, self.poll_seconds,
                                 self.upload_timeout)
        self._copy.progress.connect(self.copyProgress.emit)
        self._copy.upload.connect(self.uploadProgress.emit)
        self._copy.done.connect(self._copied)
        self._copy.start()

    def _copied(self, result: dict):
        self.copyFinished.emit(result)
        self.scan()

    @pyqtSlot(result=bool)
    def isCopying(self) -> bool:
        return bool(self._copy and self._copy.isRunning())
