"""
Library — persistent record of every manga we've successfully downloaded
(or partially downloaded), keyed by source URL. Lives at
``<project_root>/library.json``.

The library is the source of truth for the GUI's Library tab and for
the "Update" flow that fetches only chapters we haven't downloaded yet.

JSON shape (versioned so we can migrate):

    {
      "version": 1,
      "entries": [
        {
          "source": "hentairead",
          "source_url": "https://hentairead.com/hentai/<slug>",
          "manga_id": 165981,
          "hash_id": "165981",
          "manga_code": "<slug>",
          "title": "...",
          "alt_titles": [...],
          "poster_url": "https://...",
          "is_nsfw": true,
          "artists": [...],
          "tags": [...],
          "output_format": "cbz",
          "download_path": "downloads",
          "folder": "<safe_title>",
          "added_at": "<ISO-8601 UTC>",
          "last_updated_at": "<ISO-8601 UTC>",
          "last_checked_at": null,
          "chapters": {
            "1": {"title": "...", "downloaded_at": "<ISO-8601 UTC>"}
          }
        }
      ]
    }

Design notes:

- ``source_url`` is the primary key (normalized: lowercase host, no
  trailing slash, no fragment). Two URLs that point to the same
  gallery shouldn't produce two library entries.
- ``chapters`` is a dict keyed by ``Chapter.number`` (string), so
  computing "what's new on the site?" is just
  ``set(remote_numbers) - set(entry["chapters"].keys())``.
- All writes go through a process-wide lock and rewrite the whole
  file atomically (same pattern as ``secrets.py``). The library is
  small even for power users (≤ a few hundred entries), so full
  rewrites are fine.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

from .logger import get_logger

logger = get_logger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _PROJECT_ROOT / "library.json"

_SCHEMA_VERSION = 1

_lock = threading.RLock()
_singleton: Optional["LibraryManager"] = None


def _now_iso() -> str:
    """Timezone-aware UTC ISO-8601 timestamp, no microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Provider `status` strings vary ("Completed", "complete", "End",
# "Ongoing", "Publishing", …). Normalise to a fixed vocabulary so the
# GUI can match against stable values. Empty string ⇒ unknown.
_STATUS_COMPLETED = {
    "completed", "complete", "completo", "completa",
    "finished", "ended", "end", "終了", "完結",
}
_STATUS_CANCELLED = {
    "cancelled", "canceled", "dropped", "discontinued", "abandoned",
}
_STATUS_HIATUS = {
    "hiatus", "on hiatus", "paused", "on hold",
}
_STATUS_ONGOING = {
    "ongoing", "publishing", "serializing", "serialising",
    "in progress", "running", "active", "連載中",
    "releasing",   # mangafire's term
    "current",     # webtoonscan / some Madara sites
}


def normalize_status(value: Optional[str]) -> str:
    """
    Map a raw provider status string to one of:
    "completed" / "cancelled" / "hiatus" / "ongoing" / "" (unknown).

    For the skip-on-Update-All purpose, "completed" and "cancelled"
    both mean "won't get new chapters from the site".

    Whitespace and hyphens are collapsed before matching so variants
    like "on going" / "on-going" / "on  going" all resolve the same
    as "ongoing". Real-world inputs we've seen: "Completed",
    "complete", "OnGoing", "On going", "On Going", "完結", "Hiatus".
    """
    if not value:
        return ""
    v = str(value).strip().lower()
    if not v:
        return ""
    # Collapse internal whitespace + hyphens so "on going" / "on-going"
    # become "ongoing". We test both the squashed form AND the original
    # so multi-word categories like "in progress" still match.
    squashed = re.sub(r"[\s\-_]+", "", v)
    for variant in (v, squashed):
        if variant in _STATUS_COMPLETED:
            return "completed"
        if variant in _STATUS_CANCELLED:
            return "cancelled"
        if variant in _STATUS_HIATUS:
            return "hiatus"
        if variant in _STATUS_ONGOING:
            return "ongoing"
    # Fallback substring sniff for messy values ("Status: Completed!").
    for token in _STATUS_COMPLETED:
        if token in v or token in squashed:
            return "completed"
    for token in _STATUS_CANCELLED:
        if token in v or token in squashed:
            return "cancelled"
    for token in _STATUS_HIATUS:
        if token in v or token in squashed:
            return "hiatus"
    for token in _STATUS_ONGOING:
        if token in v or token in squashed:
            return "ongoing"
    return ""


def is_finished_status(status: str) -> bool:
    """True if the status means 'no more new chapters expected'."""
    return status in ("completed", "cancelled")


def _normalize_url(url: str) -> str:
    """
    Make ``source_url`` stable across trivial variants so the same
    gallery isn't recorded twice. Lowercases scheme + host, drops the
    fragment, strips a trailing slash from the path.
    """
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, p.params, p.query, ""))


