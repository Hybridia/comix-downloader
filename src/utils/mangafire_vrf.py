"""
Mangafire VRF + CF-cookie capture, isolated to a dedicated worker thread.

Mangafire's AJAX endpoints (``/ajax/read/<hid>/chapter/<lang>`` and
``/ajax/read/chapter/<chapter_id>``) require:

1. **Cloudflare cookies** (``cf_clearance`` + ``__cf_bm``) — minted by a
   real browser passing the CF challenge.
2. **A per-path ``vrf=`` query parameter** — computed by heavily
   obfuscated client-side JS.

We get both by running Chromium via Playwright, navigating to the
relevant reader page, and snooping the URL of any outbound request that
contains ``vrf=``.

**Threading model** — Playwright's sync API requires an asyncio event
loop in the calling thread, and shared `Browser`/`Page` objects can't
be touched from multiple threads safely. The download pipeline uses a
``ThreadPoolExecutor``, whose workers have no event loop and would
race on Playwright. We work around that by owning ALL Playwright
operations in a single dedicated worker thread; other threads enqueue
``(callable, args, future)`` items and block on the future. This is
the same effective model AIO uses (their CLI is single-threaded).

Inspired by the approach in ``zzyil/AIO-Webtoon-Downloader`` (read-only
inspection, no code copied).

Playwright is **optional**. Without it the mangafire provider falls
back to its earlier behaviour (cookie-paste). Install with::

    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import concurrent.futures
import os
import queue
import threading
import time
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .logger import get_logger

logger = get_logger(__name__)


_BASE_URL = "https://mangafire.to"
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_VRF_TTL_SECONDS = 300        # vrf tokens visibly rotate; refresh every 5min
_CF_COOKIE_TTL_SECONDS = 1500  # cf_clearance lasts ~30min; refresh at 25
_HEADLESS = os.environ.get("MANGAFIRE_HEADLESS", "1").strip() not in (
    "0", "false", "False", "no", "No",
)


class VRFUnavailable(RuntimeError):
    """Playwright isn't installed, or browser launch failed."""


