#!/usr/bin/env python3
"""
iCloud Manga Match — Phase 2 of the cross-reference pipeline.

Reads ``icloud_inventory.json`` (produced by ``icloud_inventory.py``),
searches each supported provider for every entry, and populates each
entry's ``matches`` + ``effective_status`` fields in place.

Provider-by-provider strategy (only the ones with usable search):

- **toonily / mangadistrict** — Madara AJAX search at
  ``/wp-admin/admin-ajax.php`` (``action=wp-manga-search-manga``).
  Returns JSON {data: [{label|title, url}, ...]}. Fast, exact.
- **manhwaread / manhwabuddy / hentairead / hentaifox / nhentai** —
  HTML search page (``/?s=Q`` or ``/search/?q=Q``). Parse result
  anchors with per-site regex.

Routing:
- ``single_cbz`` entries → gallery providers (nhentai / hentairead /
  hentaifox). These are doujinshi / one-shots; routing them to manhwa
  serial providers would only produce false positives.
- All other formats → manhwa serial providers (toonily /
  manhwabuddy / manhwaread / mangadistrict).

What we DON'T cover yet, and why:
- **webtoonscan** — search works but requires FlareSolverr; adding it
  means each query is +5-15s and a hard external dep. Defer.
- **manhwa18** — no search URL we've found that returns parseable
  results. Could be patched if we find the pattern.
- **hentaifc** — same.
- **hitomi** — JS-rendered search; non-trivial.
- **mangafire** — Playwright per query; too slow at this scale.
- **toomics** — paywalled, search isn't useful to us.

For each search hit above a low confidence floor (0.45), we fetch
the manga page via the existing provider machinery to get the
authoritative status. Aggregate to ``effective_status``:

- Any provider says ``completed`` or ``cancelled`` → ``completed``
- Else any provider says ``ongoing`` → ``ongoing``
- Else ``unknown``

User's ``END`` suffix flag (from Phase 1) overrides to ``completed``
regardless of what sites say — that's the explicit user signal.

The script is resumable: it writes ``icloud_match_cache.json`` for
search results and re-uses partial inventory state, so an
interrupted run picks up at the next un-processed entry.
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi import requests as cffi_requests

from src.providers import get_provider_for_url
from src.utils.library import normalize_status

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = PROJECT_ROOT / "icloud_inventory.json"
CACHE_PATH = PROJECT_ROOT / "icloud_match_cache.json"


# ---- Title helpers ------------------------------------------------------

# Trailing parens with noisy metadata: (Digital), (DigitalMangaFan),
# [English], _English_ — strip before searching. These come from the
# scanlation tag conventions; they hurt matches against site titles.
_NOISE_BRACKETS_RE = re.compile(
    r"[\(\[\{][^()\[\]\{\}]{0,40}[\)\]\}]"
)
# Sites that bury alt titles after a `|` or `-` (e.g. "X | 私のママ").
_AFTER_SEPARATOR_RE = re.compile(r"^([^|/]+)")


def normalize_query(folder_title: str) -> str:
    """
    Produce a search-friendly string from a folder title.

    Heuristics tuned to the iCloud folder conventions:
    - Strip leading ``_C\\d+_`` conference codes ("_C101_") — those are
      doujinshi conference codes, not part of the title.
    - Strip leading ``_<Artist>_ _<Author>_`` decorations.
    - Replace underscores with spaces (they stand in for various
      punctuation that we don't need for searching).
    - Drop bracketed/parenthesised metadata.
    - Collapse runs of whitespace.
    """
    t = folder_title
    # Drop a leading "_C\d+_ _Group_ _Author_" decoration. These show
    # up on Japanese doujinshi releases:
    #   "_C101_ _ACTIVA _SMAC__ Roshutsu Otome Chichi Comic"
    t = re.sub(r"^\s*_C\d+_\s*", "", t)
    # Replace underscores with spaces; leave hyphens alone.
    t = t.replace("_", " ")
    # Drop bracketed / parenthesised tail metadata.
    while True:
        new = _NOISE_BRACKETS_RE.sub(" ", t)
        if new == t:
            break
        t = new
    # Some titles have "X | Y" with the secondary alt-title after the
    # pipe; the first half is enough for fuzzy matching.
    m = _AFTER_SEPARATOR_RE.match(t)
    if m:
        t = m.group(1)
    return re.sub(r"\s+", " ", t).strip()


# Modifier words that frequently appear in iCloud folder names but
# rarely in the site title for the same series. Stripping them gives
# us a fallback query that catches the "Title Uncensored" vs "Title"
# mismatch we saw on the first pass.
_MODIFIER_WORDS = {
    "uncensored", "decensored", "censored",
    "full color", "fullcolor", "colorized",
    "top", "end",
    "digital", "hardcover", "complete", "complete edition",
    "translated", "english",
}


def query_variants(folder_title: str) -> list[str]:
    """
    Generate a fallback chain of search queries, in priority order.

    Why multiple variants: the first pass missed series like
    "From Pauper to Prince (Uncensored)" because the site indexes
    it as plain "From Pauper to Prince" — the "Uncensored" suffix
    was driving the similarity score down. Trying a stripped form
    as a fallback recovers those.

    Returns 1-3 strings — order matters; first hit with usable
    matches wins.
    """
    primary = normalize_query(folder_title)
    if not primary:
        return []

    out = [primary]

    # Variant 2: strip modifier words.
    stripped = primary
    for word in _MODIFIER_WORDS:
        stripped = re.sub(
            rf"\b{re.escape(word)}\b", "", stripped, flags=re.IGNORECASE,
        )
    stripped = re.sub(r"\s+", " ", stripped).strip(" -_")
    if stripped and stripped.lower() != primary.lower():
        out.append(stripped)

    # Variant 3: first 3 substantive words. Last-resort for very long
    # titles where the actual series name is at the start.
    words = stripped.split() if stripped else primary.split()
    if len(words) > 3:
        short = " ".join(words[:3])
        if short.lower() not in (v.lower() for v in out):
            out.append(short)

    return out


def normalize_for_compare(s: str) -> str:
    """Aggressive normalization for similarity scoring (both sides)."""
    if not s:
        return ""
    s = _html.unescape(s).lower()
    # Remove apostrophes / quotes / underscores BEFORE punct stripping
    # so "X's" → "xs" matches "x s" → "xs".
    s = re.sub(r"[‘’'`_]", "", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def similarity(a: str, b: str) -> float:
    """
    Custom similarity that's tolerant of one side carrying extra
    metadata (the iCloud folder names often have leading scanlation
    group / artist circles that aren't on the site).

    Returns the MAX of two scores:
    - ``SequenceMatcher.ratio()`` — classic edit-distance ratio.
      Penalises asymmetric length; near-perfect when both sides match.
    - ``longest_match.size / len(shorter)`` × 0.95 — containment.
      How much of the shorter string appears verbatim in the longer.
      Slight penalty so that an exact match still scores higher than
      a near-containment.
    """
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b)
    base = sm.ratio()
    shorter = min(len(a), len(b))
    if shorter == 0:
        return base
    longest = sm.find_longest_match(0, len(a), 0, len(b))
    contain = (longest.size / shorter) * 0.95
    return max(base, contain)


def confidence_label(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


# ---- Search adapters ----------------------------------------------------

# Default cffi-requests impersonation; matches the project's main
# session for site fingerprinting.
_IMPERSONATE = "chrome120"
_TIMEOUT = 20

# Polite per-provider gap to avoid hammering after a burst of queries.
# The site's own rate limits are stricter than this; SessionManager's
# token bucket handles its half, this one covers our direct cffi_
# requests calls.
_PROVIDER_PAUSE_SEC = 0.4


def _aj_search_madara(base_url: str, query: str) -> list[dict]:
    """
    AJAX path on standard Madara sites: POST
    /wp-admin/admin-ajax.php with action=wp-manga-search-manga.
    Returns JSON {success: true, data: [{label|title, url}, ...]}.
    """
    r = cffi_requests.post(
        f"{base_url}/wp-admin/admin-ajax.php",
        data={"action": "wp-manga-search-manga", "title": query},
        headers={
            "Referer": base_url + "/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    try:
        payload = r.json()
    except Exception:
        return []
    if not isinstance(payload, dict) or not payload.get("success"):
        return []
    data = payload.get("data") or []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        title = (item.get("label") or item.get("title")
                 or item.get("value") or "")
        if url and title:
            out.append({"title": title.strip(), "url": url})
    return out


# Per-site HTML adapters use a regex anchored on the canonical
# result-link shape. We deliberately don't try to parse the page
# layout — one regex per site, keyed off the site's manga URL pattern,
# is robust and fast.

_NHENTAI_HIT_RE = re.compile(
    # /g/<id>/ → cover anchor with the title as alt text on the
    # inner img, or in the next h-tag. We capture both the id and the
    # caption text for similarity.
    r'<a\s+class="cover"\s+href="(/g/(\d+)/)"[^>]*>'
    r'.*?<img[^>]*\balt="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)


def _html_search_nhentai(query: str) -> list[dict]:
    r = cffi_requests.get(
        "https://nhentai.to/search/",
        params={"q": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    out: list[dict] = []
    for path, gid, alt in _NHENTAI_HIT_RE.findall(r.text):
        out.append({
            "title": _html.unescape(alt).strip(),
            "url": f"https://nhentai.to{path}",
        })
    return out


_HENTAIREAD_HIT_RE = re.compile(
    # `<a href="https://hentairead.com/hentai/<slug>/" ...>Title</a>`
    # is repeated for cover-thumb AND title; we dedupe on URL below.
    r'<a[^>]+href="(https://hentairead\.com/hentai/[^"]+)"[^>]*>'
    r'([^<]+)</a>',
    re.IGNORECASE,
)


def _html_search_hentairead(query: str) -> list[dict]:
    r = cffi_requests.get(
        "https://hentairead.com/",
        params={"s": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for url, title in _HENTAIREAD_HIT_RE.findall(r.text):
        if url in seen:
            continue
        seen.add(url)
        title = _html.unescape(title).strip()
        if not title:
            continue
        out.append({"title": title, "url": url})
    return out


_HENTAIFOX_HIT_RE = re.compile(
    # Hentaifox lists results as `<h2 class="g_title"><a href="/gallery/<id>/">Title</a></h2>`.
    r'<h2[^>]*class="g_title"[^>]*>\s*<a\s+href="(/gallery/\d+/)"[^>]*>'
    r'([^<]+)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _html_search_hentaifox(query: str) -> list[dict]:
    r = cffi_requests.get(
        "https://hentaifox.com/search/",
        params={"q": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    out: list[dict] = []
    for path, title in _HENTAIFOX_HIT_RE.findall(r.text):
        out.append({
            "title": _html.unescape(title).strip(),
            "url": f"https://hentaifox.com{path}",
        })
    return out


_MANHWAREAD_HIT_RE = re.compile(
    r'<a[^>]+href="(https://manhwaread\.com/manhwa/[^"]+)"[^>]*>'
    r'([^<]+)</a>',
    re.IGNORECASE,
)


def _html_search_manhwaread(query: str) -> list[dict]:
    r = cffi_requests.get(
        "https://manhwaread.com/",
        params={"s": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for url, title in _MANHWAREAD_HIT_RE.findall(r.text):
        # Anchor text can be "Read" (cover-area click target). Skip
        # those — only keep links whose anchor contains real title
        # text.
        title = _html.unescape(title).strip()
        if not title or title.lower() == "read":
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url})
    return out


_MANHWABUDDY_HIT_RE = re.compile(
    # `<a href="/manhwa/<slug>/" title="<Series Title>">`. Relative
    # URLs. The title attribute is the canonical series name; the
    # anchor inner text is sometimes a chapter ref.
    r'<a\s+href="(/manhwa/[^"/]+/)"\s+title="([^"]+)"',
    re.IGNORECASE,
)


def _html_search_manhwabuddy(query: str) -> list[dict]:
    r = cffi_requests.get(
        "https://manhwabuddy.com/",
        params={"s": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for path, title in _MANHWABUDDY_HIT_RE.findall(r.text):
        if path in seen:
            continue
        seen.add(path)
        out.append({
            "title": _html.unescape(title).strip(),
            "url": f"https://manhwabuddy.com{path}",
        })
    return out


def _search_toonily(query: str) -> list[dict]:
    return _aj_search_madara("https://toonily.com", query)


def _search_mangadistrict(query: str) -> list[dict]:
    return _aj_search_madara("https://mangadistrict.com", query)


def _api_search_comix(query: str) -> list[dict]:
    """
    comix.to's /api/v1/manga endpoint accepts a ``keyword=`` param
    (NOT ``q``/``search``/``title`` — confusingly, those return the
    full catalogue unfiltered). Returns JSON
    {result: {items: [{hid, title, status, type, ...}]}}.

    Status comes for free in this payload, so the matcher's
    later get_manga_info call is redundant but harmless — and keeps
    the code path uniform with other providers.
    """
    r = cffi_requests.get(
        "https://comix.to/api/v1/manga",
        params={"keyword": query},
        impersonate=_IMPERSONATE,
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        return []
    try:
        payload = r.json()
    except Exception:
        return []
    items = (payload.get("result") or {}).get("items") or []
    out: list[dict] = []
    for it in items:
        hid = it.get("hid")
        title = it.get("title")
        if not (hid and title):
            continue
        # Synthesise the user-friendly URL the existing ComixProvider
        # accepts: ``/title/<hid>-<slug>``. The slug is cosmetic — the
        # provider's ``extract_code`` only reads ``hid``.
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        out.append({
            "title": title,
            "url": f"https://comix.to/title/{hid}-{slug}" if slug
                   else f"https://comix.to/title/{hid}",
        })
    return out


# Provider registry. The order matters only for cosmetic reasons
# (matches are sorted by score later anyway).
SERIAL_PROVIDERS: dict[str, Any] = {
    "comix":         _api_search_comix,
    "toonily":       _search_toonily,
    "mangadistrict": _search_mangadistrict,
    "manhwaread":    _html_search_manhwaread,
    "manhwabuddy":   _html_search_manhwabuddy,
}
GALLERY_PROVIDERS: dict[str, Any] = {
    "nhentai":     _html_search_nhentai,
    "hentairead":  _html_search_hentairead,
    "hentaifox":   _html_search_hentaifox,
}


def providers_for_entry(entry: dict) -> list[tuple[str, Any]]:
    """Pick the provider set based on the inventory entry's ``format``."""
    fmt = entry.get("format", "")
    if fmt == "single_cbz":
        return list(GALLERY_PROVIDERS.items())
    # Volume / chapter / image-folder / mixed / numbered → manhwa
    # serial sites. (Gallery sites would also have hits sometimes but
    # the false-positive rate is too high to be worth it.)
    return list(SERIAL_PROVIDERS.items())


# ---- Cache --------------------------------------------------------------

def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "searches": {}, "manga_info": {}}


def save_cache(cache: dict) -> None:
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _cache_key_search(provider: str, query: str) -> str:
    return f"{provider}::{query.lower()}"


def cached_search(
    cache: dict, provider: str, query: str, fn: Any,
) -> list[dict]:
    key = _cache_key_search(provider, query)
    if key in cache["searches"]:
        return cache["searches"][key]
    try:
        results = fn(query)
    except Exception as exc:
        print(f"      [{provider}] search error: {exc}")
        results = []
    cache["searches"][key] = results
    return results


def cached_manga_status(
    cache: dict, url: str,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Resolve a candidate URL into ``(normalized_status, raw_status,
    site_title)`` using the existing provider machinery. Cached so a
    second pass over the same URL is free.

    The cache also captures ``latest_chapter`` (the highest chapter
    number the site reports) so a separate "which site has the most
    chapters" comparison can be built without an extra HTTP per URL.
    Older cache rows without that field stay valid — they're just
    treated as if latest_chapter were unknown.
    """
    if url in cache["manga_info"]:
        cached = cache["manga_info"][url]
        return (
            cached.get("normalized_status") or "",
            cached.get("raw_status"),
            cached.get("title"),
        )

    provider = get_provider_for_url(url)
    if provider is None:
        cache["manga_info"][url] = {"normalized_status": "", "title": None}
        return "", None, None

    try:
        code = provider.extract_code(url)
        manga = provider.get_manga_info(code)
    except Exception as exc:
        print(f"      [{provider.name}] get_manga_info failed: {exc}")
        cache["manga_info"][url] = {"normalized_status": "", "title": None}
        return "", None, None

    if not manga:
        cache["manga_info"][url] = {"normalized_status": "", "title": None}
        return "", None, None

    raw = (getattr(manga, "status", "") or "")
    normalized = normalize_status(raw)
    title = getattr(manga, "title", "") or ""
    latest = getattr(manga, "latest_chapter", None) or ""
    cache["manga_info"][url] = {
        "normalized_status": normalized,
        "raw_status": raw,
        "title": title,
        "latest_chapter": latest,
    }
    return normalized, raw, title


def cached_manga_full(cache: dict, url: str) -> dict:
    """
    Lookup-or-fetch convenience that returns the full cached manga
    record ``{normalized_status, raw_status, title, latest_chapter}``
    for a URL. Triggers a fetch (via ``cached_manga_status``) only
    when the URL hasn't been resolved before.
    """
    if url not in cache["manga_info"]:
        cached_manga_status(cache, url)
    return cache["manga_info"].get(url, {})


# ---- Per-entry matching -------------------------------------------------

# Floor below which we drop matches entirely. We keep medium and low
# matches (per user preference) but drop "garbage" results so the
# report doesn't drown in noise.
_KEEP_FLOOR = 0.45
# Above this we bother fetching status. Below this, we record the
# match for user review but don't burn an HTTP call.
_FETCH_THRESHOLD = 0.55


def aggregate_status(matches: list[dict], user_marked: bool) -> str:
    """
    Apply the precedence: user marker > completed > ongoing > unknown.

    Only the SINGLE BEST match per provider counts. Without this,
    comix.to's search routinely returns several similar-titled
    siblings (e.g. searching "Chained Soldier" returns the real one
    AND two unrelated "Soldier" entries) — and the unrelated siblings
    can poison the aggregation if one of them happens to be marked
    "completed".

    Low-confidence matches (≤ 0.65) still don't count.
    """
    if user_marked:
        return "completed"

    # Pick top match per provider.
    top_per_provider: dict[str, dict] = {}
    for m in matches:
        if m.get("match_confidence") == "low":
            continue
        prov = m.get("provider", "")
        if not prov:
            continue
        existing = top_per_provider.get(prov)
        if (
            existing is None
            or m.get("match_score", 0) > existing.get("match_score", 0)
        ):
            top_per_provider[prov] = m

    saw_complete = False
    saw_ongoing = False
    for m in top_per_provider.values():
        s = m.get("reported_status") or ""
        if s in ("completed", "cancelled"):
            saw_complete = True
        elif s == "ongoing":
            saw_ongoing = True
    if saw_complete:
        return "completed"
    if saw_ongoing:
        return "ongoing"
    return "unknown"


def process_entry(entry: dict, cache: dict) -> dict:
    folder_title = entry.get("title") or entry.get("folder_name") or ""
    user_marked = bool(entry.get("marked_complete_by_user"))
    queries = query_variants(folder_title)
    cmp_left = normalize_for_compare(folder_title)

    matches: list[dict] = []
    # Track URLs we've already added so a fallback variant doesn't
    # duplicate a hit the primary already found.
    seen_urls: set[str] = set()

    for provider_name, search_fn in providers_for_entry(entry):
        provider_matches: list[dict] = []
        for q_i, query in enumerate(queries):
            results = cached_search(cache, provider_name, query, search_fn)
            time.sleep(_PROVIDER_PAUSE_SEC)

            scored = []
            for r in results:
                site_title = r.get("title", "") or ""
                # Score against the ORIGINAL folder title, not the
                # stripped query — we want to know how close the site
                # title is to what we actually have on disk.
                score = similarity(
                    cmp_left, normalize_for_compare(site_title),
                )
                if score >= _KEEP_FLOOR:
                    scored.append((score, r))
            scored.sort(reverse=True, key=lambda t: t[0])
            scored = scored[:3]

            for score, r in scored:
                if r["url"] in seen_urls:
                    continue
                seen_urls.add(r["url"])
                conf = confidence_label(score)
                entry_match = {
                    "provider": provider_name,
                    "url": r["url"],
                    "title_on_site": r.get("title", ""),
                    "match_score": round(score, 3),
                    "match_confidence": conf,
                    "reported_status": "",
                    "raw_status": None,
                    # Record which query variant produced the hit so
                    # we can see in the report when a fallback helped.
                    "query_used": query,
                }
                if score >= _FETCH_THRESHOLD:
                    norm, raw, site_title = cached_manga_status(cache, r["url"])
                    entry_match["reported_status"] = norm
                    entry_match["raw_status"] = raw
                    if site_title:
                        entry_match["title_on_site"] = site_title
                provider_matches.append(entry_match)

            # Early-exit: if the primary query already produced a
            # high-confidence hit on this provider, don't burn HTTP
            # calls on fallback variants for it.
            if any(m.get("match_confidence") == "high" for m in provider_matches):
                break

        matches.extend(provider_matches)

    entry["matches"] = matches
    entry["effective_status"] = aggregate_status(matches, user_marked)
    return entry


# ---- Markdown report ----------------------------------------------------

def write_markdown(inv: dict, out: Path) -> None:
    entries = inv["entries"]
    total = len(entries)
    completed = sum(1 for e in entries if e.get("effective_status") == "completed")
    ongoing = sum(1 for e in entries if e.get("effective_status") == "ongoing")
    unknown = sum(1 for e in entries if e.get("effective_status") == "unknown")
    matched = sum(1 for e in entries if e.get("matches"))

    lines: list[str] = []
    lines.append("# iCloud Manga Inventory (with cross-site matches)")
    lines.append("")
    lines.append(f"Generated: **{inv.get('generated_at', '?')}**  ")
    lines.append(f"Source: `{inv.get('source_root', '?')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Titles**: {total}")
    lines.append(f"- **At least one match**: {matched}")
    lines.append(f"- **Effective status: completed** — {completed}")
    lines.append(f"- **Effective status: ongoing** — {ongoing}")
    lines.append(f"- **Effective status: unknown** — {unknown}")
    lines.append("")
    lines.append("## Entries")
    lines.append("")
    lines.append("| # | Title | Status | Chapters | Format | Matches |")
    lines.append("|---|-------|--------|----------|--------|---------|")
    for i, e in enumerate(entries, 1):
        title = (e.get("title") or "").replace("|", "\\|")
        status = e.get("effective_status", "unknown")
        marker = " ✓END" if e.get("marked_complete_by_user") else ""
        match_brief = ""
        ms = e.get("matches") or []
        if ms:
            # Top 2 highest-confidence matches by score.
            best = sorted(ms, key=lambda m: -m.get("match_score", 0))[:2]
            match_brief = "<br>".join(
                f"`{m['provider']}` {m.get('reported_status') or '?'} "
                f"({m['match_confidence']} {m.get('match_score', 0):.2f})"
                for m in best
            )
        lines.append(
            f"| {i} | {title} | **{status}**{marker} | "
            f"{e.get('chapter_count', 0)} | `{e.get('format', '?')}` | "
            f"{match_brief} |"
        )
    out.write_text("\n".join(lines), encoding="utf-8")


# ---- Main ---------------------------------------------------------------

def main(argv: list[str]) -> int:
    if not INVENTORY_PATH.exists():
        print(
            f"Inventory not found at {INVENTORY_PATH}.\n"
            "Run scripts/icloud_inventory.py first."
        )
        return 1

    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    cache = load_cache()
    entries = inv["entries"]

    # CLI flags:
    #   --unknowns-only  → only re-probe entries currently tagged
    #                      "unknown". Useful for incremental refinement
    #                      after improving the query normalization.
    #   <N>              → limit to first N entries (debugging).
    unknowns_only = False
    limit = None
    for arg in argv[1:]:
        if arg == "--unknowns-only":
            unknowns_only = True
        else:
            try:
                limit = int(arg)
            except ValueError:
                print(
                    "usage: icloud_match.py [--unknowns-only] [N]"
                )
                return 2

    if unknowns_only:
        targets = [
            e for e in entries
            if (e.get("effective_status") or "unknown") == "unknown"
        ]
        print(f"--unknowns-only: re-probing {len(targets)} entries")
    else:
        targets = entries
    if limit is not None:
        targets = targets[:limit]

    t0 = time.time()
    for i, entry in enumerate(targets, 1):
        title = entry.get("title", entry.get("folder_name", "?"))
        print(f"[{i}/{len(targets)}] {title[:70]}")
        process_entry(entry, cache)
        # Save inventory + cache periodically so progress survives Ctrl-C.
        if i % 5 == 0:
            INVENTORY_PATH.write_text(
                json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8",
            )
            save_cache(cache)

    # Final flush + markdown report.
    INVENTORY_PATH.write_text(
        json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    save_cache(cache)
    write_markdown(inv, PROJECT_ROOT / "icloud_inventory.md")

    elapsed = time.time() - t0
    print(
        f"\n✓ Processed {len(targets)} entries in {elapsed:.1f}s "
        f"({elapsed / max(1, len(targets)):.1f}s avg)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
