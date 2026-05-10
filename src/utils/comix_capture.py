"""
Playwright-backed fallback for the comix.to ``/api/v1`` chapter list
and per-chapter image URLs.

Why DOM-scraping instead of XHR snooping
----------------------------------------

The chapter-list AJAX (``/api/v1/manga/{hid}/chapters``) and per-chapter
AJAX (``/api/v1/chapters/{id}``) both return **encrypted** bodies
(``{"e": "<long string>"}``) when the request comes from anything other
than the live SPA. The site's obfuscated JS bundle
(``secure-tes1em-…js`` — VMProtect-style virtualised code) decrypts
them client-side. Reverse-engineering that decryption is infeasible
on a "site changes daily" timeline.

So instead we navigate a real Chromium to the rendered page and read
the **already-decrypted** values from the DOM:

* Chapter list — ``ul.mchap-list li.mchap-item`` rows. Each row carries
  the chapter id + number in its anchor href and the scanlation group
  in a sibling link. We click the numbered pagination buttons
  (``button.npager__num``) to walk every page.
* Chapter pages — every ``<img>`` in the reader's main column whose
  src lives on a comix CDN (currently ``*.wowpic4.store`` and similar
  rotating hosts). Source order matches reading order.

If the site rolls back to a fully reverse-engineerable signing scheme,
:mod:`src.api.comix` already has a fast path through
:mod:`src.utils.hash`; this capture service is the safety net.

Threading model — same as :mod:`mangafire_vrf`. Single owning thread,
synchronous Playwright, queue-of-futures for callers from any other
thread.
"""

from __future__ import annotations

import concurrent.futures
import os
import queue
import re
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .logger import get_logger

logger = get_logger(__name__)


_BASE_URL = "https://comix.to"
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADLESS = os.environ.get("COMIX_HEADLESS", "1").strip() not in (
    "0", "false", "False", "no", "No",
)
# Hard ceiling on chapter-list pagination clicks. The biggest series on
# comix is in the low thousands of chapters at limit=20-per-page; 200
# pages = 4000 chapters and gives us a 10× safety margin without
# letting a stuck pager spin forever.
_MAX_LIST_PAGES = 200

# JS used inside page.evaluate() for both stages — kept as Python
# constants so the indentation stays readable.

_SCRAPE_CHAPTER_ROWS_JS = r"""
() => {
  const rows = document.querySelectorAll('ul.mchap-list li.mchap-item');
  const out = [];
  rows.forEach(li => {
    const a = li.querySelector('a.mchap-row__primary');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/(\d+)-chapter-([0-9.]+)/);
    if (!m) return;
    const g = li.querySelector('a.mchap-row__group');
    out.push({
      id: parseInt(m[1], 10),
      number: m[2],
      text: (a.textContent || '').trim(),
      group_name: g ? (g.textContent || '').trim() : null,
      group_href: g ? g.getAttribute('href') : null,
      is_official: !!(g && /is-official/.test(g.className)),
    });
  });
  return out;
}
"""

_SCRAPE_PAGER_JS = r"""
() => {
  const pager = document.querySelector('.npager, [class*="pager"]');
  if (!pager) return null;
  const numbers = Array.from(pager.querySelectorAll('button.npager__num')).map(b => ({
    n: parseInt((b.textContent || '').trim(), 10),
    active: /is-active/.test(b.className),
  }));
  const hasNext = !!pager.querySelector('button.npager__nav[aria-label="Next page"]');
  const hasLast = !!pager.querySelector('button.npager__nav[aria-label="Last page"]');
  return { numbers, hasNext, hasLast };
}
"""

