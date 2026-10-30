"""
Is a file in the iCloud Manga folder really in iCloud yet?

Copying into the iCloud folder finishes in seconds, but macOS uploads the
file to Apple's servers afterwards. Both Comix Downloader and MyDex only
call a downloads copy "safe to remove" once its iCloud twin is uploaded,
and show upload progress after "Copy to iCloud".

Asks macOS (``URLResourceValues``: isUploaded / isUploading /
uploadingError) through a tiny Swift helper compiled on first use —
Python has no direct access to those flags. Reads metadata only; nothing
is downloaded or changed. States per path: ``uploaded``, ``uploading``,
``waiting`` (queued), ``error: <reason>``, ``not_icloud``, ``missing``,
or ``unknown`` (helper unavailable — treated as not uploaded).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Iterable, Optional

SOURCE = Path(__file__).with_name("icloud_status.swift")
HELPER = Path.home() / "Library" / "Caches" / "comix-downloader" / "icloud-status"


def _helper(run: Callable) -> Path:
    if not HELPER.exists() or HELPER.stat().st_mtime < SOURCE.stat().st_mtime:
        HELPER.parent.mkdir(parents=True, exist_ok=True)
        r = run(["swiftc", "-O", str(SOURCE), "-o", str(HELPER)], capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError(f"couldn't build the iCloud status helper: {(r.stderr or '').strip()[:200]}")
    return HELPER


def upload_details(paths: Iterable[Path], run: Callable = subprocess.run,
                   helper: Optional[Path] = None) -> dict[str, dict]:
    """Per path: ``{"state", "done", "size"}`` — bytes uploaded so far and
    the file's size (uploaded files count fully, queued ones as 0)."""
    paths = [str(p) for p in paths]
    if not paths:
        return {}
    out = {p: {"state": "unknown", "done": 0, "size": _size(p)} for p in paths}
    try:
        exe = helper or _helper(run)
        r = run([str(exe), *paths], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return out
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or parts[1] not in out:
            continue
        d = out[parts[1]]
        state = parts[0]
        if state == "error":
            d["state"] = "error: " + (parts[2] if len(parts) > 2 else "?")
        else:
            d["state"] = state
        if state == "uploaded":
            d["done"] = d["size"]
        elif state == "uploading" and len(parts) >= 4:
            try:
                d["done"] = min(int(parts[2]), d["size"] or int(parts[3]))
            except ValueError:
                pass
    return out


def upload_status(paths: Iterable[Path], run: Callable = subprocess.run,
                  helper: Optional[Path] = None) -> dict[str, str]:
    """Per path, just the state word (see the module docstring)."""
    return {p: d["state"] for p, d in upload_details(paths, run, helper).items()}


def _size(p: str) -> int:
    try:
        return Path(p).stat().st_size
    except OSError:
        return 0


def item_state(state: str) -> str:
    """One word for the UI: uploaded / uploading / waiting / retrying /
    missing. An upload error isn't final — iCloud keeps retrying by itself
    (``brctl status`` shows the item as "needs-upload, active") — so it
    reads as "retrying"."""
    if state.startswith("error"):
        return "retrying"
    if state in ("uploaded", "uploading", "missing"):
        return state
    return "waiting"


def summarize(states: dict[str, str]) -> dict:
    """Counts for a progress line. ``reasons``: iCloud's error message →
    how many files report it (shown once, not per file)."""
    words = [item_state(s) for s in states.values()]
    reasons: dict[str, int] = {}
    for s in states.values():
        if s.startswith("error: "):
            reasons[s[7:]] = reasons.get(s[7:], 0) + 1
    uploaded = words.count("uploaded")
    return {"total": len(states), "uploaded": uploaded, "uploading": words.count("uploading"),
            "waiting": words.count("waiting") + words.count("missing"), "retrying": words.count("retrying"),
            "pending": len(states) - uploaded, "reasons": reasons}


def summarize_details(details: dict[str, dict]) -> dict:
    """``summarize`` plus ``done_bytes`` / ``total_bytes`` (Finder's "22,5 MB of 228,7 MB")."""
    s = summarize({p: d["state"] for p, d in details.items()})
    s["done_bytes"] = sum(d["done"] for d in details.values())
    s["total_bytes"] = sum(d["size"] for d in details.values())
    return s
