#!/usr/bin/env python3
"""
Local sanity-check for the Comix.to provider.

    python3 scripts/comix_test.py
    python3 scripts/comix_test.py https://comix.to/title/<hid>-<slug>

Walks the full pipeline so it's obvious which stage is broken when the
site shifts under us:

  1. URL → hid + slug parsing
  2. Manga info via /api/v1/manga/<hid>           (no token required)
  3. Chapter list — fast path (HaruNeko-style hash) AND the Playwright
     fallback both attempted; whichever produces a valid token wins
  4. Per-chapter pages for the earliest chapter — same fast/slow probe
  5. Single image fetch (HEAD) to confirm referer/host headers work

Comix.to is intentionally hostile to scrapers and changes its signing
algorithm frequently. When the fast path stops working the script will
say so explicitly and you can submit the new algo update upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.comix import ComixAPI  # noqa: E402
from src.providers import get_provider_for_url  # noqa: E402
from src.providers.comix import ComixProvider  # noqa: E402
from src.utils.hash import generate_comix_hash  # noqa: E402
from src.utils.session import get_session  # noqa: E402


DEFAULT_URL = "https://comix.to/title/kl2x6-that-time-i-got-reincarnated-as-a-slime"


def _probe_fast_path(path: str) -> tuple[bool, str]:
    """Send one signed call; return (accepted, snippet)."""
    token = generate_comix_hash(path)
    url = f"{ComixAPI.BASE_URL}{path}"
    try:
        r = get_session().get(url, timeout=20, params={"_": token})
        body = r.json()
    except Exception as e:
        return False, f"transport error: {e!r}"
    msg = body.get("message", "")
    if isinstance(body, dict) and body.get("status") == "error" and "token" in str(msg).lower():
        return False, f"server: {body.get('code')} {msg!r}"
    return True, f"server: status={body.get('status')!r}"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"target: {url}\n")

    prov = get_provider_for_url(url)
    if not isinstance(prov, ComixProvider):
        print(f"  !! router picked {type(prov).__name__}, not ComixProvider")
        return 2

    code = prov.extract_code(url)
    cached_slug = prov._slug_cache.get(code, "")
    print(f"[1/5] hid={code!r} slug={cached_slug!r}")

    info = prov.get_manga_info(code)
    if not info:
        print("  !! get_manga_info returned None — /api/v1/manga endpoint is broken")
        return 1
    print(f"[2/5] title:       {info.title!r}")
    print(f"      slug:        {info.slug!r}")
    print(f"      type:        {info.manga_type!r}  status={info.status!r}")
    print(f"      latest:      {info.latest_chapter}  poster={info.poster_url}")

    print("\n[3/5] chapter list")
    accepted, snippet = _probe_fast_path(f"/manga/{code}/chapters")
    print(f"      fast path: {'OK' if accepted else 'REJECTED'} ({snippet})")
    try:
        chapters = prov.get_chapters(code)
    except Exception as e:
        print(f"  !! get_chapters raised: {type(e).__name__}: {e}")
        return 1
    print(f"      total chapters: {len(chapters)}")
    if not chapters:
        print("  !! Playwright fallback also failed — see comix-worker logs above")
        return 1
    first = chapters[0]
    print(f"      earliest: number={first.number} id={first.chapter_id} title={first.title!r}")
    print(f"                reader_url={first.volume}")

    print("\n[4/5] page list (earliest chapter)")
    accepted, snippet = _probe_fast_path(f"/chapters/{first.chapter_id}")
    print(f"      fast path: {'OK' if accepted else 'REJECTED'} ({snippet})")
    try:
        urls = prov.get_chapter_images(first)
    except Exception as e:
        print(f"  !! get_chapter_images raised: {type(e).__name__}: {e}")
        return 1
    print(f"      pages: {len(urls)}")
    for label, idx in (("first", 0), ("middle", len(urls) // 2), ("last", -1)):
        if -len(urls) <= idx < len(urls):
            print(f"      {label:>6}: {urls[idx]}")

    print("\n[5/5] sample image fetch (HEAD on first page)")
    if not urls:
        print("  !! no URLs to probe")
        return 1
    try:
        r = get_session().get(
            urls[0],
            timeout=20,
            headers={"Referer": prov.image_referer},
            stream=True,
        )
        size = r.headers.get("content-length") or len(r.content[:64])
        print(f"      HTTP {r.status_code}  content-type={r.headers.get('content-type')}  bytes={size}")
    except Exception as e:
        print(f"  !! image fetch raised: {type(e).__name__}: {e}")
        return 1

    print("\nall stages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
