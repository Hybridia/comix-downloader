#!/usr/bin/env python3
"""
iCloud Manga Inventory — read-only walk of
``~/Library/Mobile Documents/com~apple~CloudDocs/Manga`` that produces
a structured report of every manga + chapter count.

We deliberately keep this read-only — no folder is renamed, no file
is moved. The user explicitly carved out the iCloud tree as off-limits
for any kind of mutation.

Output (written to project root):

- ``icloud_inventory.json`` — machine-readable; one record per top-level
  manga folder. Used later by the Phase-2 cross-site matcher to look
  up status (Completed / Ongoing) on supported providers.
- ``icloud_inventory.md`` — human-readable summary you can scroll.

Both files are gitignored — the inventory contains private title
names.

Conventions baked into the cleanup:

- A folder name ending in ``END`` is the user's "this series is
  finished" marker. We record ``marked_complete_by_user = True`` and
  strip ``END`` from the display title. This will translate to a
  ``status_manual = "completed"`` library override when Phase 3 runs
  the import.
- Underscores stand for various punctuation in filesystem-safe
  versions (apostrophes, commas, colons, parens). We don't try to
  un-mangle them in Phase 1 — the cleaned ``title`` keeps them as-is
  and Phase 2's fuzzy matcher will handle the comparison.
- Trailing whitespace is stripped (the iCloud sync occasionally
  preserves accidental trailing spaces in folder names).

Format detection — each manga folder falls into one of:

- ``per_chapter_cbz`` — ``Chapter_1.cbz`` … ``Chapter_N.cbz``
- ``per_volume_cbz``  — ``<Title> v01.cbz`` … ``<Title> vNN.cbz``
- ``numbered_cbz``    — CBZs with bare numeric stems (ambiguous)
- ``image_folders``   — subfolders each holding loose page images
- ``pdf``             — one or more PDF files
- ``mixed``           — a combination of the above
- ``empty``           — folder exists but contains no readable units

``chapter_count`` is the number of *units* — chapters for
``per_chapter_cbz`` / ``image_folders``, volumes for
``per_volume_cbz``, files for ``pdf``. Counting actual chapters
inside multi-chapter volume CBZs would require unzipping which we
skip for speed — Phase 1 is meant to be quick.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


# ----- Config ------------------------------------------------------------

ICLOUD_MANGA_ROOT = (
    Path.home()
    / "Library"
    / "Mobile Documents"
    / "com~apple~CloudDocs"
    / "Manga"
)

# Project root = parent of this script's parent (scripts/ → project/).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = PROJECT_ROOT / "icloud_inventory.json"
OUT_MD = PROJECT_ROOT / "icloud_inventory.md"


# ----- Title cleanup -----------------------------------------------------

_END_SUFFIX_RE = re.compile(r"\s+END\s*$", re.IGNORECASE)


def clean_title(folder_name: str) -> tuple[str, bool]:
    """
    Return ``(display_title, marked_complete_by_user)``.

    Strips trailing whitespace and the ``END`` user-marker suffix. Does
    NOT try to un-mangle underscores into apostrophes/commas — that's a
    Phase-2 concern when we have a target site title to compare against.
    """
    raw = folder_name.rstrip()
    m = _END_SUFFIX_RE.search(raw)
    if m:
        return raw[: m.start()].rstrip(), True
    return raw, False


# ----- Format detection --------------------------------------------------

_CBZ_CHAPTER_RE = re.compile(
    r"^chapter[_\s\-]*(\d+(?:[.\-]\d+)?)\b", re.IGNORECASE,
)
# Volume markers: ``v01``, ``vol 12``, ``Volume 5``. Numbers MUST be
# zero-padded or standalone to avoid matching "v" inside a word.
_CBZ_VOLUME_RE = re.compile(
    r"\b(?:vol(?:ume)?[_\s\.]*|v)(\d{1,3})\b", re.IGNORECASE,
)
# Pure numeric stem: "001.cbz", "12.cbz", "1.5.cbz" — ambiguous between
# chapter and volume.
_CBZ_NUMERIC_RE = re.compile(r"^(\d+(?:\.\d+)?)$")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name.startswith("._")


def _classify_cbz(stem: str) -> str:
    """Classify a CBZ filename stem into 'chapter' / 'volume' / 'numeric' / 'other'."""
    if _CBZ_CHAPTER_RE.search(stem):
        return "chapter"
    # Strip the leading manga-title prefix before checking volume —
    # ``Akashic Records … v01 (2017) (Digital) …`` has the ``v01`` in
    # the middle.
    if _CBZ_VOLUME_RE.search(stem):
        return "volume"
    if _CBZ_NUMERIC_RE.match(stem):
        return "numeric"
    return "other"


def _detect_format_and_count(folder: Path) -> tuple[str, int, dict]:
    """
    Walk ONE manga folder. Return ``(format, chapter_count, details)``.

    ``details`` is a free-form dict for the JSON output that surfaces
    anything interesting we noticed (multiple formats, very few
    units, etc.).
    """
    cbz_chapters = 0
    cbz_volumes = 0
    cbz_numeric = 0
    cbz_other = 0
    pdfs = 0
    image_subfolders = 0
    other_files = 0
    other_dirs = 0

    try:
        entries = list(folder.iterdir())
    except (PermissionError, OSError):
        return "unreadable", 0, {"error": "iterdir failed"}

    for entry in entries:
        name = entry.name
        if _is_hidden(name):
            continue
        if entry.is_dir():
            # Image folder = directory containing any image file at
            # the top level. Don't recurse deeply — Phase 1 is fast.
            has_image = False
            try:
                for sub in entry.iterdir():
                    if (
                        sub.is_file()
                        and sub.suffix.lower() in _IMAGE_EXTS
                    ):
                        has_image = True
                        break
            except (PermissionError, OSError):
                pass
            if has_image:
                image_subfolders += 1
            else:
                other_dirs += 1
            continue
        # Files
        ext = entry.suffix.lower()
        if ext == ".cbz":
            stem = entry.stem
            kind = _classify_cbz(stem)
            if kind == "chapter":
                cbz_chapters += 1
            elif kind == "volume":
                cbz_volumes += 1
            elif kind == "numeric":
                cbz_numeric += 1
            else:
                cbz_other += 1
        elif ext == ".pdf":
            pdfs += 1
        else:
            other_files += 1

    total_cbz = cbz_chapters + cbz_volumes + cbz_numeric + cbz_other
    units = total_cbz + pdfs + image_subfolders

    # Format: pick the single dominant kind. "mixed" if two kinds are
    # both non-trivial.
    kinds = {
        "per_chapter_cbz": cbz_chapters,
        "per_volume_cbz": cbz_volumes,
        "numbered_cbz": cbz_numeric,
        "other_cbz": cbz_other,
        "pdf": pdfs,
        "image_folders": image_subfolders,
    }
    non_zero = sorted(
        [(v, k) for k, v in kinds.items() if v > 0], reverse=True,
    )

    if not non_zero:
        fmt = "empty"
    elif len(non_zero) == 1:
        fmt = non_zero[0][1]
    else:
        # Multiple kinds. If one dominates ≥ 80 % of units, take that;
        # else label mixed.
        top_count, top_name = non_zero[0]
        if total_cbz + pdfs + image_subfolders > 0 and top_count / units >= 0.8:
            fmt = top_name
        else:
            fmt = "mixed"

    # Special-case: exactly one CBZ with no chapter / volume pattern is
    # almost certainly a single-volume doujinshi/one-shot. Surface it
    # as ``single_cbz`` so the Phase-2 matcher can route it to the
    # gallery-style providers (nhentai / hitomi / hentaifc / hentairead /
    # hentaifox) rather than the serial-manhwa providers.
    if fmt == "other_cbz" and total_cbz == 1 and pdfs == 0 and image_subfolders == 0:
        fmt = "single_cbz"

    details: dict = {
        "cbz_chapter_files": cbz_chapters,
        "cbz_volume_files": cbz_volumes,
        "cbz_numeric_files": cbz_numeric,
        "cbz_other_files": cbz_other,
        "pdf_files": pdfs,
        "image_subfolders": image_subfolders,
        "other_files": other_files,
        "other_dirs": other_dirs,
    }
    if fmt == "mixed":
        details["mixed_breakdown"] = {k: v for k, v in kinds.items() if v}

    return fmt, units, details


# ----- Folder size (best-effort) -----------------------------------------

def _folder_size_bytes(folder: Path) -> int:
    """
    Sum file sizes under ``folder``. Uses ``os.scandir`` so it's
    reasonably fast even on iCloud-synced trees. Returns 0 on any
    permission error rather than aborting.
    """
    total = 0
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += _folder_size_bytes(Path(entry.path))
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return total


# ----- Main inventory walk -----------------------------------------------

def build_inventory(root: Path, prior: Optional[dict] = None) -> dict:
    """
    Walk ``root`` and produce an inventory snapshot.

    If ``prior`` is supplied (a previously-saved inventory dict), the
    Phase-2 fields ``matches`` and ``effective_status`` are carried
    forward for folders whose name is unchanged. This way you can
    re-run the inventory after adding a few new manga to iCloud and
    the existing Phase-2 results stay intact — only the genuinely-new
    folders will need a fresh cross-site lookup.
    """
    if not root.exists():
        raise SystemExit(
            f"iCloud Manga folder not found at: {root}\n"
            "Check that iCloud Drive is enabled and the 'Manga' folder exists."
        )

    prior_by_folder: dict[str, dict] = {}
    if prior and isinstance(prior.get("entries"), list):
        for e in prior["entries"]:
            fn = e.get("folder_name")
            if fn:
                prior_by_folder[fn] = e

    folders = sorted(
        (
            p for p in root.iterdir()
            if p.is_dir() and not _is_hidden(p.name)
        ),
        key=lambda p: p.name.lower(),
    )

    entries = []
    carried = 0
    fresh = 0
    for folder in folders:
        title, marked_complete = clean_title(folder.name)
        fmt, count, details = _detect_format_and_count(folder)
        size_bytes = _folder_size_bytes(folder)
        entry = {
            "folder_name": folder.name,
            "title": title,
            "marked_complete_by_user": marked_complete,
            "chapter_count": count,
            "format": fmt,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 1),
            "details": details,
            "matches": [],
            "effective_status": "unknown",
        }
        # Carry forward Phase-2 results if we've seen this folder
        # before. Folder name is the key — if the user renamed it,
        # we'll treat it as a new folder (intentional: a rename
        # usually signals a title change that warrants re-search).
        if folder.name in prior_by_folder:
            old = prior_by_folder[folder.name]
            entry["matches"] = old.get("matches", []) or []
            entry["effective_status"] = (
                old.get("effective_status") or "unknown"
            )
            carried += 1
        else:
            fresh += 1
        entries.append(entry)

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_root": str(root),
        "total_titles": len(entries),
        "total_size_bytes": sum(e["size_bytes"] for e in entries),
        "entries": entries,
        # Telemetry, not load-bearing — but helpful when you re-run
        # after adding folders so you can see at-a-glance how many
        # rows are brand-new and need a cross-site search pass.
        "_carried_from_prior": carried,
        "_fresh_folders": fresh,
    }


# ----- Markdown report ---------------------------------------------------

def write_markdown(inv: dict, out: Path) -> None:
    entries = inv["entries"]
    total_titles = len(entries)
    total_units = sum(e["chapter_count"] for e in entries)
    total_size_gb = inv["total_size_bytes"] / (1024 ** 3)
    user_completed = sum(1 for e in entries if e["marked_complete_by_user"])

    fmt_counts: dict[str, int] = {}
    for e in entries:
        fmt_counts[e["format"]] = fmt_counts.get(e["format"], 0) + 1

    lines: list[str] = []
    lines.append("# iCloud Manga Inventory")
    lines.append("")
    lines.append(f"Generated: **{inv['generated_at']}**  ")
    lines.append(f"Source: `{inv['source_root']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Titles**: {total_titles}")
    lines.append(f"- **Units (chapters/volumes/files)**: {total_units}")
    lines.append(f"- **On disk**: {total_size_gb:.2f} GB")
    lines.append(f"- **Marked complete by user (END suffix)**: {user_completed}")
    lines.append("")
    lines.append("**Formats**:")
    for fmt, n in sorted(fmt_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{fmt}` — {n}")
    lines.append("")
    lines.append("## Entries")
    lines.append("")
    lines.append("| # | Title | Chapters | Format | Size | END? |")
    lines.append("|---|-------|----------|--------|------|------|")
    for i, e in enumerate(entries, 1):
        marker = "✓" if e["marked_complete_by_user"] else ""
        # Pipes inside titles would break the row — escape them.
        title = e["title"].replace("|", "\\|")
        lines.append(
            f"| {i} | {title} | {e['chapter_count']} | "
            f"`{e['format']}` | {e['size_mb']} MB | {marker} |"
        )
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


# ----- Entry point -------------------------------------------------------

def main() -> int:
    print(f"Scanning {ICLOUD_MANGA_ROOT}", flush=True)

    prior: Optional[dict] = None
    if OUT_JSON.exists():
        try:
            prior = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = None

    inv = build_inventory(ICLOUD_MANGA_ROOT, prior=prior)

    OUT_JSON.write_text(
        json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    write_markdown(inv, OUT_MD)

    total_units = sum(e["chapter_count"] for e in inv["entries"])
    print(
        f"\n✓ {inv['total_titles']} titles · "
        f"{total_units} units · "
        f"{inv['total_size_bytes'] / (1024**3):.2f} GB",
        flush=True,
    )
    if prior:
        carried = inv.get("_carried_from_prior", 0)
        fresh = inv.get("_fresh_folders", 0)
        print(
            f"  Carried over from previous inventory: {carried}",
            flush=True,
        )
        print(
            f"  Fresh folders (need cross-site lookup): {fresh}",
            flush=True,
        )
    print(f"  JSON: {OUT_JSON}", flush=True)
    print(f"  MD:   {OUT_MD}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
