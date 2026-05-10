"""
mangafire.to provider.

API discovery thanks to two open-source scrapers (read-only inspection,
not code-copied — credit:
https://github.com/shafat-96/mangafire and
https://github.com/artur-oliveira/manga-fire-scraper). The endpoints we
use:

- Manga page (HTML)               ``/manga/<slug>.<hid>``
- Chapter list, with chapter ids  ``/ajax/read/<hid>/chapter/<lang>``
                                  → ``{result: {html: '<li><a data-number data-id …>'}}``
- Page list for a chapter         ``/ajax/read/chapter/<chapter_id>``
                                  → ``{result: {images: [[url, …], …]}}``

We hard-filter to English (the user explicitly asked for English-only),
which means we never try the Spanish/Latam/etc. tabs even when they
exist. To switch later, change ``_LANG``.

The chapter-list AJAX is anti-scraper-gated by mangafire (you'll get
``status: 403, "Request is invalid"`` from a hostile IP / no
``cf_clearance``). Run from the user's own machine (the same network the
browser used) and it works.
"""

from __future__ import annotations

import re
import threading
from html import unescape
from typing import Optional
from urllib.parse import urlparse

import requests as _requests

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger
from ..utils.secrets import get_provider_secrets

logger = get_logger(__name__)


_BASE = "https://mangafire.to"
_LANG = "en"  # Per user request: English only.

# URL ↔ id helpers
_MANGA_URL_RE = re.compile(r"/manga/([a-zA-Z0-9-]+\.([a-zA-Z0-9]+))", re.IGNORECASE)
_HID_FROM_SLUG_RE = re.compile(r"\.([a-zA-Z0-9]+)$")

# Page parsers
_TITLE_RE = re.compile(
    r'<h1[^>]*itemprop="name"[^>]*>([^<]+)</h1>', re.IGNORECASE
)
_COVER_RE = re.compile(
    r'<div[^>]+class="poster"[\s\S]+?<img[^>]+src="([^"]+)"', re.IGNORECASE
)
_DESCRIPTION_RE = re.compile(
    r'id="synopsis"[^>]*>([\s\S]+?)</div>', re.IGNORECASE
)
_BODY_HID_RE = re.compile(r'<body[^>]+data-hid="([^"]+)"', re.IGNORECASE)

# Chapter list parser. Be liberal about attribute order — toomics-style
# `data-number` and `data-id` may appear in either order on the <a>, and
# in some responses the `<li>` itself carries `data-id`. We pull each
# attribute independently from the whole li chunk.
_CHAPTER_LI_RE = re.compile(
    r'<li[^>]*class="[^"]*\bitem\b[^"]*"[\s\S]+?</li>', re.IGNORECASE
)
_ATTR_NUMBER_RE = re.compile(r'\bdata-number="([^"]+)"', re.IGNORECASE)
_ATTR_ID_RE = re.compile(r'\bdata-id="([^"]+)"', re.IGNORECASE)
_ATTR_HREF_RE = re.compile(r'\bhref="([^"]+)"', re.IGNORECASE)
_CHAPTER_TITLE_RE = re.compile(
    r"<span[^>]*>([\s\S]+?)</span>", re.IGNORECASE
)


