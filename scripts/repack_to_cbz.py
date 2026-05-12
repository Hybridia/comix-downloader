#!/usr/bin/env python3
"""
Repack already-downloaded image folders into CBZ files.

Use when you downloaded a manga with ``output_format=images`` and
later decided you want CBZs — this packs each chapter folder into a
``.cbz`` next to it, including a proper ``ComicInfo.xml`` built from
the metadata stored in ``library.json``.

The core logic lives in :mod:`src.utils.repack` so the Library tab's
"Convert to CBZ" button uses the same implementation.

Usage
-----

    # Convert every manga under downloads/
    python3 scripts/repack_to_cbz.py --all

    # Convert one or more specific manga folders
    python3 scripts/repack_to_cbz.py "downloads/Brave New World" "downloads/Circles"

    # Convert AND delete the image folders afterwards (only after
    # successful CBZ creation)
    python3 scripts/repack_to_cbz.py --all --delete-images
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.repack import (  # noqa: E402
    manga_info_from_library_entry,
    repack_manga,
)
from src.core.models import MangaInfo  # noqa: E402


def _read_library(library_path: Path) -> dict[str, dict]:
    """Return ``{folder_name: entry_dict}`` from library.json."""
    if not library_path.exists():
        return {}
    try:
        data = json.loads(library_path.read_text())
    except Exception as e:
        print(f"  ! couldn't parse {library_path}: {e}; continuing without metadata")
        return {}
    entries = data.get("entries", data) if isinstance(data, dict) else data
    if isinstance(entries, dict):
        entries = list(entries.values())
    out: dict[str, dict] = {}
    for entry in entries:
        folder = (entry or {}).get("folder")
        if folder:
            out[folder] = entry
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folders", nargs="*",
        help="Manga folders to convert. Ignored when --all is set.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Convert every manga directory under downloads/.",
    )
    parser.add_argument(
        "--delete-images", action="store_true",
        help="Remove the source image subfolders after successful CBZ build.",
    )
    parser.add_argument(
        "--downloads-dir", default=str(ROOT / "downloads"),
        help="Root downloads directory (defaults to ./downloads).",
    )
    parser.add_argument(
        "--library", default=str(ROOT / "library.json"),
        help="Path to library.json (for ComicInfo.xml metadata).",
    )
    args = parser.parse_args()

    downloads_root = Path(args.downloads_dir).resolve()
    library = _read_library(Path(args.library))
    print(f"library entries loaded: {len(library)}  (from {args.library})")

    if args.all:
        targets = sorted(
            p for p in downloads_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
    elif args.folders:
        targets = [Path(p).resolve() for p in args.folders]
        for t in targets:
            if not t.is_dir():
                print(f"! not a directory: {t}", file=sys.stderr)
                return 2
    else:
        parser.print_help()
        return 1

    print(f"converting {len(targets)} manga folder(s)…")
    if args.delete_images:
        print("  NOTE: --delete-images is set; source folders will be removed after CBZ build")

    total_created = total_skipped = total_failed = 0
    for manga_dir in targets:
        entry = library.get(manga_dir.name)
        if entry:
            print(f"\n== {manga_dir.name} ==  (title={entry.get('title')!r})")
            manga = manga_info_from_library_entry(entry, manga_dir.name)
        else:
            print(f"\n== {manga_dir.name} ==  (no library metadata; using folder name)")
            manga = MangaInfo(title=manga_dir.name)

        def _on_progress(chapter_name, done, total, status):
            if status == "start":
                return
            mark = {"created": "✓", "skipped": "·", "failed": "!"}.get(status, "?")
            print(f"   {mark} {chapter_name}  ({done}/{total})")

        result = repack_manga(
            manga_dir,
            manga,
            library_entry=entry,
            delete_images=args.delete_images,
            on_progress=_on_progress,
        )
        print(
            f"   summary: {result.created} created, "
            f"{result.skipped} already-cbz, {result.failed} failed"
        )
        total_created += result.created
        total_skipped += result.skipped
        total_failed += result.failed

    print(
        f"\nTOTAL: {total_created} CBZs created, "
        f"{total_skipped} already had a CBZ, {total_failed} failed"
    )
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
