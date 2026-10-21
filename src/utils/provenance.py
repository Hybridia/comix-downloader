"""
Source detection — work out which site a folder's chapters came from
by looking inside the files themselves rather than guessing by title.

Every CBZ this app builds carries ``ComicInfo.xml`` with the series URL
in ``<Web>`` (see ``src/formats/cbz.py``). That URL is ground truth:
it's literally where the chapter was downloaded from. Image filenames
are useless for this — the downloader renames every page to ``NNN.ext``
— and CBZs from other tools (Yen Press rips etc.) carry no site URL at
all, so they simply contribute nothing.

**iCloud constraint.** Most of the user's iCloud folders are
"cloud-only": the CBZ is a dataless placeholder and *any* read makes
macOS download the whole file. Scanning a few hundred series that way
would pull gigabytes, so we only open files that are already on this
Mac (``is_cloud_only`` checks the ``SF_DATALESS`` flag without
touching file contents). Results are persisted on the library entry
(``detected_sources``) and merged across scans, so a source found while
a file was local stays known after iCloud evicts it again.

Read-only: never writes anywhere near the scanned folder.
"""

import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .chapters import chapter_float, chapter_number_from_filename

# macOS stat flag for an evicted iCloud file (sys/stat.h SF_DATALESS).
_SF_DATALESS = 0x40000000

_WEB_RE = re.compile(r"<Web>\s*(.*?)\s*</Web>", re.IGNORECASE | re.DOTALL)


def _sort_num(n: str) -> float:
    v = chapter_float(n)
    return -1.0 if v is None else v


def is_cloud_only(path: Path) -> bool:
    """
    True if ``path`` is an iCloud placeholder whose bytes aren't on this
    Mac. Uses ``lstat`` flags only — reading the file would trigger the
    download we're trying to avoid. Always False on non-macOS.
    """
    try:
        return bool(getattr(os.lstat(path), "st_flags", 0) & _SF_DATALESS)
    except OSError:
        return True  # unreadable — treat like "not here", skip it


def read_source_url(cbz: Path) -> Optional[str]:
    """
    The ``<Web>`` URL from a CBZ's ComicInfo.xml, or None when the file
    is cloud-only, unreadable, or wasn't made by a supported site.
    """
    if is_cloud_only(cbz):
        return None
    try:
        with zipfile.ZipFile(cbz) as z:
            name = next(
                (n for n in z.namelist() if n.lower().endswith("comicinfo.xml")),
                None,
            )
            if not name:
                return None
            xml = z.read(name).decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    m = _WEB_RE.search(xml)
    url = (m.group(1).strip() if m else "")
    return url if url.startswith("http") else None


def scan_folder(folder: Path) -> dict:
    """
    Scan every locally-present CBZ under ``folder`` for its source URL.

    Returns::

        {
          "sources": [{"url", "provider", "chapters", "latest"}, ...],
          "local": <CBZs we could read>,
          "cloud_only": <CBZs skipped because they're not on this Mac>,
        }

    ``sources`` is sorted newest-first by the latest chapter each site
    supplied, so ``sources[0]`` is "where your most recent chapters
    came from".
    """
    from ..providers import get_provider_for_url
    from .library import _normalize_url

    by_url: dict[str, dict] = {}
    local = cloud_only = 0
    try:
        files = [p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() == ".cbz"]
    except OSError:
        files = []

    for cbz in files:
        if is_cloud_only(cbz):
            cloud_only += 1
            continue
        local += 1
        url = read_source_url(cbz)
        if not url:
            continue
        key = _normalize_url(url)
        src = by_url.get(key)
        if src is None:
            provider = get_provider_for_url(key)
            src = by_url[key] = {
                "url": key,
                "provider": getattr(provider, "name", "") if provider else "",
                "chapters": 0,
                "latest": "",
            }
        src["chapters"] += 1
        n = chapter_number_from_filename(cbz.stem)
        if n and _sort_num(n) > _sort_num(src["latest"]):
            src["latest"] = n

    sources = sorted(
        by_url.values(),
        key=lambda s: _sort_num(s["latest"]),
        reverse=True,
    )
    return {"sources": sources, "local": local, "cloud_only": cloud_only}


def merge_detected(previous: list, scanned: list) -> list:
    """
    Merge a fresh scan into the sources stored on a library entry.
    Sources seen now replace their stored copy (fresh counts); stored
    sources not seen now are kept — their files were probably evicted
    to iCloud since, which doesn't make the provenance any less true.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    merged = {s.get("url"): dict(s) for s in previous or [] if s.get("url")}
    for s in scanned:
        merged[s["url"]] = {**s, "last_seen_at": now}
    return sorted(
        merged.values(),
        key=lambda s: _sort_num(s.get("latest", "")),
        reverse=True,
    )
