#!/usr/bin/env python3
"""
Enrich library entries with alternative sources.

For each library entry that came from the iCloud import, look up
every confident (high/medium) match recorded in
``icloud_inventory.json`` and store the non-primary ones as
``alternative_sources = [{provider, url, title_on_site, status,
latest_chapter, match_score, match_confidence}]`` on the entry.

Why: users want to compare the same series across sites — see
which has the most chapters, jump to each one. Right now the
library remembers only the single best match per entry, and the
runners-up sit in the inventory invisible to the GUI.

How chapter counts are populated:
- We pull ``latest_chapter`` from the cached ``manga_info`` rows in
  ``icloud_match_cache.json``. For URLs that don't have it cached
  (older cache rows), the script triggers a fresh
  ``provider.get_manga_info()`` call so ``latest_chapter`` is
  always present in the output. The cache is updated in place.

Run after ``icloud_to_library.py``. Safe to re-run — alternatives
are recomputed from scratch each time so refining the inventory
and re-running flushes stale entries.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the match script's cache + manga-info pipeline so the cache
# format stays consistent.
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import icloud_match as M  # noqa: E402

INVENTORY_PATH = PROJECT_ROOT / "icloud_inventory.json"
LIBRARY_PATH = PROJECT_ROOT / "library.json"


def fuzz(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def parse_chapter_count(latest_chapter: str) -> int:
    """
    Coerce a ``latest_chapter`` string (the highest chapter number
    the site reports) into an int for comparison. Handles common
    shapes: "215", "215.5", "Chapter 215", "Ch. 47b". Returns 0 on
    failure — callers should treat that as "unknown".
    """
    if not latest_chapter:
        return 0
    m = re.search(r"(\d+)(?:\.\d+)?", str(latest_chapter))
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def main() -> int:
    if not LIBRARY_PATH.exists():
        print(f"library.json not found at {LIBRARY_PATH}.")
        return 1
    if not INVENTORY_PATH.exists():
        print(f"icloud_inventory.json not found at {INVENTORY_PATH}.")
        return 1

    # Back up before mutating.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = LIBRARY_PATH.with_suffix(f".json.bak.enrich-{ts}")
    shutil.copy2(LIBRARY_PATH, backup)
    print(f"Backed up to {backup.name}")

    lib = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    cache = M.load_cache()

    # Index inventory entries by fuzzed folder name so we can map
    # library entries back to their iCloud row (origin == icloud_import
    # entries store the iCloud folder verbatim in `folder`).
    inv_by_folder: dict[str, dict] = {
        fuzz(e.get("folder_name", "")): e for e in inv.get("entries", [])
    }

    enriched_count = 0
    with_multi = 0
    fresh_fetches = 0

    # Also index inventory entries by fuzzed TITLE so we can pair
    # up pre-existing library entries (which may have been downloaded
    # in-app before any iCloud import) with their iCloud row via
    # title-similarity. Folder-name match takes priority since it's
    # stronger; title is the fallback.
    inv_by_title: dict[str, dict] = {}
    for ie in inv.get("entries", []):
        key = fuzz(ie.get("title", ""))
        if key and key not in inv_by_title:
            inv_by_title[key] = ie

    for entry in lib["entries"]:
        # Resolve the right inventory row. Three lookups, in order:
        # 1. fuzz(library.folder) → fuzz(inventory.folder_name)
        # 2. fuzz(library.title)  → fuzz(inventory.folder_name)
        # 3. fuzz(library.title)  → fuzz(inventory.title)
        # This catches both icloud-imported entries (1) AND pre-
        # existing entries whose title matches an iCloud folder (2/3).
        inv_entry = (
            inv_by_folder.get(fuzz(entry.get("folder", "")))
            or inv_by_folder.get(fuzz(entry.get("title", "")))
            or inv_by_title.get(fuzz(entry.get("title", "")))
        )
        if not inv_entry:
            entry["alternative_sources"] = []
            continue

        primary_url = M._normalize_url(entry.get("source_url", "")) \
            if hasattr(M, "_normalize_url") else entry.get("source_url", "")
        # Normalise via the match script's helper — re-import the
        # function here so URLs compare cleanly. The inventory matches
        # use raw URLs while library entries store normalised ones.
        from src.utils.library import _normalize_url as _norm_url
        primary_url = _norm_url(entry.get("source_url", ""))

        alternatives: list[dict] = []
        seen: set[str] = {primary_url}
        for m in inv_entry.get("matches", []):
            if m.get("match_confidence") not in ("high", "medium"):
                continue
            url = _norm_url(m.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)

            # Pull cached manga_info (with latest_chapter). If the
            # cache row predates the field, fetch fresh to populate it.
            info_before = url in cache.get("manga_info", {})
            cached = M.cached_manga_full(cache, url)
            if not info_before:
                fresh_fetches += 1
            elif "latest_chapter" not in cached:
                # Old cache row — invalidate so next call re-fetches.
                del cache["manga_info"][url]
                cached = M.cached_manga_full(cache, url)
                fresh_fetches += 1

            latest = cached.get("latest_chapter", "") or ""
            alternatives.append({
                "provider": m["provider"],
                "url": url,
                "title_on_site": cached.get("title")
                                 or m.get("title_on_site", ""),
                "status": cached.get("normalized_status") or "",
                "latest_chapter": latest,
                "chapter_count": parse_chapter_count(latest),
                "match_score": m.get("match_score", 0),
                "match_confidence": m.get("match_confidence", ""),
            })

        # Sort: most chapters first, ties broken by match score. This
        # way the GUI's first chip is the "biggest" alternative.
        alternatives.sort(
            key=lambda a: (a["chapter_count"], a["match_score"]),
            reverse=True,
        )

        entry["alternative_sources"] = alternatives
        if alternatives:
            enriched_count += 1
            if len(alternatives) >= 2:
                with_multi += 1

    # Persist library + cache.
    LIBRARY_PATH.write_text(
        json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    M.save_cache(cache)

    print(f"\nEnriched library: {len(lib['entries'])} entries")
    print(f"  with ≥1 alternative source: {enriched_count}")
    print(f"  with ≥2 alternative sources: {with_multi}")
    print(f"  fresh manga_info fetches:   {fresh_fetches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
