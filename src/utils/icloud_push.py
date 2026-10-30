"""
Copy chapters waiting in the downloads folder into the series' folder in
the iCloud Manga folder — the "Copy to iCloud" button in Comix
Downloader and MyDex.

Copies, never moves: the downloads file stays (afterwards it counts as
"safe to remove"). Safety rules:

- Writes only into a direct, non-hidden subfolder of the iCloud Manga
  folder, so ``Manga/.reader_state.json`` (Comix Reader's sync state)
  and everything outside iCloud is never touched.
- Never overwrites: a chapter the folder already has — same number in
  any notation (62.5 / 62-5 / 62_5) or the same file name — is skipped.
- Copies to a hidden ``.partial`` name first and renames when complete,
  so iCloud and Comix Reader never see a half-written CBZ.
- Reads only file names in iCloud; no iCloud file is opened, so nothing
  cloud-only gets downloaded.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Optional

from .chapters import chapter_float, chapter_number_from_filename, chapter_numbers_on_disk
from .update_check import ICLOUD_ROOT, _icloud_folder_for, downloads_folders, entry_folder


def _check_target(target: Path, icloud_root: Path) -> None:
    root = icloud_root.resolve()
    t = target.resolve() if target.exists() else target.parent.resolve() / target.name
    if t.parent != root or t.name.startswith(".") or not t.name:
        raise ValueError(f"not a series folder in the iCloud Manga folder: {target}")


def copy_chapters(files: Iterable[Path], target: Path, icloud_root: Path = ICLOUD_ROOT) -> dict:
    """Copy chapter files into ``target`` (created if missing). Returns
    ``{"copied": [...], "skipped": [...], "failed": [(name, error), ...]}``."""
    _check_target(target, icloud_root)
    files = list(files)
    target.mkdir(exist_ok=True)
    have = chapter_numbers_on_disk(target)
    names = {p.name for p in target.iterdir()}
    out: dict = {"copied": [], "skipped": [], "failed": []}
    for f in files:
        f = Path(f)
        n = chapter_number_from_filename(f.stem)
        if f.name in names or (n is not None and n in have):
            out["skipped"].append(f.name)
            continue
        tmp = target / f".{f.name}.partial"
        try:
            shutil.copy2(f, tmp)
            os.replace(tmp, target / f.name)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            out["failed"].append((f.name, str(exc)))
            continue
        out["copied"].append(f.name)
        names.add(f.name)
        if n is not None:
            have.add(n)
    return out


def icloud_folder(entry: dict, icloud_root: Path = ICLOUD_ROOT) -> Optional[Path]:
    """The series' existing iCloud folder, or None."""
    rec = entry_folder(entry)
    try:
        if rec and rec.is_dir() and rec.resolve().parent == icloud_root.resolve():
            return rec
    except OSError:
        pass
    return _icloud_folder_for(entry, icloud_root)


def pending_for_entry(entry: dict, downloads_root: Optional[Path] = None,
                      icloud_root: Path = ICLOUD_ROOT, entries: Optional[list[dict]] = None) -> dict:
    """Chapters of this Library entry that are in the downloads folder but
    not in its iCloud folder, and where they would go. A series without an
    iCloud folder gets a new one named like its downloads folder.
    ``entries`` = the whole Library (so another series' downloads folder is
    never claimed; loaded when None)."""
    folder = icloud_folder(entry, icloud_root)
    dl = downloads_folders(entry, folder, downloads_root, entries=entries)
    have = chapter_numbers_on_disk(folder) if folder else set()
    seen: dict[str, Path] = {}
    for d in dl:
        for p in sorted(d.glob("*.cbz")):
            n = chapter_number_from_filename(p.stem)
            if n is not None and n not in have and n not in seen:
                seen[n] = p
    if folder is not None:
        target = folder
    else:
        name = dl[0].name if dl else (entry.get("folder") or entry.get("title") or "").strip()
        target = icloud_root / name
    chapters = sorted(({"number": n, "path": p} for n, p in seen.items()),
                      key=lambda c: (chapter_float(c["number"]) is None, chapter_float(c["number"]) or 0))
    return {"target": target, "target_exists": folder is not None, "chapters": chapters}
