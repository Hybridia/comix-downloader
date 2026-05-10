#!/usr/bin/env python3
"""
Local sanity-check for the Mangafire provider.

    python3 scripts/mangafire_test.py
    python3 scripts/mangafire_test.py https://mangafire.to/manga/<slug>.<hid>

Hits the manga page → chapter-list AJAX → first chapter's image-list AJAX
→ pulls the first 2 images. Anything failing prints a clear cause.

The chapter-list AJAX is anti-bot gated (mangafire returns
``status:403, "Request is invalid"`` from suspect IPs); run from the
same network the browser uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers import get_provider_for_url  # noqa: E402
from src.providers.mangafire import MangafireProvider  # noqa: E402
from src.utils.session import get_session  # noqa: E402


DEFAULT_URL = "https://mangafire.to/manga/youkai-izakaya-nonberekee.l3k53"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"target: {url}")

    prov = get_provider_for_url(url)
    if not isinstance(prov, MangafireProvider):
        print(f"  !! router picked {type(prov).__name__}, not MangafireProvider")
        return 2

    code = prov.extract_code(url)
    print(f"\n[1/4] slug={code!r} hid={prov._hid!r}")

    info = prov.get_manga_info(code)
    print(f"[2/4] title:       {info.title!r}")
    print(f"      cover:       {info.poster_url}")
    print(f"      description: {(info.description or '')[:120]}…")

    chapters = prov.get_chapters(code)
    print(f"[3/4] english chapters: {len(chapters)}")
    for ch in chapters[:3]:
        print(f"      ch {ch.number:>5}  id={ch.volume}  title={ch.title!r}")
    if len(chapters) > 3:
        print(f"      … and {len(chapters) - 3} more")
    if not chapters:
        print("  !! No chapters returned. Causes: anti-bot 403 (try from "
              "browser network), or no English release for this title.")
        return 3

    first = chapters[0]
    print(f"\n[4/4] fetching image URLs for chapter {first.number}")
    urls = prov.get_chapter_images(first)
    print(f"      image URLs:  {len(urls)}")
    for u in urls[:3]:
        print(f"        {u}")

    print("\n[+] downloading first 2 images to /tmp/mangafire_test_*.bin")
    sess = get_session()
    referer = f"https://mangafire.to/read/{prov._slug}/en/chapter-{first.number}"
    for i, u in enumerate(urls[:2]):
        r = sess.get(u, headers={"Referer": referer}, timeout=30)
        out = Path(f"/tmp/mangafire_test_{i}.bin")
        out.write_bytes(r.content)
        ct = r.headers.get("Content-Type", "?")
        print(f"    {out}  status={r.status_code}  type={ct}  size={len(r.content)}")

    print("\nOK — listing parses, AJAX works, images reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
