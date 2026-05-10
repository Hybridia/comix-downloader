#!/usr/bin/env python3
"""
Local sanity-check for the Toomics provider.

Run this from the project root with a toon URL (or just an id):

    python3 scripts/toomics_test.py
    python3 scripts/toomics_test.py 4698
    python3 scripts/toomics_test.py https://global.toomics.com/en/webtoon/episode/toon/8655

It loads your secrets.json, hits the listing page, parses chapters,
fetches the first accessible episode's image URLs, and (optionally)
downloads the first 2 images to /tmp to confirm the auth headers reach
the comic CDN. Nothing is committed anywhere.

Anything that fails prints a clear reason. Paste the full output back to
the assistant if you need help diagnosing.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as ``python3 scripts/toomics_test.py`` from project root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers import get_provider_for_url  # noqa: E402
from src.providers.toomics import ToomicsProvider, ToomicsAuthError  # noqa: E402
from src.utils.secrets import load_secrets, secrets_path  # noqa: E402
from src.utils.session import get_session  # noqa: E402


DEFAULT_URL = "https://global.toomics.com/en/webtoon/episode/toon/4698"


def _resolve_url(arg: str | None) -> str:
    if not arg:
        return DEFAULT_URL
    if arg.isdigit():
        return f"https://global.toomics.com/en/webtoon/episode/toon/{arg}"
    return arg


def main() -> int:
    url = _resolve_url(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"target: {url}")
    print(f"secrets: {secrets_path()} (exists={secrets_path().exists()})")

    sec = (load_secrets() or {}).get("toomics") or {}
    if not sec.get("cookie"):
        print(
            "  !! no `toomics.cookie` in secrets.json — re-paste cookies "
            "and try again."
        )
        return 2
    print(f"  cookie len: {len(sec['cookie'])}")
    print(f"  user_agent: {sec.get('user_agent', '<unset>')[:90]}")

    prov = get_provider_for_url(url)
    if not isinstance(prov, ToomicsProvider):
        print(f"  !! router picked {type(prov).__name__}, not ToomicsProvider")
        return 3

    code = prov.extract_code(url)
    print(f"\n[1/4] toon id: {code}")

    try:
        info = prov.get_manga_info(code)
    except ToomicsAuthError as e:
        print(f"  !! auth error: {e}")
        return 4
    print(f"[2/4] title:   {info.title!r}")
    print(f"      cover:   {info.poster_url}")

    # Raw listing dump — used to diagnose missing VIP / membership
    # episodes when the parser is too strict.
    listing_html = prov._fetch(prov._listing_url(code))
    import re as _re
    li_blocks = _re.findall(r"<li class=\"([^\"]+)\"[^>]*>([\s\S]+?)</li>", listing_html)
    print(f"\n[debug] total <li> elements: {len(li_blocks)}")
    from collections import Counter as _Counter
    cls_dist = _Counter(c for c, _ in li_blocks)
    print(f"[debug] <li class> distribution: {cls_dist.most_common(10)}")
    # Group entries that contain a /detail/code/N/ep/N/toon/N reference
    detail_re = _re.compile(r"/en/webtoon/detail/code/\d+/ep/\d+/toon/\d+")
    detail_lis = [(c, b) for c, b in li_blocks if detail_re.search(b)]
    print(f"[debug] <li> with episode link: {len(detail_lis)}")
    # Bucket by what handler they use AND by the cell-coin badge class
    # (cointypeNN), so we can tell VIP-accessible entries apart from Coin-
    # locked ones when both use the modal-login popup handler.
    cointype_re = _re.compile(r'cointype(\d+)', _re.IGNORECASE)
    label_re = _re.compile(
        r'<em class="cointype\d+">[^<]*</em>([^<]+?)</span>', _re.IGNORECASE
    )
    buckets: _Counter = _Counter()
    for cls, body in detail_lis:
        if "location.href=" in body and "popupForStat" not in body:
            handler = "direct"
        elif "popupForStat" in body and "modal-login" in body:
            handler = "modal-login"
        elif "popupForStat" in body:
            m = _re.search(r"popupForStat\('([^']+)'", body)
            handler = f"popup-{m.group(1) if m else '?'}"
        else:
            handler = "other"
        ct = cointype_re.search(body)
        ct_str = ct.group(0) if ct else "no-cointype"
        lb = label_re.search(body)
        label = (
            _re.sub(r"\s+", " ", lb.group(1)).strip().upper()
            if lb else "?"
        )
        buckets[(cls, handler, ct_str, label)] += 1
    print("[debug] (class, handler, cointype, label) → count:")
    for k, n in buckets.most_common():
        print(f"        {n:4d}  {k}")
    # Print one compact sample for each (class,kind) bucket
    seen = set()
    for cls, body in detail_lis:
        if "location.href=" in body and "popupForStat" not in body:
            key = (cls, "direct")
        elif "popupForStat" in body and "modal-login" in body:
            key = (cls, "modal-login")
        elif "popupForStat" in body:
            m = _re.search(r"popupForStat\('([^']+)'", body)
            key = (cls, f"popup-{m.group(1) if m else '?'}")
        else:
            key = (cls, "other")
        if key in seen:
            continue
        seen.add(key)
        compact = _re.sub(r"\s+", " ", body)[:600]
        print(f"\n[debug] sample {key}:\n  {compact}")

    chapters = prov.get_chapters(code)
    print(f"\n[3/4] accessible chapters (FREE + membership): {len(chapters)}")
    for ch in chapters[:5]:
        print(f"      ep {ch.number:>3}  code={ch.chapter_id}  title={ch.title!r}")
    if len(chapters) > 5:
        print(f"      … and {len(chapters) - 5} more")
    if not chapters:
        print(
            "  !! No accessible chapters. Either this series is fully "
            "Coins-locked for your account, or the session cookie is "
            "invalid (try re-pasting from devtools)."
        )
        return 5

    first = chapters[0]
    print(f"\n[4/4] fetching image URLs for ep {first.number} (code={first.chapter_id})")
    try:
        urls = prov.get_chapter_images(first)
    except ToomicsAuthError as e:
        print(f"  !! auth error: {e}")
        return 6
    print(f"      image URLs found: {len(urls)}")
    for u in urls[:3]:
        print(f"        {u}")

    # Optional: pull the first 2 images so we know the auth headers reach
    # the comic CDN. Saved to /tmp so they don't pollute the project tree.
    print("\n[+] downloading first 2 images to /tmp/toomics_test_*.bin")
    sess = get_session()
    headers = prov.chapter_request_headers()
    for i, u in enumerate(urls[:2]):
        r = sess.get(u, headers=headers, timeout=30)
        out = Path(f"/tmp/toomics_test_{i}.bin")
        out.write_bytes(r.content)
        ct = r.headers.get("Content-Type", "?")
        print(f"    {out}  status={r.status_code}  type={ct}  size={len(r.content)}")

    print("\nOK — listing parses, auth works, images reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
