#!/usr/bin/env python3
"""
Local sanity-check for the webtoonscan.com provider.

    python3 scripts/webtoonscan_test.py
    python3 scripts/webtoonscan_test.py https://webtoonscan.com/manhwa/<slug>/

Walks every pipeline stage so it's obvious which one fails:

  0. FlareSolverr reachable (the whole site is CF-walled — without
     FlareSolverr nothing works)
  1. URL → slug parsing
  2. Series-page fetch + metadata parse (title / cover / description)
  3. Chapter-list parse (count + first/last)
  4. Earliest chapter's reader page → image URL list
  5. Sample image HEAD with the correct Referer header

If stage 2 or 3 fails with "no chapters parsed", the Madara selectors
in src/providers/webtoonscan.py probably need tweaking — paste the
relevant HTML chunk into the conversation and we'll iterate.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests as std_requests  # noqa: E402

from src.providers import get_provider_for_url  # noqa: E402
from src.providers.webtoonscan import WebtoonscanProvider  # noqa: E402
from src.utils.session import get_session  # noqa: E402


DEFAULT_URL = "https://webtoonscan.com/manhwa/brawling-go/"


def _probe_flaresolverr(url: str) -> bool:
    """Quick HEAD on the FlareSolverr endpoint; print a clear hint."""
    try:
        r = std_requests.get(url.rstrip("/v1") + "/", timeout=3)
        ok = r.status_code in (200, 404)
        print(f"  FlareSolverr at {url}: {'OK' if ok else 'unexpected HTTP ' + str(r.status_code)}")
        return ok
    except Exception as e:
        print(f"  FlareSolverr at {url}: NOT REACHABLE ({type(e).__name__})")
        print("  Start it with:")
        print("    docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")
        return False


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"target: {url}\n")

    print("[0/5] FlareSolverr reachability")
    sess = get_session()
    if not _probe_flaresolverr(sess.flaresolverr_url):
        print("\n  -> FlareSolverr is required for this site. Aborting.")
        return 2

    prov = get_provider_for_url(url)
    if not isinstance(prov, WebtoonscanProvider):
        print(f"\n  !! router picked {type(prov).__name__}, not WebtoonscanProvider")
        return 2
    slug = prov.extract_code(url)
    print(f"\n[1/5] slug: {slug!r}")

    try:
        info = prov.get_manga_info(slug)
    except Exception as e:
        print(f"  !! get_manga_info raised: {type(e).__name__}: {e}")
        return 1
    print(f"\n[2/5] title:       {info.title!r}")
    print(f"      cover:       {info.poster_url}")
    print(f"      latest:      {info.latest_chapter}")
    print(f"      desc[:140]:  {(info.description or '')[:140]}…")

    try:
        chapters = prov.get_chapters(slug)
    except Exception as e:
        print(f"  !! get_chapters raised: {type(e).__name__}: {e}")
        return 1
    print(f"\n[3/5] chapters: {len(chapters)}")
    if not chapters:
        print("  !! empty chapter list — the Madara selectors may need adjusting")
        return 1
    print(f"      first (oldest): #{chapters[0].number}  url={chapters[0].volume}")
    print(f"      last  (newest): #{chapters[-1].number}  url={chapters[-1].volume}")

    try:
        urls = prov.get_chapter_images(chapters[0])
    except Exception as e:
        print(f"  !! get_chapter_images raised: {type(e).__name__}: {e}")
        return 1
    print(f"\n[4/5] chapter {chapters[0].number} pages: {len(urls)}")
    for label, idx in (("first", 0), ("middle", len(urls) // 2), ("last", -1)):
        if -len(urls) <= idx < len(urls):
            print(f"      {label:>6}: {urls[idx]}")

    print(f"\n[5/5] HEAD on first image (Referer={prov.image_referer})")
    try:
        r = get_session().get(urls[0], timeout=30, headers={"Referer": prov.image_referer})
        size = r.headers.get("content-length") or len(r.content[:64])
        print(f"      HTTP {r.status_code}  content-type={r.headers.get('content-type')}  bytes={size}")
    except Exception as e:
        print(f"  !! image fetch raised: {type(e).__name__}: {e}")
        return 1

    print("\nall stages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
