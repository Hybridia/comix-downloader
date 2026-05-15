#!/usr/bin/env python3
"""
iCloud → Library importer (Phase 3).

Reads ``icloud_inventory.json`` and adds each matched entry to
``library.json`` so the manga shows up in the Library tab with the
correct status badge.

Scope per user: ONLY non-hentai providers count for import.
- ALLOWED:  toonily, manhwabuddy, manhwaread, manhwa18, mangadistrict,
            webtoonscan, mangafire, comix
- SKIPPED:  nhentai, hitomi, hentaifc, hentairead, hentaifox

For each iCloud entry, we pick the single best (highest-score)
match from the allowed providers, requiring at least **medium**
confidence. Entries with no allowed match are skipped — they stay
in the inventory for later review but aren't added to library.

Library entries are keyed by ``source_url``; if the URL is already
present we skip (no duplicates). The matched URL is preserved
verbatim so the new entry's "🔗 Website" button opens the right page.

Chapter numbers are extracted from the iCloud folder filenames so
``Update All`` knows what's already on disk. For ``per_chapter_cbz``
we read ``Chapter_NN.cbz`` patterns; for other formats we fall
back to ``1..N`` placeholders. (Not perfect for series with .5
chapters under volume packaging — but those are rare in the manhwa
formats this script targets.)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = PROJECT_ROOT / "icloud_inventory.json"
LIBRARY_PATH = PROJECT_ROOT / "library.json"
ICLOUD_ROOT = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "Manga"
)


# Allowed providers for import. Two groups:
#  - Serial-manhwa providers: produce library entries with real
#    chapter counts and potentially get "Update" probes for new
#    chapters when status is ongoing.
#  - Gallery (hentai) providers: produce library entries that are
#    always single-chapter "completed" — Update All naturally skips
#    them. We include them anyway so the user has the same URL /
#    badge / Open Website affordances on the Library tab as the
#    serial entries.
SERIAL_ALLOWED = {
    "toonily", "manhwabuddy", "manhwaread", "manhwa18",
    "mangadistrict", "webtoonscan", "mangafire", "comix",
}
GALLERY_ALLOWED = {
    "nhentai", "hentaifox", "hentairead", "hentaifc", "hitomi",
}
ALLOWED_PROVIDERS = SERIAL_ALLOWED | GALLERY_ALLOWED

# Confidence floor for import. The match script labels 'high' for ≥
# 0.85 similarity, 'medium' for ≥ 0.65. Below medium is not worth
# putting in the user-facing Library.
ALLOWED_CONFIDENCE = {"high", "medium"}


# ---- Chapter-number extraction from iCloud filenames -------------------

# Prefer "Chapter_NN" / "Chapter NN" / "ChNN" / "Episode NN" patterns —
# in that order — to avoid latching onto stray numbers in the title.
_CHAPTER_NUM_RE = re.compile(
    r"(?:chapter|chap|episode|ep|ch)[_\s\.\-]*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_TRAILING_NUM_RE = re.compile(r"\b(\d{1,4}(?:\.\d+)?)\s*$")


def _chapter_number_from_stem(stem: str) -> Optional[str]:
    m = _CHAPTER_NUM_RE.search(stem)
    if m:
        return m.group(1)
    m = _TRAILING_NUM_RE.search(stem)
    if m:
        return m.group(1)
    return None


def extract_chapter_numbers(folder_name: str, fmt: str, fallback_count: int) -> list[str]:
    """
    Return the chapter numbers actually present on disk for one
    iCloud manga folder. Read-only; never touches the iCloud tree.

    For formats where the filename carries the chapter number
    (``per_chapter_cbz`` / ``other_cbz``) we extract real numbers so
    a future ``Update`` knows precisely what's missing.

    For volume / single / image_folder / mixed formats we fall back
    to ``1..N`` placeholders since we don't actually know which
    chapter ranges are inside each volume CBZ.
    """
    folder = ICLOUD_ROOT / folder_name

    if fmt in ("per_chapter_cbz", "other_cbz", "numbered_cbz", "mixed"):
        numbers: list[str] = []
        try:
            for f in folder.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() != ".cbz":
                    continue
                n = _chapter_number_from_stem(f.stem)
                if n:
                    # Strip leading zeros to match the standard form
                    # used elsewhere in the library ("01" → "1").
                    try:
                        # Preserve ".5" suffix but drop pure-int padding.
                        if "." in n:
                            head, tail = n.split(".", 1)
                            n = f"{int(head)}.{tail}"
                        else:
                            n = str(int(n))
                    except ValueError:
                        pass
                    numbers.append(n)
        except (PermissionError, OSError):
            pass
        # Dedupe and sort numerically.
        seen: set[str] = set()
        unique = []
        for n in numbers:
            if n not in seen:
                seen.add(n); unique.append(n)
        unique.sort(key=lambda x: float(x) if re.match(r"^\d+(?:\.\d+)?$", x) else 0.0)
        if unique:
            return unique
        # Empty extraction: fall through to 1..N placeholder.

    if fmt == "single_cbz":
        return ["1"]

    if fallback_count > 0:
        return [str(i) for i in range(1, fallback_count + 1)]
    return []


# ---- Library entry construction ----------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_url(url: str) -> str:
    """Same logic as src/utils/library.py::_normalize_url so primary-
    key dedupe matches the existing entries exactly."""
    from urllib.parse import urlparse, urlunparse
    if not url:
        return ""
    p = urlparse(url.strip())
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, p.params, p.query, ""))


def _safe_title(title: str) -> str:
    """Mirrors MangaInfo.get_safe_title for filesystem-safe folders."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    return safe.strip()[:100]