class LibraryManager:
    """Persistent library of downloaded manga."""

    def __init__(self, path: Optional[Path] = None):
        self.path: Path = Path(path) if path else _DEFAULT_PATH
        self._data: dict = {"version": _SCHEMA_VERSION, "entries": []}
        # Track the file's mtime at the moment we last loaded or saved.
        # ``_reload_if_changed`` uses this to detect external edits
        # (e.g. the user runs ``scripts/library_relocate_to_icloud.py``
        # while the GUI is open) so the next GUI write doesn't clobber
        # them.
        self._mtime: float = 0.0
        self._load()

    # --- IO ----------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            self._mtime = 0.0
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
                self._data = raw
                # Forward compatibility: tolerate missing keys per entry.
                for e in self._data["entries"]:
                    e.setdefault("chapters", {})
            self._mtime = self.path.stat().st_mtime
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "library.json unreadable (%s); starting from empty library.", exc
            )

    def _reload_if_changed(self) -> None:
        """
        Re-read library.json from disk if its mtime has advanced since
        our last load or save — i.e. some other process (a script) has
        edited it. Without this, every GUI mutation would silently
        revert the script's changes by writing our stale in-memory
        copy back over them.

        Uses a small tolerance (0.5s) because os.replace gives the new
        file a slightly newer mtime than the second we set during
        ``_save``, and we don't want our own writes to look "external"
        on the very next call.
        """
        try:
            current = self.path.stat().st_mtime
        except OSError:
            return
        if current > self._mtime + 0.5:
            logger.info(
                "library.json changed externally (mtime %s > %s); reloading",
                current, self._mtime,
            )
            self._load()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._mtime = self.path.stat().st_mtime
        except OSError as exc:
            logger.error("Failed to persist library.json: %s", exc)

    # --- Internal lookup --------------------------------------------

    def _index(self, source_url: str) -> int:
        """Return the index of an entry by normalized URL, or -1."""
        key = _normalize_url(source_url)
        if not key:
            return -1
        for i, e in enumerate(self._data["entries"]):
            if _normalize_url(e.get("source_url", "")) == key:
                return i
        return -1

    # --- Public API --------------------------------------------------

    def list_entries(self) -> list[dict]:
        """Return a deep-ish copy of all entries (safe for QML)."""
        with _lock:
            self._reload_if_changed()
            # shallow-copy each entry; chapters is a small dict so ok.
            return [dict(e) for e in self._data["entries"]]

    def get_entry(self, source_url: str) -> Optional[dict]:
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            return dict(self._data["entries"][i]) if i >= 0 else None

    def upsert_manga(
        self,
        manga,
        output_format: str,
        download_path: str,
        manga_code: Optional[str] = None,
    ) -> dict:
        """
        Create or refresh the entry for ``manga``. Updates the snapshot
        of metadata (title, poster, tags) without touching the
        ``chapters`` dict. Called once at the start of every download
        run so an entry exists even if every chapter ends up failing.

        ``status`` is auto-tracked from ``MangaInfo.status`` and
        normalised. A user "Mark as completed" toggle on the GUI sets
        ``status_manual = True`` — when that flag is set, the auto
        value is recorded under ``status_auto`` for visibility but the
        effective ``status`` is left alone.
        """
        with _lock:
            self._reload_if_changed()
            now = _now_iso()
            auto_status = normalize_status(getattr(manga, "status", None))
            entry = {
                "source": getattr(manga, "source", "") or "",
                "source_url": _normalize_url(getattr(manga, "source_url", "") or ""),
                "manga_id": getattr(manga, "manga_id", None),
                "hash_id": getattr(manga, "hash_id", None),
                "manga_code": manga_code or getattr(manga, "slug", None),
                "title": getattr(manga, "title", "") or "Unknown",
                "alt_titles": list(getattr(manga, "alt_titles", []) or []),
                "poster_url": getattr(manga, "poster_url", "") or "",
                "is_nsfw": bool(getattr(manga, "is_nsfw", False)),
                "artists": list(getattr(manga, "artists", []) or []),
                "tags": list(getattr(manga, "tags", []) or []),
                "output_format": output_format,
                "download_path": download_path,
                "folder": (
                    manga.get_safe_title()
                    if hasattr(manga, "get_safe_title")
                    else getattr(manga, "title", "Unknown")
                ),
                "last_updated_at": now,
                "status_auto": auto_status,
            }

            i = self._index(entry["source_url"]) if entry["source_url"] else -1
            if i >= 0:
                existing = self._data["entries"][i]
                # Preserve historical fields we don't overwrite.
                entry["added_at"] = existing.get("added_at", now)
                entry["last_checked_at"] = existing.get("last_checked_at")
                entry["chapters"] = existing.get("chapters", {})
                # Status precedence: a manual override (set via the
                # Library card's status toggle) wins; otherwise we use
                # whatever the provider just reported. This is also why
                # status_auto is stored separately — so the GUI can
                # show "you've marked this Completed; site says Ongoing".
                if existing.get("status_manual"):
                    entry["status"] = existing.get("status", "")
                    entry["status_manual"] = True
                else:
                    entry["status"] = auto_status
                    entry["status_manual"] = False
                self._data["entries"][i] = entry
            else:
                entry["added_at"] = now
                entry["last_checked_at"] = None
                entry["chapters"] = {}
                entry["status"] = auto_status
                entry["status_manual"] = False
                self._data["entries"].append(entry)

            self._save()
            return dict(entry)

    def set_status(
        self, source_url: str, status: str, manual: bool = True,
    ) -> bool:
        """
        Set an entry's status. With ``manual=True`` (the default)
        the auto-tracker won't overwrite this on the next probe; pass
        ``manual=False`` to clear an override.

        Clearing an override (``status=""``, ``manual=False``) restores
        the last-known auto value from ``status_auto`` — otherwise the
        card would show "?" until the next probe re-syncs from the
        provider, which is the wrong default for a "Clear override"
        button.
        """
        normalized = normalize_status(status) if status else ""
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            if i < 0:
                return False
            entry = self._data["entries"][i]
            if not manual and not normalized:
                # "Use site status" — fall back to whatever the last
                # probe recorded. Empty if the provider doesn't expose
                # status (in which case the badge correctly shows "?").
                entry["status"] = entry.get("status_auto", "") or ""
            else:
                entry["status"] = normalized
            entry["status_manual"] = bool(manual)
            self._save()
            return True

    def record_chapter(
        self,
        manga,
        chapter,
        output_format: str,
        download_path: str,
        manga_code: Optional[str] = None,
    ) -> None:
        """Mark a single chapter as successfully downloaded."""
        with _lock:
            self._reload_if_changed()
            url = _normalize_url(getattr(manga, "source_url", "") or "")
            if not url:
                # No source URL means we can't dedupe; skip silently
                # rather than spam library.json with anonymous entries.
                return
            i = self._index(url)
            if i < 0:
                self.upsert_manga(manga, output_format, download_path, manga_code)
                i = self._index(url)
                if i < 0:
                    return

            entry = self._data["entries"][i]
            chapters = entry.setdefault("chapters", {})
            number = str(getattr(chapter, "number", "")) or "?"
            chapters[number] = {
                "title": getattr(chapter, "title", "") or "",
                "downloaded_at": _now_iso(),
            }
            entry["last_updated_at"] = _now_iso()
            self._save()

    def mark_checked(
        self, source_url: str, manga_status: Optional[str] = None,
    ) -> None:
        """
        Stamp ``last_checked_at`` (called after an Update probe).

        If ``manga_status`` is provided, also refresh ``status_auto``
        from the live provider value. The effective ``status`` is
        re-synced only when the user hasn't set a manual override —
        a user "Mark as completed" should survive a routine probe
        that disagrees.
        """
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            if i < 0:
                return
            entry = self._data["entries"][i]
            entry["last_checked_at"] = _now_iso()
            if manga_status is not None:
                normalized = normalize_status(manga_status)
                entry["status_auto"] = normalized
                if not entry.get("status_manual"):
                    entry["status"] = normalized
            self._save()

    def set_output_format(self, source_url: str, fmt: str) -> bool:
        """
        Update an entry's ``output_format`` (e.g. after the Library
        "Convert to CBZ" button runs). Returns True if the entry
        existed and was updated.
        """
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            if i < 0:
                return False
            self._data["entries"][i]["output_format"] = fmt
            self._data["entries"][i]["last_updated_at"] = _now_iso()
            self._save()
            return True

    def remove_entry(self, source_url: str) -> bool:
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            if i < 0:
                return False
            self._data["entries"].pop(i)
            self._save()
            return True

    def downloaded_chapter_numbers(self, source_url: str) -> set[str]:
        with _lock:
            self._reload_if_changed()
            i = self._index(source_url)
            if i < 0:
                return set()
            return set(self._data["entries"][i].get("chapters", {}).keys())


def shared() -> LibraryManager:
    """Process-wide singleton."""
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = LibraryManager()
        return _singleton


def reset_for_tests() -> None:
    """Drop the singleton — only for unit tests."""
    global _singleton
    with _lock:
        _singleton = None
