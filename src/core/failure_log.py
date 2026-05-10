"""
Per-manga failure log.

After a download session finishes, write a text file inside the manga's
output directory listing chapters that failed (with the reason). On a
clean run the log is removed so the directory stays tidy. The same
helper is used by both the CLI and the GUI download paths so the
output is consistent.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Chapter, DownloadConfig, MangaInfo
from ..utils.logger import get_logger

logger = get_logger(__name__)


class FailureLog:
    """Collects per-chapter failures during a download session."""

    def __init__(self, manga: MangaInfo, config: DownloadConfig) -> None:
        self.manga = manga
        self.config = config
        self.entries: list[tuple[Chapter, str]] = []

    @property
    def path(self) -> Path:
        return (
            Path(self.config.download_path)
            / self.manga.get_safe_title()
            / "_failed.txt"
        )

    def record(self, chapter: Chapter, reason: str) -> None:
        # Trim noisy stack-trace leftovers so the log stays scannable.
        reason = (reason or "unknown error").strip().splitlines()[0]
        self.entries.append((chapter, reason))

    @staticmethod
    def _sort_key(entry: tuple[Chapter, str]) -> float:
        ch = entry[0]
        try:
            return float(ch.number)
        except (TypeError, ValueError):
            return 0.0

    def write(self) -> Optional[Path]:
        """
        Write the failure log to disk. If there are no failures, remove
        any stale log from a previous run. Returns the path written, or
        ``None`` if nothing was written.
        """
        if not self.entries:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Couldn't remove stale failure log: {e}")
            return None

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entries = sorted(self.entries, key=self._sort_key)
            with self.path.open("w", encoding="utf-8") as f:
                f.write(f"# Failure log — {self.manga.title}\n")
                f.write(
                    f"# Run finished {datetime.now().isoformat(timespec='seconds')}\n"
                )
                f.write(
                    f"# {len(entries)} chapter(s) failed. "
                    "Re-run the download — completed chapters will skip.\n\n"
                )
                # Tab-separated for easy column selection in spreadsheet apps.
                f.write("number\ttitle\treason\n")
                for ch, reason in entries:
                    title = (ch.title or "").replace("\t", " ").strip()
                    f.write(f"{ch.number}\t{title}\t{reason}\n")
            logger.info(f"Wrote failure log → {self.path}")
            return self.path
        except Exception as e:
            logger.warning(f"Couldn't write failure log: {e}")
            return None
