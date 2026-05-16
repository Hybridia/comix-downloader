#!/usr/bin/env python3
"""
library_relocate_to_icloud.py — make every library entry read its
"what I have" set from iCloud.

For each library entry whose ``origin`` is NOT ``icloud_import``:

1. **Has iCloud counterpart** (fuzzy match — strict, then with
   ``TOP / END / Uncensored / Decensored / Raw / Hot / Complete``
   suffix words stripped):
   - Rewrite ``download_path`` to the iCloud Manga root and ``folder``
     to the matched iCloud folder name. After this, the rewritten
     UpdateProbeWorker reads the actual iCloud files as the truth set,
     so re-downloads of existing chapters won't happen anymore.
   - Tag with ``origin = "icloud_import"`` and ``relocated_at`` so
     future passes can recognise these as ground-truth-aligned.

2. **Two entries collapse to the same iCloud folder** (e.g.
   ``Secret Class`` + ``Secret Class TOP``, ``Four's a Crowd × 2``):
   keep the one with the richer ``alternative_sources`` list (ties
   broken by chapter count, then arbitrary). Drop the other.

3. **No iCloud counterpart**: drop the entry entirely. These are
   either manga the user explicitly said shouldn't track
   (Strawberry Love, Please Put Them On, Bastard… wait, Bastard
   IS in iCloud — so it gets relocated) or single-shot doujinshi
   that don't belong in a Library tab focused on serial follows.

Run before deleting ``./downloads/`` — that way every remaining
library entry has its truth set in iCloud, and Update will only
fetch genuinely-new chapters.

Always backs up library.json with a timestamped ``.bak`` first.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = PROJECT_ROOT / "library.json"
ICLOUD_ROOT = (
    Path.home() / "Library" / "Mobile Documents"
    / "com~apple~CloudDocs" / "Manga"
)


def fuzz(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def fuzz_loose(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(
        r"\b(top|end|uncensored|decensored|raw|hot|complete)\b", "", s,
    )
    return re.sub(r"[^a-z0-9]+", "", s)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_icloud_index() -> dict[str, Path]:
    """Map ``fuzz(name) -> iCloud folder Path`` (strict + loose)."""
    idx: dict[str, Path] = {}
    if not ICLOUD_ROOT.exists():
        return idx
    for p in ICLOUD_ROOT.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            idx.setdefault(fuzz(p.name), p)
            idx.setdefault(fuzz_loose(p.name), p)
    return idx


def _resolve_icloud_folder(entry: dict, idx: dict[str, Path]) -> Path | None:
    """Return the matching iCloud folder for an entry, or None."""
    for cand in (entry.get("folder"), entry.get("title")):
        k = fuzz(cand or "")
        if k and k in idx:
            return idx[k]
    for cand in (entry.get("folder"), entry.get("title")):
        k = fuzz_loose(cand or "")
        if k and k in idx:
            return idx[k]
    return None


def _entry_richness(e: dict) -> tuple[int, int]:
    """
    Sort key for dedupe: prefer entries with more alternative_sources,
    then more chapters tracked.
    """
    return (
        len(e.get("alternative_sources") or []),
        len(e.get("chapters") or {}),
    )


def main() -> int:
    if not LIBRARY_PATH.exists():
        print(f"library.json not found at {LIBRARY_PATH}")
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = LIBRARY_PATH.with_suffix(f".json.bak.relocate-{ts}")
    shutil.copy2(LIBRARY_PATH, backup)
    print(f"Backed up to {backup.name}")

    lib = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    entries = lib.get("entries", [])
    icloud_idx = _build_icloud_index()
    print(f"iCloud index: {len(icloud_idx)//2} folders")

    relocated: list[dict] = []
    removed_no_icloud: list[dict] = []
    untouched: list[dict] = []

    # First pass: per-entry decide relocate vs remove vs keep-as-is.
    for e in entries:
        if e.get("origin") == "icloud_import":
            untouched.append(e)
            continue
        icloud_p = _resolve_icloud_folder(e, icloud_idx)
        if icloud_p is None:
            removed_no_icloud.append(e)
            continue
        # Relocate this entry in place. Mark the relocation so
        # downstream passes can recognise that this entry's truth
        # folder is now iCloud.
        e["download_path"] = str(ICLOUD_ROOT)
        e["folder"] = icloud_p.name
        e["origin"] = "icloud_import"
        e["relocated_at"] = _now_iso()
        relocated.append(e)

    # Second pass: dedupe by iCloud folder. After relocation, multiple
    # entries can point at the same (download_path, folder) pair —
    # keep the richest, drop the rest.
    surviving: list[dict] = []
    by_folder: dict[tuple[str, str], list[dict]] = {}
    for e in untouched + relocated:
        key = (e.get("download_path") or "", e.get("folder") or "")
        by_folder.setdefault(key, []).append(e)

    dropped_dup: list[dict] = []
    for key, group in by_folder.items():
        if len(group) == 1:
            surviving.append(group[0])
            continue
        # Multiple entries → keep the richest.
        ranked = sorted(group, key=_entry_richness, reverse=True)
        surviving.append(ranked[0])
        for loser in ranked[1:]:
            dropped_dup.append(loser)

    lib["entries"] = surviving

    LIBRARY_PATH.write_text(
        json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # ── Report ──────────────────────────────────────────────────────
    print()
    print(f"Library entries: {len(entries)} → {len(surviving)}")
    print(f"  Untouched (already icloud_import):     {len(untouched)}")
    print(f"  Relocated to iCloud:                   {len(relocated)}")
    print(f"  Removed (no iCloud counterpart):       {len(removed_no_icloud)}")
    print(f"  Removed (duplicate of another entry):  {len(dropped_dup)}")

    if relocated[:5]:
        print("\nSample relocations:")
        for e in relocated[:8]:
            print(f"  [{e['source']:13s}] {e['title'][:48]:48s} -> {e['folder']}")

    if removed_no_icloud:
        print("\nRemoved (no iCloud folder):")
        for e in removed_no_icloud:
            print(f"  [{e['source']:13s}] {e['title']}")

    if dropped_dup:
        print("\nRemoved (dedup):")
        for e in dropped_dup:
            print(f"  [{e['source']:13s}] {e['title']}  (kept the richer alt)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