_SCRAPE_READER_STATE_JS = r"""
() => {
  // The reader is paginated (single-page mode is the only option;
  // there's no long-strip layout in this build). It pre-mounts ~3
  // images around the current page; the rest are placeholder divs
  // showing "<n> / <total>" text.
  //
  // We grab one CDN image URL (any mounted page) and the total page
  // count, then the caller reconstructs every NN.<ext> URL by
  // template — host + path + zero-padded page number.
  const imgs = Array.from(document.querySelectorAll('img'))
    .map(i => i.getAttribute('src') || i.getAttribute('data-src') || '')
    .filter(s => /^https?:\/\/[^/]+\/ii\//.test(s));
  let total = 0;
  document.querySelectorAll('.rpage-page__loader-inner, [class*="page__loader"]').forEach(el => {
    const m = (el.textContent || '').match(/(\d+)\s*\/\s*(\d+)/);
    if (m) total = Math.max(total, parseInt(m[2], 10));
  });
  // Fallback: read the bottom-bar progress label "Ch.X X / Y" if the
  // placeholder loaders didn't render.
  if (total === 0) {
    document.querySelectorAll('[class*="bottombar"], [class*="progress"]').forEach(el => {
      const m = (el.textContent || '').match(/(\d+)\s*\/\s*(\d+)/);
      if (m) total = Math.max(total, parseInt(m[2], 10));
    });
  }
  return { sample_urls: Array.from(new Set(imgs)), total };
}
"""

# Some pages mount nuisance overlays — a "reader gestures" hint
# dialog and ad anchors with target="_blank" — that intercept pointer
# events and prevent clicking the pagination buttons. We remove them
# from the DOM up front rather than try to fight them per-click.
_HIDE_OVERLAYS_JS = r"""
() => {
  const sel = [
    '.rpage-hint',
    '.rpage-hint__backdrop',
    '[role="dialog"][aria-label*="gestures"]',
    'a[href="#"][target="_blank"]',
    '[class*="popup"]',
    '[class*="overlay"]',
  ];
  sel.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
}
"""


class ComixCaptureUnavailable(RuntimeError):
    """Playwright isn't installed, or browser launch failed."""