def build_library_entry(
    inv_entry: dict, match: dict,
) -> dict:
    """
    Construct a fresh library entry from an iCloud inventory entry
    and its best match. Matches the schema in src/utils/library.py.

    Path strategy: ``download_path`` + ``folder`` point at the EXISTING
    iCloud folder, so the Library tab's "📂 Folder" button opens the
    real files. We do not copy any .cbz into the project — only the
    metadata + chapter numbers we read off iCloud get persisted.

    Heads-up about Update behaviour: when the user clicks "Update" on
    an ongoing entry later, the download pipeline writes NEW chapters
    to the config-driven downloads path (``config.json:download_path``),
    not back to iCloud. Old chapters stay in iCloud, new ones land
    elsewhere. The library entry still knows about both via its
    ``chapters`` dict, but the physical files end up split. That's
    intentional — we're respecting the user's rule that iCloud
    contents aren't modified.
    """
    now = _now_iso()
    title = match.get("title_on_site") or inv_entry.get("title") or "Unknown"
    chapters_numbers = extract_chapter_numbers(
        inv_entry["folder_name"],
        inv_entry.get("format", ""),
        inv_entry.get("chapter_count", 0),
    )
    # ``downloaded_at`` is set to ``added_at`` so the existing
    # set-difference logic in UpdateProbeWorker treats these as
    # "already known" — Update will then only fetch genuinely-new
    # chapter numbers from the site.
    chapters_dict = {
        n: {"title": "", "downloaded_at": now}
        for n in chapters_numbers
    }

    # status_manual=True only when the user marked the folder with END.
    # Otherwise the auto status from cross-site lookup wins, and a
    # future Update probe can refresh it via the normal flow.
    user_marked = bool(inv_entry.get("marked_complete_by_user"))
    effective = inv_entry.get("effective_status") or "unknown"
    status = effective if effective != "unknown" else ""

    return {
        "source": match["provider"],
        "source_url": _normalize_url(match["url"]),
        "manga_id": None,
        "hash_id": None,
        "manga_code": None,
        "title": title,
        "alt_titles": [],
        "poster_url": "",
        # Gallery / hentai providers are unambiguously NSFW; serial
        # providers can be NSFW too (toonily, mangadistrict, etc.) but
        # we don't know per-entry without a Manga-info fetch, so leave
        # those False here. The next probe via Update sets it correctly.
        "is_nsfw": match["provider"] in GALLERY_ALLOWED,
        "artists": [],
        "tags": [],
        "output_format": "cbz",
        # Point at the existing iCloud location so "Open Folder" works
        # and the user can see their real files. NOTE: the running
        # downloader still writes NEW chapters to config.download_path
        # rather than mutating iCloud — see the docstring.
        "download_path": str(ICLOUD_ROOT),
        "folder": inv_entry["folder_name"],
        "last_updated_at": now,
        "status_auto": status if not user_marked else "",
        "added_at": now,
        "last_checked_at": now,
        "status_manual": user_marked,
        "status": "completed" if user_marked else status,
        "chapters": chapters_dict,
        # Marker so we can recognise these later — e.g. if we add a
        # "Hide iCloud-only entries" filter or a separate import
        # report.
        "origin": "icloud_import",
    }


# ---- Importer -----------------------------------------------------------

def best_match(inv_entry: dict) -> Optional[dict]:
    candidates = [
        m for m in (inv_entry.get("matches") or [])
        if m.get("provider") in ALLOWED_PROVIDERS
        and m.get("match_confidence") in ALLOWED_CONFIDENCE
    ]
    if not candidates:
        return None
    # Highest score wins; ties broken by provider order in the list
    # (which mirrors the search loop, i.e. roughly preference).
    return max(candidates, key=lambda m: m.get("match_score", 0))


def main() -> int:
    if not INVENTORY_PATH.exists():
        print(f"Inventory not found at {INVENTORY_PATH}.")
        return 1

    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    try:
        lib = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        lib = {"version": 1, "entries": []}

    existing_urls = {
        _normalize_url(e.get("source_url", "")) for e in lib.get("entries", [])
    }

    added: list[dict] = []
    skipped_existing: list[str] = []
    skipped_no_match: list[str] = []
    by_provider: dict[str, int] = {}

    for entry in inv["entries"]:
        match = best_match(entry)
        if not match:
            skipped_no_match.append(entry.get("title", "?"))
            continue

        url = _normalize_url(match["url"])
        if url in existing_urls:
            skipped_existing.append(entry.get("title", "?"))
            continue

        lib_entry = build_library_entry(entry, match)
        lib["entries"].append(lib_entry)
        existing_urls.add(url)
        added.append(lib_entry)
        by_provider[match["provider"]] = by_provider.get(match["provider"], 0) + 1

    # Persist library atomically.
    tmp = LIBRARY_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    tmp.replace(LIBRARY_PATH)

    # Report.
    print(f"\nImport summary:")
    print(f"  Added to library:       {len(added)}")
    print(f"  Skipped (already in):   {len(skipped_existing)}")
    print(f"  Skipped (no confident match in allowed providers): {len(skipped_no_match)}")
    print()
    print("Added by provider:")
    for prov, n in sorted(by_provider.items(), key=lambda kv: -kv[1]):
        print(f"  {prov:15s} {n}")

    # Sample list of additions for quick visual confirmation.
    if added:
        print("\nSample of added entries:")
        for e in added[:10]:
            chap_n = len(e["chapters"])
            print(f"  [{e['source']:13s}] {e['title'][:55]:55s}  "
                  f"status={e['status'] or 'unknown':10s}  ch={chap_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
