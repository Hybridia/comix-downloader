"""
Update checker — "what's new for the series I have?" without
downloading anything.

For one library entry:

1. Read what's on disk (CBZ filenames in ``download_path/folder`` —
   usually the user's iCloud folder). Filenames only, so cloud-only
   files aren't pulled down.
2. Detect which site(s) the chapters came from (``provenance.py``),
   merging with what earlier scans found.
3. Probe candidate sites in trust order — detected sources first, then
   the entry's primary URL, then ``alternative_sources`` — and diff
   each site's chapter list against disk. Alternatives are only probed
   when their recorded latest chapter beats everything found so far,
   to keep a full-library check from hitting every mirror.
4. Split missing chapters into ``newer`` (past the highest chapter on
   disk — what an "update" means) and ``gaps`` (holes below it, shown
   but not pre-selected: often deliberate, e.g. skipped side stories).
5. Recommend the source offering the most new chapters, tie-broken in
   favour of the site the files actually came from, then the primary.

The result is a plain JSON-able dict so the GUI can persist it in
``pending_updates.json`` and show it for approval later.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .chapters import (
    chapter_float,
    chapter_numbers_on_disk,
    max_chapter,
    norm_chapter_number,
)
from .logger import get_logger

logger = get_logger(__name__)


def manga_info_to_dict(manga, manga_code: str) -> dict:
    """Mirror MangaBridge's manga_dict shape so DownloadBridge
    accepts it untouched."""
    return {
        "manga_id": manga.manga_id,
        "hash_id": manga.hash_id,
        "title": manga.title,
        "alt_titles": list(manga.alt_titles or []),
        "manga_type": manga.manga_type or "Unknown",
        "status": manga.status or "Unknown",
        "poster_url": manga.poster_url or "",
        "year": manga.year or 0,
        "rated_avg": manga.rated_avg or 0,
        "follows_total": manga.follows_total or 0,
        "is_nsfw": bool(manga.is_nsfw),
        "description": manga.description or "",
        "latest_chapter": manga.latest_chapter or "",
        "original_language": manga.original_language or "",
        "manga_code": manga_code,
        "source": manga.source,
        "source_url": manga.source_url or "",
        "artists": list(manga.artists or []),
        "tags": list(manga.tags or []),
    }


def chapter_to_dict(ch) -> dict:
    return {
        "chapter_id": ch.chapter_id,
        "number": str(ch.number),
        "title": ch.title or "",
        "volume": ch.volume or "",
        "group_name": ch.group_name or "Unknown",
        "pages_count": ch.pages_count,
        "image_urls": list(ch.image_urls or []),
        "selected": True,
    }


def entry_folder(entry: dict) -> Optional[Path]:
    """Folder this entry's chapters live in, or None if malformed."""
    dp = (entry or {}).get("download_path") or ""
    folder = (entry or {}).get("folder") or ""
    if not dp or not folder:
        return None
    return Path(dp) / folder


ICLOUD_ROOT = (
    Path.home() / "Library" / "Mobile Documents"
    / "com~apple~CloudDocs" / "Manga"
)