class ComixCaptureService:
    """Single-process Comix.to chapter + page scraper."""

    _instance: Optional["ComixCaptureService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError as e:
            raise ComixCaptureUnavailable(
                "playwright is not installed. Run: "
                "`pip install playwright && python -m playwright install chromium`"
            ) from e

        # All state below is owned by the worker thread.
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialized = False

        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._worker = threading.Thread(
            target=self._run_worker,
            daemon=True,
            name="comix-playwright",
        )
        self._worker.start()

    # ── singleton accessor ───────────────────────────────────────────

    @classmethod
    def shared(cls) -> "ComixCaptureService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ── worker thread loop ───────────────────────────────────────────

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, args, kwargs, fut = item
            try:
                fut.set_result(fn(*args, **kwargs))
            except BaseException as e:  # noqa: BLE001
                fut.set_exception(e)
        self._do_close()

    def _submit(self, fn, *args, timeout: float = 120.0, **kwargs):
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((fn, args, kwargs, fut))
        return fut.result(timeout=timeout)

    # ── worker-thread methods (only called from _run_worker) ─────────

    def _do_ensure_browser(self) -> None:
        if self._initialized:
            return
        from playwright.sync_api import sync_playwright

        print(f"[comix-worker] launching chromium (headless={_HEADLESS})", flush=True)
        logger.info(
            "comix capture: launching %s Chromium",
            "headless" if _HEADLESS else "visible",
        )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=_HEADLESS)
        self._context = self._browser.new_context(user_agent=_DEFAULT_UA)

        # Skip media/font payloads, but ALLOW images — the reader
        # mounts pages one-by-one and waits for each to load before
        # mounting the next, so blocking image requests stalls the
        # whole pipeline. Reader thumbnails are small (~50-200 KB)
        # so the bandwidth cost is negligible.
        try:
            def _skip_heavy(route, request):
                if request.resource_type in ("media", "font"):
                    return route.abort()
                return route.continue_()

            self._context.route("**/*", _skip_heavy)
        except Exception:
            pass

        self._page = self._context.new_page()
        self._initialized = True

    def _do_close(self) -> None:
        for closer in (
            getattr(self._page, "close", None),
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            try:
                if closer:
                    closer()
            except Exception:
                pass
        self._page = self._context = self._browser = self._playwright = None
        self._initialized = False

    def _do_get_chapter_list(self, hid: str, slug: str) -> list[dict]:
        self._do_ensure_browser()
        page = self._page
        assert page is not None

        nav = f"{_BASE_URL}/title/{hid}-{slug}" if slug else f"{_BASE_URL}/title/{hid}"
        print(f"[comix-worker] get_chapter_list: nav={nav}", flush=True)
        page.goto(nav, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(
            'ul.mchap-list a[href*="-chapter-"]', timeout=30000
        )

        all_rows: list[dict] = []
        seen_ids: set[int] = set()

        for page_no in range(1, _MAX_LIST_PAGES + 1):
            rows = page.evaluate(_SCRAPE_CHAPTER_ROWS_JS) or []
            new_count = 0
            for r in rows:
                if r["id"] in seen_ids:
                    continue
                seen_ids.add(r["id"])
                all_rows.append(r)
                new_count += 1
            print(
                f"[comix-worker]   page {page_no}: scraped {len(rows)} rows "
                f"({new_count} new), total={len(all_rows)}",
                flush=True,
            )

            # Decide whether to advance. Page 1 was free; from here on
            # we click the next numbered button > active. If the
            # "Next page" button is disabled or missing, we're done.
            target = page_no + 1
            try:
                btn = page.locator(
                    f'button.npager__num',
                    has_text=re.compile(rf"^\s*{target}\s*$"),
                ).first
                if btn.count() == 0:
                    # No higher-numbered button visible — try the
                    # generic "Next page" arrow as a fallback.
                    btn = page.locator(
                        'button.npager__nav[aria-label="Next page"]'
                    ).first
                    if btn.count() == 0:
                        print("[comix-worker]   no next button — stopping", flush=True)
                        break
                if btn.is_disabled():
                    print("[comix-worker]   next button disabled — stopping", flush=True)
                    break
            except Exception as e:
                print(f"[comix-worker]   pager probe failed: {e!r}", flush=True)
                break

            # Capture current first-row id and click; wait for DOM
            # change to confirm the new page rendered. ``force=True``
            # bypasses ad-anchor intercepts (comix mounts an
            # ``<a target="_blank">`` overlay over the chapters
            # section that otherwise eats the click).
            prev_first = rows[0]["id"] if rows else None
            try:
                page.evaluate(_HIDE_OVERLAYS_JS)
            except Exception:
                pass
            try:
                btn.click(timeout=5000, force=True)
            except Exception as e:
                print(f"[comix-worker]   click failed: {e!r}", flush=True)
                break
            try:
                page.wait_for_function(
                    """(prev) => {
                        const a = document.querySelector('ul.mchap-list a.mchap-row__primary');
                        if (!a) return false;
                        const m = (a.getAttribute('href') || '').match(/\\/(\\d+)-chapter-/);
                        return m && parseInt(m[1], 10) !== prev;
                    }""",
                    arg=prev_first,
                    timeout=20000,
                )
            except Exception as e:
                print(
                    f"[comix-worker]   DOM didn't update after click: {e!r}; "
                    f"stopping with {len(all_rows)} chapters",
                    flush=True,
                )
                break

        return all_rows

    def _do_get_chapter_pages(self, chapter_url: str) -> list[str]:
        self._do_ensure_browser()
        page = self._page
        assert page is not None

        print(f"[comix-worker] get_chapter_pages: nav={chapter_url[:100]}", flush=True)
        page.goto(chapter_url, wait_until="domcontentloaded", timeout=30000)

        # Wait until at least one reader image has rendered AND the
        # placeholder loaders show a total. The reader pre-mounts ~3
        # pages around the current one; the rest stay as
        # ``rpage-page__loader-inner`` divs displaying ``"<n> / <N>"``,
        # which is where we read the total page count.
        try:
            page.wait_for_function(
                # Wrap the arrow-function literal in IIFE parens so we
                # can call it and read .sample_urls off the result.
                f"() => ({_SCRAPE_READER_STATE_JS})().sample_urls.length > 0",
                timeout=30000,
            )
        except Exception as e:
            raise RuntimeError(
                f"comix: reader page rendered no images within 30s "
                f"({chapter_url})"
            ) from e

        state = page.evaluate(_SCRAPE_READER_STATE_JS) or {}
        sample = list(state.get("sample_urls") or [])
        total = int(state.get("total") or 0)
        print(
            f"[comix-worker]   sample_urls={len(sample)} total_pages={total}",
            flush=True,
        )
        if not sample:
            raise RuntimeError("comix: no sample image URL in reader DOM")

        # The reader renders the smallest page numbers first, so
        # ``sample[0]`` is reliably page 1 (or close to it). When the
        # placeholders never materialised (e.g. very short chapter, or
        # everything mounted), use the count of distinct samples.
        if total <= 0:
            total = len(sample)

        return reconstruct_page_urls(sample, total)

    # ── public API (callable from any thread) ────────────────────────

    def get_chapter_list(
        self, hid: str, slug: str = "", *, timeout: float = 600.0
    ) -> list[dict]:
        return self._submit(
            self._do_get_chapter_list, hid, slug, timeout=timeout,
        )

    def get_chapter_pages(
        self, chapter_url: str, *, timeout: float = 120.0
    ) -> list[str]:
        return self._submit(
            self._do_get_chapter_pages, chapter_url, timeout=timeout,
        )

    def close(self) -> None:
        self._queue.put(None)
        with type(self)._instance_lock:
            if type(self)._instance is self:
                type(self)._instance = None


_PAGE_FILENAME_RE = re.compile(r"^(\d+)(\.[A-Za-z0-9]+)$")


def reconstruct_page_urls(samples: list[str], total: int) -> list[str]:
    """
    Given one or more reader image URLs (e.g. ``…/ii/<key>/01.webp``)
    and the total page count, return the URL for every page in order.

    Padding width is inferred from the observed filename: ``01.webp`` →
    width 2, ``001.jpg`` → width 3. We bump the width up to fit
    ``total`` if the observed sample wasn't wide enough on its own
    (a 47-page chapter mounted with width 2 covers it; a 200-page
    chapter would need width 3 even if page 1 happened to render as
    ``01.webp``).
    """
    if not samples or total <= 0:
        return []
    # Pick the sample with the smallest page number — reader mounts low
    # numbers first, but be defensive.
    best: Optional[tuple[int, int, str, str]] = None  # (page, width, prefix, ext)
    for url in samples:
        idx = url.rfind("/")
        if idx == -1:
            continue
        prefix = url[: idx + 1]
        filename = url[idx + 1 :]
        m = _PAGE_FILENAME_RE.match(filename)
        if not m:
            continue
        digits, ext = m.group(1), m.group(2)
        page_no = int(digits)
        width = len(digits)
        if best is None or page_no < best[0]:
            best = (page_no, width, prefix, ext)
    if best is None:
        # Couldn't parse any sample — fall back to returning samples
        # as-is so the caller still has *something* to download.
        logger.warning(
            "comix: couldn't parse any reader URL pattern; returning %d "
            "raw samples (download may be incomplete)",
            len(samples),
        )
        return list(samples)
    _, width, prefix, ext = best
    width = max(width, len(str(total)))
    return [f"{prefix}{n:0{width}d}{ext}" for n in range(1, total + 1)]


# ── Helpers for callers ──────────────────────────────────────────────

def chapter_id_from_url(url: str) -> Optional[int]:
    """
    Extract the numeric chapter id from a comix reader URL such as
    ``https://comix.to/title/<hid>-<slug>/<chapter_id>-chapter-<n>``.
    """
    try:
        path = urlparse(url).path
    except Exception:
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "title":
        m = re.match(r"(\d+)-", parts[-1])
        if m:
            return int(m.group(1))
    return None


def get_chapter_list(hid: str, slug: str = "") -> list[dict]:
    return ComixCaptureService.shared().get_chapter_list(hid, slug)


def get_chapter_pages(chapter_url: str) -> list[str]:
    return ComixCaptureService.shared().get_chapter_pages(chapter_url)
