#!/usr/bin/env python3
"""
library.json deduplication — drops pre-iCloud-import library entries
whose series title also appears among the iCloud-imported entries.

Why this exists: until this week the library only knew about manga
downloaded via the GUI (origin not set, files under ./downloads/).
This week's import added the iCloud collection with
``origin = "icloud_import"`` and ``download_path = <iCloud>/Manga``.
For ~70 series the user has BOTH: an old "I downloaded this in-app"
entry AND a new "this is in iCloud" entry, showing up twice in the
Library tab.

The iCloud-import row is the better one to keep because:
1. ``chapters`` is populated from the actual iCloud filenames (so
   ``Update`` knows precisely what's missing on the site side).
2. ``download_path`` points at the iCloud folder, so the "📂 Folder"
   button opens the real files.

So the rule is: for each pre-existing entry whose title fuzzy-matches
an iCloud-imported entry, drop the pre-existing one.

Also removes the single known intra-import duplicate ("The Mating of
Elves" got matched on both manhwaread and comix; the manhwaread row
has empty status so we keep the comix one).

Backup is written to ``library.json.bak.dedupe-<timestamp>`` first.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = PROJECT_ROOT / "library.json"


def fuzz(s: str) -> str:
    """Lowercase, strip all non-alphanumerics — for safe title matching."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def main() -> int:
    if not LIBRARY_PATH.exists():
        print(f"library.json not found at {LIBRARY_PATH}.")
        return 1

    # Backup first.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = LIBRARY_PATH.with_suffix(f".json.bak.dedupe-{ts}")
    shutil.copy2(LIBRARY_PATH, backup)
    print(f"Backed up to {backup.name}")

    lib = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    entries = lib["entries"]
    before = len(entries)

    # Build the iCloud-key set from THREE sources:
    # 1. iCloud-imported entries' titles (site-reported)
    # 2. iCloud-imported entries' folders (raw iCloud folder names)
    # 3. The inventory's folder_name + title fields
    # That way a pre-existing entry's title is considered an overlap
    # whether it matches the site title OR the original iCloud folder.
    icloud_keys: set[str] = set()
    for e in entries:
        if e.get("origin") == "icloud_import":
            icloud_keys.add(fuzz(e.get("title", "")))
            icloud_keys.add(fuzz(e.get("folder", "")))

    inv_path = PROJECT_ROOT / "icloud_inventory.json"
    if inv_path.exists():
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
        for ie in inv.get("entries", []):
            icloud_keys.add(fuzz(ie.get("title", "")))
            icloud_keys.add(fuzz(ie.get("folder_name", "")))

    # Drop the empty key — fuzz("") == "" matches everything otherwise.
    icloud_keys.discard("")

    # Step 1 — drop pre-existing entries whose title (or folder name)
    # matches any iCloud key. Pre-existing = origin != "icloud_import".
    keep: list[dict] = []
    dropped_overlap: list[dict] = []
    for e in entries:
        if e.get("origin") == "icloud_import":
            keep.append(e); continue
        candidates = {
            fuzz(e.get("title", "")),
            fuzz(e.get("folder", "")),
        }
        candidates.discard("")
        if candidates & icloud_keys:
            dropped_overlap.append(e)
        else:
            keep.append(e)

    # Step 2 — drop the manhwaread "The Mating of Elves" dup. We
    # match by (folder, source) because the iCloud-import marker is
    # already on both rows.
    final: list[dict] = []
    dropped_intra: list[dict] = []
    for e in keep:
        if (
            e.get("folder") == "The Mating of Elves"
            and e.get("source") == "manhwaread"
        ):
            dropped_intra.append(e)
            continue
        final.append(e)

    lib["entries"] = final
    LIBRARY_PATH.write_text(
        json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    print(f"\nLibrary: {before} → {len(final)} entries")
    print(f"  Dropped pre-iCloud overlaps:    {len(dropped_overlap)}")
    print(f"  Dropped intra-import duplicate: {len(dropped_intra)}")
    if dropped_overlap[:5]:
        print("\nSample of dropped pre-existing overlaps:")
        for e in dropped_overlap[:10]:
            print(f"  [{e.get('source','?'):13s}] {e.get('title','?')[:55]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