class MangafireProvider(Provider):
    """Provider for https://mangafire.to/ (English chapters only)."""

    name = "mangafire"
    label = "mangafire.to"
    domains = ("mangafire.to",)
    image_referer = "https://mangafire.to/"
    example_url = "https://mangafire.to/manga/<slug>.<hid>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "mangafire.to" in (url or "").lower()

    def __init__(self) -> None:
        # Cache the slug from the most recent extract_code so
        # `get_chapter_images` can re-derive the listing if needed.
        self._slug: Optional[str] = None  # e.g. "youkai-…-nonberekee.l3k53"
        self._hid: Optional[str] = None   # e.g. "l3k53"
        # Manual fallback if Playwright isn't installed: user can paste
        # cf_clearance + session cookie via Settings → MANGAFIRE COOKIE.
        sec = get_provider_secrets(self.name) or {}
        self._fallback_cookie = (sec.get("cookie") or "").strip()
        self._fallback_ua = (sec.get("user_agent") or "").strip()
        # Private session for HTTP calls — we manage cookies + UA
        # ourselves (out of curl_cffi's chrome120 path; we want the
        # same fingerprint as the Chromium that minted cf_clearance).
        self._http = _requests.Session()
        self._http_lock = threading.Lock()
        self._cf_loaded_at: float = 0.0

    # --- URL / id helpers --------------------------------------------

    def extract_code(self, url: str) -> str:
        """Return the manga's full slug ``<name>.<hid>``."""
        m = _MANGA_URL_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find a /manga/<slug> in URL: {url}")
        self._slug = m.group(1)
        self._hid = m.group(2)
        return self._slug

    @staticmethod
    def _hid_from_slug(slug: str) -> str:
        m = _HID_FROM_SLUG_RE.search(slug)
        if not m:
            raise ValueError(f"Slug missing hid suffix: {slug!r}")
        return m.group(1)

    # --- HTTP --------------------------------------------------------

    def _headers(self, *, ajax: bool = False, referer: Optional[str] = None) -> dict:
        # Cookies + UA come from the session jar (set by
        # `_ensure_cf_state`) — don't send them as headers (would
        # double up). Just add request-shape hints here.
        h = {
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer or _BASE + "/",
        }
        if ajax:
            h.update(
                {
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                }
            )
        else:
            h["Accept"] = (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            )
        return h

    def _ensure_cf_state(self) -> None:
        """
        Make sure ``self._http`` carries valid cf_clearance + UA.
        Tries Playwright first (auto); falls back to user-pasted cookie.
        """
        with self._http_lock:
            # Refresh every 25 min (cf_clearance lasts ~30).
            import time as _t

            if (_t.time() - self._cf_loaded_at) < 1500 and self._http.cookies:
                return

            print("[mangafire] _ensure_cf_state: starting", flush=True)
            cookies_loaded = False
            try:
                from ..utils.mangafire_vrf import get_cf_state, VRFUnavailable

                try:
                    print("[mangafire] _ensure_cf_state: calling get_cf_state()", flush=True)
                    cookies, ua = get_cf_state()
                    print(f"[mangafire] _ensure_cf_state: got {len(cookies)} cookies, UA={ua[:40]}…", flush=True)
                    if cookies:
                        self._http.cookies.clear()
                        for c in cookies:
                            try:
                                self._http.cookies.set(
                                    c["name"], c["value"],
                                    domain=c.get("domain", ".mangafire.to"),
                                    path=c.get("path", "/"),
                                )
                            except Exception:
                                pass
                        self._http.headers["User-Agent"] = ua
                        cookies_loaded = True
                        logger.info(
                            f"mangafire: loaded {len(cookies)} CF cookies "
                            f"from headless Chromium"
                        )
                except VRFUnavailable as e:
                    print(f"[mangafire] playwright unavailable: {e}", flush=True)
                    logger.info(f"mangafire: playwright path unavailable ({e})")
            except Exception as e:
                print(f"[mangafire] CF bootstrap exception: {type(e).__name__}: {e}", flush=True)
                logger.warning(f"mangafire: CF bootstrap via playwright failed: {e}")

            if not cookies_loaded and self._fallback_cookie:
                # Manual cookie paste path (Settings → MANGAFIRE COOKIE)
                self._http.cookies.clear()
                for piece in self._fallback_cookie.split(";"):
                    piece = piece.strip()
                    if "=" not in piece:
                        continue
                    name, _, value = piece.partition("=")
                    try:
                        self._http.cookies.set(
                            name.strip(), value.strip(),
                            domain=".mangafire.to", path="/",
                        )
                    except Exception:
                        pass
                if self._fallback_ua:
                    self._http.headers["User-Agent"] = self._fallback_ua
                cookies_loaded = True
                logger.info(
                    "mangafire: loaded CF cookies from manual paste "
                    "(Settings → MANGAFIRE COOKIE)"
                )

            if cookies_loaded:
                self._cf_loaded_at = _t.time()

    @retry_with_backoff()
    def _fetch_html(self, path: str, *, referer: Optional[str] = None) -> str:
        self._ensure_cf_state()
        url = path if path.startswith("http") else _BASE + path
        r = self._http.get(url, headers=self._headers(referer=referer), timeout=30)
        r.raise_for_status()
        return r.text

    def _raw_ajax_get(self, url: str, referer: Optional[str]) -> dict:
        """Single GET, parse JSON, return the result dict (or raise)."""
        self._ensure_cf_state()
        r = self._http.get(
            url, headers=self._headers(ajax=True, referer=referer), timeout=30
        )
        r.raise_for_status()
        try:
            data = r.json()
        except Exception as e:
            raise RuntimeError(
                f"mangafire AJAX {url} returned non-JSON ({len(r.text)} bytes): {e}"
            )
        return data

    def _fetch_ajax(
        self,
        path: str,
        *,
        referer: Optional[str] = None,
        vrf_init_url: Optional[str] = None,
    ) -> dict:
        """
        Hit a mangafire AJAX endpoint with the VRF query token attached.

        VRF is a per-path JS-generated query parameter; we obtain it by
        running headless Chromium (Playwright) once and snooping the
        XHR. Tokens are cached in-memory across requests.

        NO retries on the body-status 403 path: that's anti-bot, not
        transient — retrying earns a Cloudflare 1015 IP rate-limit.
        """
        url = path if path.startswith("http") else _BASE + path
        # Default nav target: the reader URL for chapter-1. AIO uses
        # this even for the chapter-list AJAX because a manga-info
        # page doesn't reliably fire the chapter-list XHR in headless
        # Chromium, but a reader page does (it loads the chapter list
        # on first paint to populate the prev/next nav).
        if vrf_init_url:
            nav_url = vrf_init_url
        elif self._hid:
            nav_url = f"{_BASE}/read/manga.{self._hid}/{_LANG}/chapter-1"
        else:
            nav_url = _BASE + "/"
        print(f"[mangafire] _fetch_ajax: path={path} nav={nav_url}", flush=True)

        # Try with VRF first. The endpoints we care about all require it.
        try:
            from ..utils.mangafire_vrf import get_vrf, VRFUnavailable

            try:
                print(f"[mangafire] _fetch_ajax: requesting vrf for {path}", flush=True)
                token = get_vrf(path, navigate_to=nav_url)
                print(f"[mangafire] _fetch_ajax: got vrf {token[:24]}…", flush=True)
                vrf_url = f"{url}?vrf={token}"
                print(f"[mangafire] _fetch_ajax: GET {vrf_url[:100]}…", flush=True)
                data = self._raw_ajax_get(vrf_url, referer)
                print(f"[mangafire] _fetch_ajax: response status={data.get('status')}", flush=True)
                if data.get("status") == 200:
                    return data.get("result") or {}
                logger.warning(
                    "mangafire AJAX %s with VRF still returned status=%s "
                    "(message=%r). Cached VRF may be stale; falling back "
                    "to bare URL.", path, data.get("status"), data.get("message"),
                )
            except VRFUnavailable as e:
                print(f"[mangafire] _fetch_ajax: VRFUnavailable: {e}", flush=True)
                logger.warning(
                    "mangafire vrf unavailable: %s — trying bare URL "
                    "(will fail unless you've pasted a fresh anti-bot "
                    "cookie in Settings → MANGAFIRE COOKIE).", e,
                )
        except Exception as e:
            print(f"[mangafire] _fetch_ajax: vrf path failed: {type(e).__name__}: {e}", flush=True)
            logger.warning(f"mangafire vrf path failed: {e}")

        # Last-ditch: try without VRF (works only if user pasted cookies
        # that already include a recent cf_clearance + session).
        print(f"[mangafire] _fetch_ajax: bare-URL fallback to {url}", flush=True)
        data = self._raw_ajax_get(url, referer)
        if data.get("status") != 200:
            raise RuntimeError(
                f"mangafire AJAX {path} → status={data.get('status')}, "
                f"message={data.get('message')!r}. The endpoint is "
                "anti-bot gated and we couldn't obtain a VRF token. "
                "Install Playwright (`pip install playwright && python "
                "-m playwright install chromium`) so the provider can "
                "fetch tokens automatically, or paste a fresh cookie in "
                "Settings → MANGAFIRE COOKIE."
            )
        return data.get("result") or {}

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _strip_tags(html: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    def _parse_manga_html(self, html: str) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
        """Return (title, cover, description, hid)."""
        title_m = _TITLE_RE.search(html)
        title = unescape(title_m.group(1).strip()) if title_m else "Unknown"
        cover_m = _COVER_RE.search(html)
        cover = cover_m.group(1) if cover_m else None
        desc_m = _DESCRIPTION_RE.search(html)
        description = (
            self._strip_tags(unescape(desc_m.group(1))) if desc_m else ""
        )
        hid_m = _BODY_HID_RE.search(html)
        hid = hid_m.group(1) if hid_m else None
        return title, cover, description, hid

    def _parse_chapter_list_html(self, html: str) -> list[dict]:
        """
        Return [{number, chapter_id, title, href}, ...] from the AJAX html.

        ``chapter_id`` is only present in the VRF-gated listing endpoint
        (``/ajax/read/<hid>/chapter/<lang>``); the public endpoint
        (``/ajax/manga/<hid>/chapter/<lang>``) omits it. We require
        ``data-number`` + ``href`` since those are enough to download —
        the per-chapter id comes from snooping the reader-page XHR at
        download time.
        """
        out: list[dict] = []
        for li_m in _CHAPTER_LI_RE.finditer(html):
            chunk = li_m.group(0)
            num_m = _ATTR_NUMBER_RE.search(chunk)
            href_m = _ATTR_HREF_RE.search(chunk)
            if not num_m or not href_m:
                continue
            id_m = _ATTR_ID_RE.search(chunk)
            t_m = _CHAPTER_TITLE_RE.search(chunk)
            title = self._strip_tags(unescape(t_m.group(1))) if t_m else ""
            out.append(
                {
                    "number": num_m.group(1),
                    "chapter_id": id_m.group(1) if id_m else "",
                    "title": title,
                    "href": href_m.group(1),
                }
            )
        return out

    # --- Provider interface ------------------------------------------

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        slug = code or self._slug
        if not slug:
            raise RuntimeError("Mangafire: no manga slug — call extract_code first.")
        self._slug = slug
        html = self._fetch_html(f"/manga/{slug}")
        title, cover, description, hid = self._parse_manga_html(html)
        if hid:
            self._hid = hid
        return MangaInfo(
            manga_id=None,  # mangafire's numeric internal id isn't stable
            hash_id=self._hid or self._hid_from_slug(slug),
            title=title,
            slug=slug,
            manga_type="manga",
            poster_url=cover,
            original_language="en",
            description=description or "",
            source=self.name,
            source_url=f"{_BASE}/manga/{slug}",
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        slug = code or self._slug
        if not slug:
            raise RuntimeError("Mangafire: no manga slug — call extract_code first.")
        self._slug = slug
        hid = self._hid or self._hid_from_slug(slug)
        self._hid = hid

        # Use the PUBLIC endpoint (`/ajax/manga/...`) — no VRF, no
        # Playwright launch. We don't need per-chapter ids at this
        # stage; they get captured by snooping the reader page's XHR
        # at download time. Major UX win: chapter list appears
        # instantly instead of after a 5-10s Chromium boot.
        public_path = f"/ajax/manga/{hid}/chapter/{_LANG}"
        public_url = _BASE + public_path
        print(f"[mangafire] get_chapters: GET {public_url} (no VRF)", flush=True)
        result = self._raw_ajax_get(public_url, f"{_BASE}/manga/{slug}")
        if result.get("status") != 200:
            # Fall back to the VRF-gated path only if the public one
            # is blocked for this account/IP.
            print(f"[mangafire] get_chapters: public endpoint returned status="
                  f"{result.get('status')}; falling back to VRF path", flush=True)
            result = self._fetch_ajax(
                f"/ajax/read/{hid}/chapter/{_LANG}",
                referer=f"{_BASE}/manga/{slug}",
            )
        else:
            result = result.get("result") or {}
        html = result if isinstance(result, str) else (
            result.get("html") if isinstance(result, dict) else ""
        )
        if not html:
            raise RuntimeError(
                f"Mangafire returned no chapter HTML for {hid} (lang={_LANG})."
            )
        items = self._parse_chapter_list_html(html)
        if not items:
            # Surface enough context to diagnose: HTML length + first
            # 200 chars + how many bare <li> blocks the listing-shape
            # regex did match (so we can tell "empty AJAX" from "parser
            # missed the markup").
            li_count = len(_CHAPTER_LI_RE.findall(html))
            logger.warning(
                "mangafire: 0 chapters parsed for %s (html_len=%d, "
                "li_blocks=%d). First 200 chars: %r",
                slug, len(html), li_count, html[:200],
            )
            return []

        chapters: list[Chapter] = []
        for it in items:
            try:
                num = it["number"] or "0"
                # Chapter.chapter_id is a numeric field — toon-style ids
                # are alphanumeric, so we stash them in `volume` (the
                # download bridge already preserves volume across the
                # GUI's chapter-dict round-trip) and keep chapter_id at 0.
                ch = Chapter(
                    chapter_id=0,
                    number=str(num),
                    title=it["title"] or None,
                    volume=it["chapter_id"],
                    pages_count=0,
                    image_urls=[],
                )
                chapters.append(ch)
            except Exception as e:
                logger.debug("mangafire: skipping malformed chapter entry: %s", e)
        # Listing is newest-first in the markup; sort ascending by
        # numeric chapter number so downloads/CBZ folders read in order.
        def _sort_key(c: Chapter):
            try:
                return float(c.number)
            except ValueError:
                return 0.0
        chapters.sort(key=_sort_key)
        return chapters

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        chapter_id = (chapter.volume or "").strip()
        print(
            f"[mangafire] get_chapter_images: ENTER ep={chapter.number} "
            f"chapter_id={chapter_id!r} slug={self._slug!r}",
            flush=True,
        )
        reader_url = (
            f"{_BASE}/read/{self._slug}/{_LANG}/chapter-{chapter.number}"
            if self._slug
            else _BASE + "/"
        )

        if not chapter_id:
            # Public chapter list doesn't carry chapter_id. Recover it
            # by snooping the AJAX URL the reader page fires — the path
            # contains the id and the query carries the vrf, in one shot.
            from ..utils.mangafire_vrf import capture_ajax_url, get_cf_state

            print(
                f"[mangafire] get_chapter_images: ep={chapter.number} — "
                f"capturing /ajax/read/chapter/<id>?vrf=… via {reader_url}",
                flush=True,
            )
            full_url = None
            last_err: Optional[Exception] = None
            # Retry on capture failure: mangafire occasionally throttles
            # in bursts and the chapter-image XHR doesn't fire within
            # the timeout. A second navigation usually succeeds.
            import time as _t
            for attempt in (1, 2, 3):
                try:
                    full_url = capture_ajax_url(
                        re.compile(r"^/ajax/read/chapter/(\d+)$"),
                        navigate_to=reader_url,
                    )
                    break
                except Exception as e:
                    last_err = e
                    print(
                        f"[mangafire] capture attempt {attempt}/3 FAILED "
                        f"for ep {chapter.number}: {type(e).__name__}: {e}",
                        flush=True,
                    )
                    if attempt < 3:
                        _t.sleep(2.0 * attempt)  # 2s, then 4s
            if full_url is None:
                raise RuntimeError(
                    f"Mangafire: couldn't capture chapter id + vrf for ep "
                    f"{chapter.number} after 3 attempts. "
                    f"Cause: {type(last_err).__name__}: {last_err}"
                ) from last_err

            # Force-refresh CF cookies from the LIVE Playwright context.
            # The browser just navigated; cookies may have rotated.
            # Pass them per-request (cookies=…) instead of mutating the
            # shared session — avoids a race when multiple chapter
            # workers run concurrently.
            print(
                f"[mangafire] get_chapter_images: refreshing cookies from "
                f"Playwright after capture",
                flush=True,
            )
            cookies, ua = get_cf_state(force=True)
            cookie_jar = {c["name"]: c["value"] for c in cookies}
            print(
                f"[mangafire] get_chapter_images: {len(cookie_jar)} cookies, "
                f"GET {full_url[:120]}…",
                flush=True,
            )
            req_headers = self._headers(ajax=True, referer=reader_url)
            req_headers["User-Agent"] = ua
            r = self._http.get(
                full_url,
                headers=req_headers,
                cookies=cookie_jar,
                timeout=30,
            )
            print(
                f"[mangafire] get_chapter_images: HTTP {r.status_code} "
                f"len={len(r.text)}",
                flush=True,
            )
            r.raise_for_status()
            try:
                data = r.json()
            except Exception as e:
                raise RuntimeError(
                    f"Mangafire ep {chapter.number}: response wasn't JSON "
                    f"({len(r.text)} bytes, head={r.text[:120]!r})"
                ) from e
            if data.get("status") != 200:
                raise RuntimeError(
                    f"Mangafire AJAX failed for ep {chapter.number}: "
                    f"status={data.get('status')}, message={data.get('message')!r}"
                )
            result = data.get("result") or {}
        else:
            result = self._fetch_ajax(
                f"/ajax/read/chapter/{chapter_id}",
                referer=reader_url,
                vrf_init_url=reader_url,
            )
        images = result.get("images") if isinstance(result, dict) else None
        if not isinstance(images, list) or not images:
            raise RuntimeError(
                f"Mangafire chapter {chapter_id} returned no images."
            )
        urls: list[str] = []
        for entry in images:
            # Each entry is [url, ...metadata...]; we only need the URL.
            if isinstance(entry, list) and entry and isinstance(entry[0], str):
                urls.append(entry[0])
            elif isinstance(entry, str):
                urls.append(entry)
        return urls
