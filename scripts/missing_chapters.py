#!/usr/bin/env python3
"""
missing_chapters.py — dry-run "Update All" that produces a report
of chapters present on any matched site but absent from iCloud.

Walks every library entry whose ``download_path`` points at iCloud
(or has any on-disk CBZs), probes the primary URL plus every
alternative source, normalises chapter numbers across sites
(``62.5`` ⇄ ``62-5``), and lists what's missing.

Output: ``missing_chapters_report.md`` at project root (gitignored).

Read-only — no downloads triggered, no library mutation. Safe to
re-run; uses the existing icloud_match_cache for repeat speed but
fetches chapter lists fresh each time (status caching wouldn't help
us here since we need the full list, not just status).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gui.bridge.library_bridge import (  # noqa: E402
    _chapter_numbers_on_disk,
    _max_chapter,
    _norm_chapter_number,
)
from src.providers import get_provider_for_url  # noqa: E402


LIBRARY_PATH = PROJECT_ROOT / "library.json"
REPORT_PATH = PROJECT_ROOT / "missing_chapters_report.md"
ICLOUD_ROOT = (
    Path.home() / "Library" / "Mobile Documents"
    / "com~apple~CloudDocs" / "Manga"
)


def _fuzz(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _fuzz_loose(s: str) -> str:
    """Strip TOP / END / Uncensored / Decensored / etc. suffix tokens
    before fuzzing — catches the 'Secret Class TOP' vs 'Secret Class'
    pairing that vanilla fuzz misses."""
    s = (s or "").lower()
    s = re.sub(
        r"\b(top|end|uncensored|decensored|raw|hot|complete)\b", "", s,
    )
    return re.sub(r"[^a-z0-9]+", "", s)


# Index iCloud folders once for fast resolution. Two keys per folder:
# strict + loose (suffix-stripped).
def _build_icloud_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    if not ICLOUD_ROOT.exists():
        return idx
    for p in ICLOUD_ROOT.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            idx.setdefault(_fuzz(p.name), p)
            idx.setdefault(_fuzz_loose(p.name), p)
    return idx


def _resolve_truth_folder(
    entry: dict, icloud_idx: dict[str, Path],
) -> Optional[Path]:
    """
    Return the folder whose CBZs represent what the user actually has
    for this library entry.

    Priority (revised after the dry-run bug — see commit log):
      1. iCloud folder via fuzzy match of title/folder (strict, then
         suffix-stripped). iCloud is the user's master copy; even if
         ``./downloads/<folder>/`` has a few stale re-downloads,
         they're not the truth set. Pre-existing library entries
         whose ``download_path = downloads`` AND have a same-named
         iCloud folder MUST resolve to iCloud, not the partial
         project-local copy.
      2. ``download_path / folder`` only if iCloud has nothing for
         this series at all — covers genuinely project-only entries
         (Strawberry Love etc.) that the user manages outside iCloud.
      3. None — no usable on-disk truth set.
    """
    # Try iCloud first — strict, then loose.
    for candidate in (entry.get("folder"), entry.get("title")):
        key = _fuzz(candidate or "")
        if key and key in icloud_idx:
            return icloud_idx[key]
    for candidate in (entry.get("folder"), entry.get("title")):
        key = _fuzz_loose(candidate or "")
        if key and key in icloud_idx:
            return icloud_idx[key]

    # No iCloud match → fall back to the project-local folder if
    # there is one with actual content.
    dp = entry.get("download_path") or ""
    fld = entry.get("folder") or ""
    if dp and fld:
        direct = Path(dp) / fld
        if _chapter_numbers_on_disk(direct):
            return direct

    return None

# Mild politeness delay between probes — each provider has its own
# per-host rate limiter, but spacing things out by a fraction of a
# second avoids burst-induced 403s on the looser sites.
_PROBE_PAUSE = 0.3


def _probe_site(url: str) -> tuple[set[str], Optional[str]]:
    """
    Fetch the chapter list at ``url`` and return
    ``(normalised_chapter_set, error)``. ``error`` is None on success.
    """
    provider = get_provider_for_url(url)
    if provider is None:
        return set(), "unsupported URL"
    try:
        code = provider.extract_code(url)
        chapters = provider.get_chapters(code) or []
    except Exception as exc:
        return set(), str(exc)
    return {_norm_chapter_number(c.number) for c in chapters if getattr(c, "number", None)}, None


def _format_chapter_list(missing: set[str], max_show: int = 12) -> str:
    """Sort numerically (best-effort) and join. Truncate to keep
    the report scrollable."""
    def keyf(n: str) -> float:
        try:
            return float(n)
        except ValueError:
            return 999_999.0
    ordered = sorted(missing, key=keyf)
    shown = ordered[:max_show]
    extra = len(ordered) - len(shown)
    if extra > 0:
        return ", ".join(shown) + f" *(+{extra} more)*"
    return ", ".join(shown)


def main() -> int:
    if not LIBRARY_PATH.exists():
        print(f"library.json not found at {LIBRARY_PATH}")
        return 1

    lib = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    entries = lib.get("entries", [])

    icloud_idx = _build_icloud_index()
    print(f"iCloud index: {len(icloud_idx)//2} folders")

    # Dedupe: if multiple library entries resolve to the SAME truth
    # folder (e.g. 'Secret Class' and 'Secret Class TOP' both map to
    # iCloud/Secret Class), only probe once. Keep the entry with the
    # richest alternative_sources list.
    by_folder: dict[Path, dict] = {}
    skipped_no_truth = 0
    for e in entries:
        truth = _resolve_truth_folder(e, icloud_idx)
        if truth is None:
            skipped_no_truth += 1
            continue
        existing = by_folder.get(truth)
        if existing is None or (
            len(e.get("alternative_sources") or [])
            > len(existing.get("alternative_sources") or [])
        ):
            by_folder[truth] = e

    print(f"Skipped {skipped_no_truth} library entries with no iCloud-side truth")
    print(f"Probing {len(by_folder)} distinct iCloud folders...")

    targets = []
    for truth, e in by_folder.items():
        on_disk = _chapter_numbers_on_disk(truth)
        if not on_disk:
            continue
        targets.append((e, truth, on_disk))

    print(f"Probing {len(targets)} library entries that have on-disk chapters...")

    rows = []
    t0 = time.time()
    for i, (entry, path, on_disk) in enumerate(targets, 1):
        title = entry.get("title", "?")
        on_disk_max = _max_chapter(on_disk)

        primary_url = entry.get("source_url", "") or ""
        all_sources: list[tuple[str, str]] = []  # (label, url)
        if primary_url:
            all_sources.append((entry.get("source", "primary"), primary_url))
        for alt in entry.get("alternative_sources") or []:
            au = alt.get("url")
            if au and au != primary_url:
                all_sources.append((alt.get("provider", "alt"), au))

        per_site: list[dict] = []
        for label, url in all_sources:
            site_chs, err = _probe_site(url)
            time.sleep(_PROBE_PAUSE)
            if err:
                per_site.append({
                    "site": label, "url": url, "error": err,
                    "missing_count": 0, "missing": set(),
                    "site_max": None,
                })
                continue
            missing = site_chs - on_disk
            per_site.append({
                "site": label, "url": url, "error": None,
                "missing_count": len(missing), "missing": missing,
                "site_max": _max_chapter(site_chs),
            })

        # Union of all missing across all sites. We deduplicate by
        # normalised chapter number so 62.5/62-5 don't double-count.
        union_missing: set[str] = set()
        for ps in per_site:
            union_missing |= ps["missing"]

        if not union_missing:
            continue  # nothing missing — skip from the report

        # Pick the recommended source: the site that lists the most
        # missing chapters (i.e. is most up-to-date). Ties broken by
        # order (primary first).
        per_site_with_missing = [p for p in per_site if p["missing"]]
        if per_site_with_missing:
            best = max(per_site_with_missing, key=lambda p: p["missing_count"])
        else:
            best = per_site[0] if per_site else None

        rows.append({
            "title": title,
            "icloud_max": on_disk_max,
            "icloud_count": len(on_disk),
            "missing": union_missing,
            "recommended": best,
            "per_site": per_site,
            "icloud_folder": entry.get("folder", ""),
        })

        if i % 10 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] {title[:40]} — running... ({time.time()-t0:.0f}s elapsed)")

    # ── Write the report ────────────────────────────────────────────
    rows.sort(key=lambda r: -len(r["missing"]))

    lines: list[str] = []
    lines.append("# Missing chapters — dry-run Update All")
    lines.append("")
    lines.append(f"Generated: **{time.strftime('%Y-%m-%d %H:%M:%S')}**")
    lines.append("")
    lines.append(f"- Library entries with on-disk chapters: **{len(targets)}**")
    lines.append(f"- Entries missing 1+ chapter on any site: **{len(rows)}**")
    lines.append(f"- Total missing chapters across all entries: **{sum(len(r['missing']) for r in rows)}**")
    lines.append("")
    lines.append("Each row shows the highest chapter in iCloud, the per-site count of missing chapters, and the recommended site to download from (the one with the most chapters past your current state).")
    lines.append("")
    lines.append("Format normalisation is applied: `62.5` and `62-5` count as the same chapter.")
    lines.append("")
    lines.append("## Entries with missing chapters")
    lines.append("")
    lines.append("| Title | iCloud max | Missing | Best source | Missing chapter numbers |")
    lines.append("|-------|-----------:|--------:|-------------|--------------------------|")
    for r in rows:
        title = r["title"].replace("|", "\\|")
        icl_max = r["icloud_max"]
        icl_max_str = f"{icl_max:g}" if icl_max >= 0 else "—"
        best = r["recommended"]
        best_str = f"`{best['site']}`" if best else "—"
        missing_str = _format_chapter_list(r["missing"])
        lines.append(
            f"| {title} | {icl_max_str} | {len(r['missing'])} | {best_str} | {missing_str} |"
        )

    lines.append("")
    lines.append("## Per-entry detail")
    lines.append("")
    for r in rows:
        lines.append(f"### {r['title']}")
        lines.append("")
        lines.append(f"- iCloud folder: `{r['icloud_folder']}` ({r['icloud_count']} chapters, max {r['icloud_max']:g})")
        lines.append(f"- Missing across all sites (deduped): **{len(r['missing'])}**")
        lines.append("")
        lines.append("| Site | Site max | Missing chs | Notes |")
        lines.append("|------|---------:|------------:|-------|")
        for ps in r["per_site"]:
            site_max = f"{ps['site_max']:g}" if ps["site_max"] is not None and ps["site_max"] >= 0 else "—"
            n = ps["missing_count"]
            note = ps["error"] or (_format_chapter_list(ps["missing"], max_show=8) if n else "—")
            note = note.replace("|", "\\|")
            lines.append(f"| `{ps['site']}` | {site_max} | {n} | {note} |")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"✓ Report written to {REPORT_PATH}")
    print(f"  {len(rows)} of {len(targets)} entries have missing chapters")
    print(f"  Total missing chapter-instances: {sum(len(r['missing']) for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