def _fuzz(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _fuzz_loose(s: str) -> str:
    """Also drop TOP / END / Uncensored / … tokens ("Secret Class TOP"
    vs the iCloud folder "Secret Class"; "[MOTION] X" vs "X"). Underscores
    count as spaces: safe folder names turn "(Uncensored)" into "_Uncensored_"."""
    s = re.sub(r"\b(top|end|uncensored|decensored|raw|hot|complete|motion)\b", "",
               (s or "").lower().replace("_", " "))
    return re.sub(r"[^a-z0-9]+", "", s)


def _icloud_folder_for(entry: dict, root: Optional[Path] = None) -> Optional[Path]:
    """
    The user's iCloud Manga subfolder for this entry, by fuzzy match on
    folder name then title (strict, then suffix-stripped). Same rules as
    ``scripts/missing_chapters.py``. Lists directory names only — and
    only subfolders, so ``Manga/.reader_state.json`` is never touched.
    """
    try:
        dirs = [p for p in (root or ICLOUD_ROOT).iterdir()
                if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return None
    for fuzz in (_fuzz, _fuzz_loose):
        idx: dict[str, Path] = {}
        for d in dirs:
            idx.setdefault(fuzz(d.name), d)
        for candidate in (entry.get("folder"), entry.get("title")):
            key = fuzz(candidate or "")
            if key and key in idx:
                return idx[key]
    return None


def resolve_folder(entry: dict) -> Optional[Path]:
    """
    Where this entry's chapters actually are. The recorded
    ``download_path/folder`` wins when it has chapters; otherwise look
    for the series in iCloud — the common case being an in-app download
    the user later moved into iCloud, leaving the entry pointing at a
    ``./downloads/...`` folder that no longer exists.
    """
    recorded = entry_folder(entry)
    if recorded and chapter_numbers_on_disk(recorded):
        return recorded
    icloud = _icloud_folder_for(entry)
    if icloud and chapter_numbers_on_disk(icloud):
        return icloud
    return recorded


def downloads_root() -> Path:
    """config.json's ``download_path`` (relative paths are project-root based)."""
    from .config import ConfigManager, _PROJECT_ROOT
    p = Path(ConfigManager().get("download_path", "downloads") or "downloads").expanduser()
    return p if p.is_absolute() else _PROJECT_ROOT / p


def chapters_on_disk(entry: dict, folder: Optional[Path],
                     downloads_root: Optional[Path] = None) -> set[str]:
    """
    Chapters you already have: the series' folder (usually iCloud) plus
    this series' folder(s) in the downloads folder — chapters downloaded
    but not yet moved into iCloud. Without the second part every check
    re-lists those chapters as new. Downloads folders are matched by the
    entry's folder / title / alt titles and each site's title (the
    downloader names folders after the site's title), with the same
    strict-then-loose fuzzy rules as the iCloud lookup. Names only —
    nothing is opened.
    """
    have = chapter_numbers_on_disk(folder) if folder else set()
    for d in downloads_folders(entry, folder, downloads_root):
        have |= chapter_numbers_on_disk(d)
    return have


def _own_keys(entry: dict) -> set[str]:
    """Fuzzy keys of the series' own names (folder + title, not alt titles)."""
    return {f(n) for n in (entry.get("folder"), entry.get("title")) if n for f in (_fuzz, _fuzz_loose)} - {""}


def downloads_folders(entry: dict, folder: Optional[Path],
                      downloads_root: Optional[Path] = None,
                      entries: Optional[list[dict]] = None) -> list[Path]:
    """This series' folder(s) in the downloads folder (not ``folder`` itself).

    A folder can match through an alt title or another site's title, but a
    folder named after *another* series in the Library (its own title or
    folder) belongs to that series: "College Grades Skyrocketing" lists
    "Study Buddies" as an alt title, and a wrong "also on" match calls
    Secret Life "Secret Class". ``entries`` = the Library (loaded when None).
    """
    root = downloads_root if downloads_root is not None else globals()["downloads_root"]()
    try:
        dirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return []
    names = [entry.get("folder"), entry.get("title"), *(entry.get("alt_titles") or []),
             *[a.get("title_on_site") for a in entry.get("alternative_sources") or []]]
    keys = {f(n) for n in names if n for f in (_fuzz, _fuzz_loose)} - {""}
    own = _own_keys(entry)
    if entries is None:
        try:
            from .library import shared
            entries = list(shared().list_entries())
        except Exception:
            entries = []
    me = (entry.get("source_url") or "").rstrip("/").lower()
    others: set[str] = set()
    for e in entries:
        if (e.get("source_url") or "").rstrip("/").lower() != me:
            others |= _own_keys(e)
    out = []
    for d in dirs:
        if folder and d.resolve() == Path(folder).resolve():
            continue
        k = {_fuzz(d.name), _fuzz_loose(d.name)}
        if not k & keys:
            continue
        if not k & own and k & others:
            continue  # another series' own folder
        out.append(d)
    return out


def _num_key(n: str) -> float:
    v = chapter_float(n)
    return -1.0 if v is None else v


def _probe(url: str, on_disk: set[str], on_disk_max: float) -> dict:
    """Fetch one site's chapter list and diff it against disk."""
    from ..providers import get_provider_for_url

    out = {
        "url": url, "provider": "", "title": "", "latest": "",
        "remote_count": 0, "newer": [], "gaps": [], "error": "",
        "manga": None, "status": None,
    }
    provider = get_provider_for_url(url)
    if provider is None:
        out["error"] = "Unsupported site"
        return out
    out["provider"] = getattr(provider, "name", "")
    try:
        code = provider.extract_code(url)
        manga = provider.get_manga_info(code)
        if not manga:
            out["error"] = "Site returned no info (removed?)"
            return out
        chapters = provider.get_chapters(code) or []
    except Exception as exc:
        out["error"] = str(exc) or exc.__class__.__name__
        return out

    out["title"] = manga.title or ""
    out["status"] = getattr(manga, "status", None)
    out["manga"] = manga_info_to_dict(manga, code)
    out["remote_count"] = len(chapters)

    seen: set[str] = set()
    newer, gaps = [], []
    latest = ""
    for ch in chapters:
        n = norm_chapter_number(getattr(ch, "number", ""))
        if not n or n in seen:
            continue  # same number from several scanlation groups
        seen.add(n)
        if _num_key(n) > _num_key(latest):
            latest = n
        if n in on_disk:
            continue
        d = chapter_to_dict(ch)
        d["norm"] = n
        v = chapter_float(n)
        if v is None or v > on_disk_max:
            newer.append(d)
        else:
            gaps.append(d)
    newer.sort(key=lambda d: _num_key(d["norm"]))
    gaps.sort(key=lambda d: _num_key(d["norm"]))
    out["newer"], out["gaps"], out["latest"] = newer, gaps, latest
    return out


def check_entry(entry: dict, cancelled=lambda: False) -> dict:
    """
    Run the full check for one library entry. Side effects are limited
    to library bookkeeping: ``detected_sources`` and (on a successful
    primary probe) ``last_checked_at`` / ``status_auto``.
    """
    from . import provenance
    from .library import _normalize_url, shared as _library

    library_url = entry.get("source_url") or ""
    result = {
        "library_url": library_url,
        "title": entry.get("title") or library_url,
        "poster_url": entry.get("poster_url") or "",
        "folder": str(entry_folder(entry) or ""),
        "on_disk_count": 0,
        "on_disk_max": "",
        "cloud_only": 0,
        "detected": [],
        "sources": [],
        "recommended": -1,
        "error": "",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    folder = resolve_folder(entry)
    result["folder"] = str(folder or "")
    if folder and folder != entry_folder(entry):
        # Found it in iCloud — repoint the entry so Folder / Update /
        # the next check all use the right place.
        try:
            _library().relocate(library_url, str(folder.parent), folder.name)
        except Exception as exc:
            logger.warning("relocate failed: %s", exc)
    on_disk = chapters_on_disk(entry, folder) if folder else set()
    if not on_disk:
        # Nothing on disk ⇒ not a series being followed (abandoned
        # in-app download, per-volume CBZs, …). Same rule as Update.
        return result
    on_disk_max = max_chapter(on_disk)
    result["on_disk_count"] = len(on_disk)
    result["on_disk_max"] = norm_chapter_number(
        str(int(on_disk_max)) if on_disk_max.is_integer() else str(on_disk_max)
    )

    # ── Which sites did these chapters come from? ────────────────────
    scan = provenance.scan_folder(folder)
    result["cloud_only"] = scan["cloud_only"]
    # CBZs waiting in ./downloads are always on this Mac — read their site too,
    # so chapters downloaded from another site count before they reach iCloud.
    scanned = {s["url"]: dict(s) for s in scan["sources"]}
    for d in downloads_folders(entry, folder):
        for s in provenance.scan_folder(d)["sources"]:
            cur = scanned.get(s["url"])
            if cur is None:
                scanned[s["url"]] = dict(s)
            else:
                cur["chapters"] += s["chapters"]
                if _num_key(s["latest"]) > _num_key(cur["latest"]):
                    cur["latest"] = s["latest"]
    detected = provenance.merge_detected(entry.get("detected_sources"), list(scanned.values()))
    result["detected"] = detected
    if detected != (entry.get("detected_sources") or []):
        try:
            _library().set_detected_sources(library_url, detected)
        except Exception as exc:
            logger.warning("set_detected_sources failed: %s", exc)

    # ── Candidate order: detected → primary → alternatives ──────────
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    def _add(url, **flags):
        key = _normalize_url(url or "")
        if not key or key in seen_urls:
            # Already queued — just add the flag (detected + primary).
            for c in candidates:
                if c["url"] == key:
                    for k, v in flags.items():
                        c[k] = c.get(k) or v
            return
        seen_urls.add(key)
        candidates.append({"url": key, **flags})

    for s in detected:
        _add(s.get("url"), is_detected=True)
    # Sites chapters were downloaded from (recorded at download time) —
    # always checked, even while those chapters still sit in ./downloads.
    downloaded_last: dict[str, str] = {}
    for s in entry.get("download_sources") or []:
        key = _normalize_url(s.get("url") or "")
        if key:
            downloaded_last.setdefault(key, str(s.get("last_chapter") or ""))
            _add(key, is_downloaded=True)
    _add(library_url, is_primary=True)
    for alt in entry.get("alternative_sources") or []:
        _add(alt.get("url"), is_alt=True,
             alt_latest=float(alt.get("chapter_count") or 0))

    best_latest = on_disk_max
    for c in candidates:
        if cancelled():
            break
        if c.get("is_alt") and not (c.get("is_detected") or c.get("is_primary") or c.get("is_downloaded")):
            # Only worth a network round-trip if the enricher saw this
            # mirror further along than anything we've found so far.
            if c["alt_latest"] <= best_latest:
                continue
        probe = _probe(c["url"], on_disk, on_disk_max)
        probe["is_detected"] = bool(c.get("is_detected"))
        probe["is_primary"] = bool(c.get("is_primary"))
        probe["is_downloaded"] = bool(c.get("is_downloaded"))
        probe["downloaded_last"] = downloaded_last.get(c["url"], "")
        if probe["is_primary"] and not probe["error"]:
            try:
                _library().mark_checked(library_url, manga_status=probe["status"])
            except Exception:
                pass
        probe.pop("status", None)
        best_latest = max(best_latest, _num_key(probe["latest"]))
        result["sources"].append(probe)

    # ── Recommend ────────────────────────────────────────────────────
    best, best_key = -1, None
    for i, s in enumerate(result["sources"]):
        if not s["newer"]:
            continue
        key = (len(s["newer"]), s["is_detected"] or s.get("is_downloaded", False), s["is_primary"])
        if best_key is None or key > best_key:
            best, best_key = i, key
    result["recommended"] = best

    if best < 0 and result["sources"] and all(s["error"] for s in result["sources"]):
        result["error"] = result["sources"][0]["error"]
    return result


def has_updates(result: dict) -> bool:
    return (result or {}).get("recommended", -1) >= 0