class MangafireVRFGenerator:
    """
    Single-process VRF token broker. Spawns a dedicated worker thread
    that owns Chromium; all browser operations run there.
    """

    _instance: Optional["MangafireVRFGenerator"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError as e:
            raise VRFUnavailable(
                "playwright is not installed. Run: "
                "`pip install playwright && python -m playwright install chromium`"
            ) from e

        # All state below is owned by the worker thread.
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialized = False
        # path -> (vrf_token, captured_at)
        self._vrf_cache: Dict[str, Tuple[str, float]] = {}
        # Cloudflare bootstrap cache
        self._cf_cookies: list[dict] = []
        self._cf_ua: str = _DEFAULT_UA
        self._cf_captured_at: float = 0.0

        # Queue of (callable, args, kwargs, future) work items.
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._worker = threading.Thread(
            target=self._run_worker,
            daemon=True,
            name="mangafire-playwright",
        )
        self._worker.start()

    # ---- singleton accessor ----------------------------------------

    @classmethod
    def shared(cls) -> "MangafireVRFGenerator":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ---- worker thread loop ----------------------------------------

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, args, kwargs, fut = item
            try:
                result = fn(*args, **kwargs)
                fut.set_result(result)
            except BaseException as e:  # noqa: BLE001
                fut.set_exception(e)
        self._do_close()

    def _submit(self, fn, *args, timeout: float = 120.0, **kwargs):
        """Submit work to the dedicated thread; block until it returns."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((fn, args, kwargs, fut))
        return fut.result(timeout=timeout)

    # ---- worker-thread methods (only called from _run_worker) ------

    def _do_ensure_browser(self) -> None:
        if self._initialized:
            return
        from playwright.sync_api import sync_playwright

        print(f"[vrf-worker] launching chromium (headless={_HEADLESS})", flush=True)
        logger.info(
            "mangafire vrf: launching %s Chromium",
            "headless" if _HEADLESS else "visible",
        )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=_HEADLESS)
        self._context = self._browser.new_context(user_agent=_DEFAULT_UA)

        # Skip images/fonts/media for speed.
        try:
            def _skip_heavy(route, request):
                if request.resource_type in ("image", "media", "font"):
                    return route.abort()
                return route.continue_()

            self._context.route("**/*", _skip_heavy)
        except Exception:
            pass

        self._page = self._context.new_page()
        self._page.on("request", self._do_on_request)
        self._initialized = True

        # Warm up so cf_clearance + __cf_bm get minted.
        try:
            print("[vrf-worker] warm-up navigate mangafire.to/", flush=True)
            self._page.goto(_BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
            self._do_refresh_cf_state()
            print(
                f"[vrf-worker] warm-up done: {len(self._cf_cookies)} cookies",
                flush=True,
            )
        except Exception as e:
            logger.warning(f"mangafire vrf: warm-up navigate failed: {e}")

    def _do_on_request(self, request) -> None:
        try:
            url = request.url
        except Exception:
            return
        if "vrf=" not in url:
            return
        try:
            parsed = urlparse(url)
            vrf = (parse_qs(parsed.query).get("vrf") or [""])[0]
        except Exception:
            return
        if not vrf:
            return
        # Worker thread is single-threaded; no lock needed for cache writes.
        self._vrf_cache[parsed.path] = (vrf, time.time())

    def _do_refresh_cf_state(self) -> None:
        if not self._context or not self._page:
            return
        try:
            cookies = self._context.cookies()
            ua = self._page.evaluate("navigator.userAgent") or _DEFAULT_UA
        except Exception as e:
            logger.debug(f"mangafire vrf: couldn't read cf state: {e}")
            return
        self._cf_cookies = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".mangafire.to"),
                "path": c.get("path", "/"),
            }
            for c in cookies
        ]
        self._cf_ua = ua
        self._cf_captured_at = time.time()

    def _do_close(self) -> None:
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = self._context = self._browser = self._playwright = None
        self._initialized = False

    def _cached_fresh(self, ajax_path: str) -> Optional[str]:
        entry = self._vrf_cache.get(ajax_path)
        if not entry:
            return None
        token, ts = entry
        if time.time() - ts > _VRF_TTL_SECONDS:
            return None
        return token

    def _do_get_cf_state(self, *, force: bool) -> Tuple[list[dict], str]:
        self._do_ensure_browser()
        stale = (
            force
            or not self._cf_cookies
            or (time.time() - self._cf_captured_at) > _CF_COOKIE_TTL_SECONDS
        )
        if stale:
            if not force:
                try:
                    self._page.goto(
                        _BASE_URL + "/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception as e:
                    logger.warning(
                        f"mangafire vrf: cf refresh navigate failed: {e}"
                    )
            self._do_refresh_cf_state()
        return list(self._cf_cookies), self._cf_ua

    def _do_get_vrf(
        self, ajax_path: str, *, navigate_to: str, wait_ms: int
    ) -> str:
        cached = self._cached_fresh(ajax_path)
        if cached:
            return cached
        self._do_ensure_browser()
        page = self._page
        assert page is not None

        def _pred(req):
            try:
                if "vrf=" not in req.url:
                    return False
                return urlparse(req.url).path == ajax_path
            except Exception:
                return False

        print(
            f"[vrf-worker] get_vrf: expect {ajax_path}, nav {navigate_to}",
            flush=True,
        )
        try:
            with page.expect_request(_pred, timeout=wait_ms) as req_info:
                page.goto(navigate_to, wait_until="commit", timeout=30000)
            req = req_info.value
            vrf = (parse_qs(urlparse(req.url).query).get("vrf") or [""])[0]
            if not vrf:
                raise RuntimeError(
                    f"navigated to {navigate_to} but no vrf= captured for {ajax_path}"
                )
            self._vrf_cache[ajax_path] = (vrf, time.time())
            return vrf
        except Exception as e:
            cached = self._cached_fresh(ajax_path)
            if cached:
                return cached
            raise RuntimeError(
                f"mangafire vrf capture failed for {ajax_path}: "
                f"{type(e).__name__}: {e}"
            ) from e

    def _do_capture_ajax_url(
        self, path_regex, *, navigate_to: str, wait_ms: int
    ) -> str:
        self._do_ensure_browser()
        page = self._page
        assert page is not None

        def _pred(req):
            try:
                if "vrf=" not in req.url:
                    return False
                return bool(path_regex.search(urlparse(req.url).path))
            except Exception:
                return False

        print(
            f"[vrf-worker] capture_ajax_url: pattern={path_regex.pattern!r} "
            f"nav={navigate_to}",
            flush=True,
        )
        with page.expect_request(_pred, timeout=wait_ms) as req_info:
            page.goto(navigate_to, wait_until="commit", timeout=30000)
        req = req_info.value
        print(f"[vrf-worker] capture_ajax_url: matched {req.url[:120]}…", flush=True)
        return req.url

    # ---- public API (callable from any thread) ---------------------

    def get_vrf(
        self,
        ajax_path: str,
        *,
        navigate_to: str,
        wait_ms: int = 12000,
    ) -> str:
        return self._submit(
            self._do_get_vrf,
            ajax_path,
            navigate_to=navigate_to,
            wait_ms=wait_ms,
        )

    def capture_ajax_url(
        self,
        path_regex,
        *,
        navigate_to: str,
        wait_ms: int = 30000,
    ) -> str:
        # Bumped default timeout from 15s → 30s. Mangafire's reader
        # page sometimes takes 10-20s for the chapter-image XHR to
        # fire (especially when CF is throttling), so 15s timed out
        # ~30 % of chapters. 30s catches the slow tail without making
        # genuine failures noticeably slower.
        return self._submit(
            self._do_capture_ajax_url,
            path_regex,
            navigate_to=navigate_to,
            wait_ms=wait_ms,
            timeout=wait_ms / 1000.0 + 30.0,
        )

    def get_cf_state(self, *, force: bool = False) -> Tuple[list[dict], str]:
        return self._submit(self._do_get_cf_state, force=force)

    def close(self) -> None:
        # Send sentinel; worker stops cleanly.
        self._queue.put(None)
        with type(self)._instance_lock:
            if type(self)._instance is self:
                type(self)._instance = None


# ---- Module-level convenience wrappers around the singleton --------


def get_vrf(ajax_path: str, *, navigate_to: str) -> str:
    return MangafireVRFGenerator.shared().get_vrf(
        ajax_path, navigate_to=navigate_to
    )


def get_cf_state(*, force: bool = False) -> Tuple[list[dict], str]:
    return MangafireVRFGenerator.shared().get_cf_state(force=force)


def capture_ajax_url(
    path_regex, *, navigate_to: str, wait_ms: int = 30000
) -> str:
    return MangafireVRFGenerator.shared().capture_ajax_url(
        path_regex, navigate_to=navigate_to, wait_ms=wait_ms,
    )
