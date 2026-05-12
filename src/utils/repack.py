"""
Repack-to-CBZ core. Shared by ``scripts/repack_to_cbz.py`` (CLI use)
and ``gui/bridge/library_bridge.py`` (per-manga "Convert to CBZ"
button in the Library tab).

Takes a manga folder on disk full of ``Chapter_NN/*.<ext>`` image
folders and packs each chapter into a sibling ``Chapter_NN.cbz`` with
a proper ComicInfo.xml built from a :class:`MangaInfo`. No network
involved.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..core.models import Chapter, MangaInfo
from ..formats.cbz import create_cbz
from .logger import get_logger

logger = get_logger(__name__)


IMAGE_EXTS = {".webp", ".jpg", ".jpeg", ".png", ".gif"}
_CHAPTER_NUM_RE = re.compile(r"^Chapter_([0-9]+(?:\.[0-9]+)?)(?:_|$)", re.IGNORECASE)


@dataclass
class RepackResult:
    """Summary of a single manga's repack run."""
    created: int = 0
    skipped: int = 0  # already had a .cbz
    failed: int = 0


def manga_info_from_library_entry(entry: dict, folder_name: str) -> MangaInfo:
    """Reconstruct a MangaInfo from a library.json entry."""
    return MangaInfo(
        manga_id=entry.get("manga_id"),
        hash_id=entry.get("hash_id"),
        title=entry.get("title") or folder_name,
        alt_titles=list(entry.get("alt_titles") or []),
        slug=entry.get("slug"),
        manga_type=entry.get("manga_type"),
        poster_url=entry.get("poster_url"),
        original_language=entry.get("original_language"),
        status=entry.get("status"),
        is_nsfw=bool(entry.get("is_nsfw", False)),
        description=entry.get("description") or "",
        source=entry.get("source") or "",
        source_url=entry.get("source_url") or "",
        artists=list(entry.get("artists") or []),
        tags=list(entry.get("tags") or []),
        genres=list(entry.get("genres") or entry.get("tags") or []),
    )


def list_image_files(chapter_dir: Path) -> list[Path]:
    """All image files in ``chapter_dir`` sorted by numeric prefix."""
    files = [
        p
        for p in chapter_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]

    def sort_key(p: Path):
        m = re.match(r"^(\d+)", p.stem)
        return (0, int(m.group(1))) if m else (1, p.name)

    files.sort(key=sort_key)
    return files


def list_chapter_dirs(manga_dir: Path) -> list[Path]:
    """All ``Chapter_*`` subdirectories under ``manga_dir``, in numeric order."""
    chapter_dirs = [
        p
        for p in manga_dir.iterdir()
        if p.is_dir() and p.name.lower().startswith("chapter_")
    ]
    chapter_dirs.sort(
        key=lambda p: (
            float(_CHAPTER_NUM_RE.match(p.name).group(1))
            if _CHAPTER_NUM_RE.match(p.name)
            else float("inf")
        )
    )
    return chapter_dirs


def _build_chapter(chapter_dir: Path, library_entry: Optional[dict]) -> Chapter:
    """Synthesise a Chapter object for ComicInfo.xml."""
    name = chapter_dir.name
    m = _CHAPTER_NUM_RE.match(name)
    number = m.group(1) if m else name.replace("Chapter_", "").replace("Chapter ", "")

    title: Optional[str] = None
    group_name: Optional[str] = None
    if library_entry:
        ch_meta = (library_entry.get("chapters") or {}).get(str(number))
        if isinstance(ch_meta, dict):
            title = ch_meta.get("title")
            group_name = ch_meta.get("group_name")

    return Chapter(
        chapter_id=0,
        number=str(number),
        title=title,
        group_name=group_name,
    )


# Progress callback signature:
#   (chapter_name: str, done: int, total: int, status: str) -> None
# Statuses: "created", "skipped", "failed", "start"
ProgressCallback = Callable[[str, int, int, str], None]


def repack_manga(
    manga_dir: Path,
    manga: MangaInfo,
    *,
    library_entry: Optional[dict] = None,
    delete_images: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> RepackResult:
    """
    Pack every ``Chapter_*`` subfolder of ``manga_dir`` into a sibling
    ``.cbz``. Idempotent — chapters that already have a CBZ next to
    them are skipped. ``delete_images=True`` removes the source folder
    only AFTER its CBZ is successfully built.

    ``on_progress`` is invoked once per chapter (and once at the start
    with ``status="start"``) so a GUI can render live progress.
    """
    result = RepackResult()
    chapter_dirs = list_chapter_dirs(manga_dir)
    if not chapter_dirs:
        logger.info(f"repack: no Chapter_* folders in {manga_dir}")
        return result

    total = len(chapter_dirs)
    if on_progress:
        on_progress("", 0, total, "start")

    done = 0
    for ch_dir in chapter_dirs:
        out_path = manga_dir / f"{ch_dir.name}.cbz"
        if out_path.exists():
            result.skipped += 1
            done += 1
            if on_progress:
                on_progress(ch_dir.name, done, total, "skipped")
            continue

        images = list_image_files(ch_dir)
        if not images:
            logger.warning(f"repack: {ch_dir} has no images, skipping")
            result.failed += 1
            done += 1
            if on_progress:
                on_progress(ch_dir.name, done, total, "failed")
            continue

        chapter = _build_chapter(ch_dir, library_entry)
        try:
            create_cbz(images, out_path, manga=manga, chapter=chapter)
            result.created += 1
            if delete_images:
                try:
                    shutil.rmtree(ch_dir)
                except Exception as e:
                    # Non-fatal — the CBZ exists, so it's still a success.
                    logger.warning(
                        f"repack: couldn't delete {ch_dir} after CBZ build: {e}"
                    )
            done += 1
            if on_progress:
                on_progress(ch_dir.name, done, total, "created")
        except Exception as e:
            logger.exception(f"repack: failed to build CBZ for {ch_dir}: {e}")
            result.failed += 1
            done += 1
            if on_progress:
                on_progress(ch_dir.name, done, total, "failed")
    return result
