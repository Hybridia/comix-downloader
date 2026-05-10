"""
global.toomics.com provider.

Toomics is a paid commercial webtoon platform. Every viewer page only
emits comic image URLs after the request is authenticated as a paying
member; without a session cookie the page renders a sign-in modal
instead. This provider therefore requires the user to drop their own
browser session cookie + matching User-Agent into ``secrets.json``
under the ``toomics`` block. Nothing is bypassed: the server itself
decides what the user can see; we only download what the listing marks
as accessible to that account.

Listing structure:
    ``<li class="normal_ep">`` per episode. The ``<a onclick="…">``
    handler tells us whether the episode is accessible:
      - ``…location.href='/en/webtoon/detail/code/{code}/ep/{n}/toon/{toon}'``
        → server thinks this account can read it (FREE / VIP-included).
      - ``…Base.popupForStat('modal-login', 'login', …)``
        → server gates this episode behind another purchase (Coins).
    We include only the first kind in ``get_chapters``.

Viewer page:
    Image URLs are full ``https://toon-g{N}.toomics.com/toon-g/<blob>``
    pre-signed links with ``?time=…&code=…&tri=…`` query params; we
    pull them out in document order. The signed query string carries
    a TTL (~24h), so we never cache the URLs across runs — every
    download fetches the viewer page fresh.
"""

from __future__ import annotations

import re
import threading
from html import unescape
from typing import Iterable, Optional

import requests as _requests

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.logger import get_logger
from ..utils.secrets import get_provider_secrets

logger = get_logger(__name__)


_TOON_ID_RE = re.compile(r"/toon/(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
# Episode list entries (each <li class="normal_ep …"> wraps one episode;
# `normal_ep own` means the user has opened this one before — same access
# tier as plain `normal_ep`).
_EP_LI_RE = re.compile(
    r'<li class="(normal_ep[^"]*)"[^>]*>([\s\S]+?)</li>', re.IGNORECASE
)
# Episode URL appears in two places depending on access tier:
#   - FREE  ⇒ onclick="…location.href='/en/webtoon/detail/code/…'…"
#   - VIP   ⇒ onclick="…Base.popupForStat('modal-login','login','/en/…',…)…"
# Toomics shows the same modal-login popup to logged-in members for VIP
# episodes (apparently a marketing nudge rather than an access check), so
# we treat both forms as possibly-accessible. The actual access decision
# is made by `cointype` below and re-confirmed by the viewer page.
_EP_DETAIL_PATH_RE = re.compile(
    r"(?:location\.href='|popupForStat\([^)]*?',\s*')"
    r"(/en/webtoon/detail/code/(\d+)/ep/(\d+)/toon/(\d+))",
    re.IGNORECASE,
)
# Coin-badge CSS class — kept for diagnostics only. ``cointype05`` is
# overloaded: toomics uses it for both VIP and Coin tiers, so the class
# alone can't tell us whether a member has access. The visible label
# inside the same span (``"VIP ONLY"`` vs ``"N COINS"``) is the only
# reliable discriminator.
_EP_COINTYPE_RE = re.compile(r'<em class="cointype(\d+)"', re.IGNORECASE)
# Coin-tier label, including translated variants the viewer might emit.
# We grab everything between the ``<em class="cointypeNN">…</em>`` icon
# and the closing ``</span>``, normalised to uppercase + collapsed
# whitespace.
_EP_LABEL_RE = re.compile(
    r'<em class="cointype\d+"[^>]*>[^<]*</em>([\s\S]*?)</span>',
    re.IGNORECASE,
)
# Labels we treat as accessible to a paid VIP / standard member.
# - "FREE"          — anyone (cointype01)
# - "VIP ONLY"      — included in a VIP membership (cointype05 + this label)
# Anything containing "COIN" is per-episode purchase content; we never
# attempt those even if a member has VIP, because they're sold
# separately from the membership.
_ACCESSIBLE_LABELS = frozenset({"FREE", "VIP ONLY", "VIP"})
_EP_TITLE_RE = re.compile(
    r'class="cell-title"[\s\S]+?<strong[^>]*>([\s\S]+?)</strong>',
    re.IGNORECASE,
)
_EP_THUMB_RE = re.compile(
    r'data-original="(https?://[^"]+)"', re.IGNORECASE
)
_EP_DATE_RE = re.compile(
    r"<time[^>]*datetime=\"([^\"]+)\"", re.IGNORECASE
)
# Comic CDN. Hosts seen so far: toon-g1, toon-g2 — pattern is "toon-g\d+".
_VIEWER_IMG_RE = re.compile(
    r"https?://toon-g\d+\.toomics\.com/toon-[^\s\"'<>]+",
    re.IGNORECASE,
)
# Hidden inputs we use to confirm we got a real viewer page (not a login wall).
_VIEWER_TOON_IDX_RE = re.compile(
    r'<input[^>]+id="toon_idx"[^>]+value="(\d+)"', re.IGNORECASE
)


class ToomicsAuthError(RuntimeError):
    """Auth misconfigured or session expired."""


class ToomicsProvider(Provider):
    """Provider for https://global.toomics.com/ (paid membership required)."""

    name = "toomics"
    label = "global.toomics.com"
    domains = ("global.toomics.com",)
    image_referer = "https://global.toomics.com/"
    # `extract_code` requires `/toon/<id>` in the URL — the viewer link
    # the user copies from clicking any episode in the listing.
    example_url = "https://global.toomics.com/en/webtoon/episode/toon/<id>"

    @classmethod
    def matches(cls, url: str) -> bool:
        return "global.toomics.com" in (url or "").lower()

    def __init__(self) -> None:
        self._secrets = get_provider_secrets(self.name) or {}
        self._user_agent = (self._secrets.get("user_agent") or "").strip()
        # Cached toon id from the most recent extract_code / get_* call so
        # `get_chapter_images` can reconstruct the episode URL without
        # roundtripping the toon id through the GUI's lossy chapter dicts.
        self._toon_id: Optional[str] = None
        # Toomics binds the session to the exact User-Agent string that
        # was active when the cookie was minted. Going through the global
        # SessionManager risks a curl_cffi Chrome-120 impersonation
        # silently overriding our header (or sending a TLS / sec-ch-ua
        # fingerprint that doesn't match the bound UA), which makes the
        # server treat the session as logged-out. We use a private plain
        # requests.Session here so the headers we set are exactly what
        # goes on the wire.
        self._http = _requests.Session()
        # Load the saved cookie string into the session jar so subsequent
        # requests reuse it automatically AND any Set-Cookie response
        # from toomics rotates the cached value (toomics rotates the
        # session id on activity; we have to follow or we get logged out
        # mid-download). Don't pass `Cookie:` as a header anymore — the
        # jar will compose it from current state on every request.
        self._cookie_lock = threading.Lock()
        self._auto_relogin_in_flight = False
        self._set_cookies_from_string(self._secrets.get("cookie") or "")
        if not self._has_session_cookie():
            logger.warning(
                "Toomics provider initialised without a session cookie. "
                "Either Login from Settings (email + password) or paste "
                "the cookie manually."
            )

    # --- Cookie jar plumbing ----------------------------------------

    @staticmethod
    def _parse_cookie_string(s: str) -> dict:
        out: dict[str, str] = {}
        for piece in (s or "").split(";"):
            piece = piece.strip()
            if not piece or "=" not in piece:
                continue
            name, _, value = piece.partition("=")
            out[name.strip()] = value.strip()
        return out

    def _set_cookies_from_string(self, s: str) -> None:
        """Replace the session jar's contents with the given cookie string."""
        with self._cookie_lock:
            self._http.cookies.clear()
            for name, value in self._parse_cookie_string(s).items():
                # Bind to the global.toomics.com domain so the jar attaches
                # them to every request we make.
                self._http.cookies.set(
                    name, value, domain=".toomics.com", path="/"
                )

    def _current_cookie_string(self) -> str:
        with self._cookie_lock:
            return "; ".join(
                f"{c.name}={c.value}" for c in self._http.cookies
            )

    def _has_session_cookie(self) -> bool:
        with self._cookie_lock:
            return any(
                c.name == "GTOOMICScisession" for c in self._http.cookies
            )

    def _persist_cookies(self) -> None:
        """
        Save the session jar back to secrets.json so a restart picks up
        whatever the server has rotated since login. We never overwrite
        anything except the `cookie` field of the toomics block.
        """
        s = self._current_cookie_string()
        if not s:
            return
        try:
            from ..utils.secrets import save_provider_secrets

            save_provider_secrets("toomics", {"cookie": s})
        except Exception as e:
            # Persistence is best-effort; don't crash the download if the
            # filesystem is read-only or similar.
            logger.debug(f"toomics: skipping cookie persist ({e})")

    # --- HTTP --------------------------------------------------------

    def _request_headers(self, referer: Optional[str] = None) -> dict:
        h = {
            "Referer": referer or "https://global.toomics.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._user_agent:
            h["User-Agent"] = self._user_agent
        return h

    @retry_with_backoff()
    def _fetch(self, url: str, referer: Optional[str] = None) -> str:
        if not self._has_session_cookie():
            raise ToomicsAuthError(
                "No GTOOMICScisession cookie present. Open Settings → "
                "TOOMICS LOGIN and either click Login (email + password) "
                "or paste a fresh cookie."
            )
        logger.debug(f"toomics: GET {url}")
        r = self._http.get(
            url, headers=self._request_headers(referer), timeout=30
        )
        r.raise_for_status()
        return r.text

    # --- Auto-relogin ------------------------------------------------

    def _try_auto_relogin(self) -> bool:
        """
        If the user stored email + password, log in again to refresh
        the session cookie. Returns True on success. Reentrancy-guarded
        so concurrent failing chapters don't stampede the login form.
        """
        with self._cookie_lock:
            if self._auto_relogin_in_flight:
                return self._has_session_cookie()
            self._auto_relogin_in_flight = True
        try:
            email = (self._secrets.get("email") or "").strip()
            password = self._secrets.get("password") or ""
            if not email or not password:
                return False
            from ..utils.toomics_login import login as toomics_login

            logger.info("toomics: session expired — auto-relogin via stored credentials")
            result = toomics_login(
                email=email,
                password=password,
                user_agent=self._user_agent or None,
                # Hand the live jar's cookies to the login flow so it
                # merges instead of replacing — preserves USERTYPE etc.
                existing_cookies=self._current_cookie_string() or None,
            )
            self._set_cookies_from_string(result.cookie)
            self._user_agent = result.user_agent
            try:
                from ..utils.secrets import save_provider_secrets

                save_provider_secrets(
                    "toomics",
                    {"cookie": result.cookie, "user_agent": result.user_agent},
                )
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"toomics: auto-relogin failed: {e}")
            return False
        finally:
            with self._cookie_lock:
                self._auto_relogin_in_flight = False

    # --- URL helpers -------------------------------------------------

    def extract_code(self, url: str) -> str:
        m = _TOON_ID_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find toon id in URL: {url}")
        self._toon_id = m.group(1)
        return self._toon_id

    @staticmethod
    def _listing_url(code: str, *, adult_confirmed: bool = False) -> str:
        # ``/search/Y`` is toomics' "I confirm I'm 18+" flag in the URL.
        # Non-adult toons render fine without it; adult-flagged toons
        # come back as an empty listing unless the session already has
        # the adult-confirm state OR we pass /search/Y. Fresh sessions
        # minted by /auth/layer_login don't carry that state, so we try
        # the plain URL first and fall back to /search/Y on empty.
        suffix = "/search/Y" if adult_confirmed else ""
        return (
            f"https://global.toomics.com/en/webtoon/episode/toon/{code}{suffix}"
        )

    @staticmethod
    def _episode_url(code: int | str, ep: int | str, toon: int | str) -> str:
        return (
            f"https://global.toomics.com/en/webtoon/detail/code/{code}/"
            f"ep/{ep}/toon/{toon}"
        )

    # --- Parsing -----------------------------------------------------

    @staticmethod
    def _parse_title(html: str) -> str:
        m = _TITLE_RE.search(html)
        if not m:
            return "Toomics title"
        title = unescape(m.group(1)).strip()
        # "<title>My Stepmom - Toomics</title>" → "My Stepmom"
        title = re.sub(r"\s*[-–|]\s*Toomics\s*$", "", title, flags=re.IGNORECASE)
        return title or "Toomics title"

    def _iter_accessible_episodes(self, html: str) -> Iterable[dict]:
        """
        Yield ``{code, ep, toon, title, thumb, date, cointype, label}``
        dicts for every episode whose visible tier label is in
        ``_ACCESSIBLE_LABELS`` (FREE / VIP). Coin-tier entries (per-
        episode purchase) are skipped — we don't attempt them even
        when a VIP member is logged in, because they're sold separately
        from the membership and the viewer page would just bounce.
        """
        skipped: dict[str, int] = {}
        for li_m in _EP_LI_RE.finditer(html):
            cls, chunk = li_m.group(1), li_m.group(2)
            detail = _EP_DETAIL_PATH_RE.search(chunk)
            if not detail:
                continue
            ct_m = _EP_COINTYPE_RE.search(chunk)
            cointype = ct_m.group(1) if ct_m else "?"
            lbl_m = _EP_LABEL_RE.search(chunk)
            label = (
                re.sub(r"\s+", " ", unescape(lbl_m.group(1))).strip().upper()
                if lbl_m else ""
            )
            if label not in _ACCESSIBLE_LABELS:
                skipped[label or "?"] = skipped.get(label or "?", 0) + 1
                continue
            _, code, ep, toon = detail.groups()
            t = _EP_TITLE_RE.search(chunk)
            title = (
                re.sub(r"\s+", " ", unescape(t.group(1))).strip() if t else ""
            )
            thumb_m = _EP_THUMB_RE.search(chunk)
            thumb = thumb_m.group(1) if thumb_m else None
            date_m = _EP_DATE_RE.search(chunk)
            date = date_m.group(1) if date_m else None
            yield {
                "code": int(code),
                "ep": int(ep),
                "toon": int(toon),
                "title": title,
                "thumb": thumb,
                "date": date,
                "cointype": cointype,
                "label": label,
            }
        if skipped:
            summary = ", ".join(
                f"{n}× {lbl!r}" for lbl, n in sorted(skipped.items())
            )
            logger.info(
                "toomics: skipped %s — outside the FREE/VIP label "
                "allowlist (Coin-tier or unknown). Extend "
                "_ACCESSIBLE_LABELS if you actually have access.",
                summary,
            )

    @staticmethod
    def _extract_image_urls(viewer_html: str) -> list[str]:
        """
        Pull the comic image URLs out of an episode viewer page in
        document order, deduped. Order matches page order — toomics
        emits them sequentially in the markup.
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for m in _VIEWER_IMG_RE.finditer(viewer_html):
            url = m.group(0).strip().rstrip("'\"")
            # Skip thumb-* hosts (different CDN) and assets, just in case
            # the regex slipped.
            if "/toon-g/" not in url and "/toon-h/" not in url:
                # Permit any toon-* path under the comic CDN; reject other
                # toon-host static assets if we ever encounter them.
                if not re.search(r"/toon-[a-z0-9]+/", url, re.IGNORECASE):
                    continue
            if url in seen:
                continue
            seen.add(url)
            ordered.append(url)
        return ordered

    # --- Auth check -------------------------------------------------

    def _assert_authenticated_viewer(self, html: str, episode_url: str) -> None:
        """
        Validate that a viewer-page response actually contains comic
        content. If toomics returns the listing-style stub (~165 bytes)
        or omits the toon_idx hidden field, the session is either
        expired, wrong IP, or wrong UA.
        """
        if not _VIEWER_TOON_IDX_RE.search(html):
            raise ToomicsAuthError(
                "Toomics returned a viewer page without comic data for "
                f"{episode_url}. Likely causes: session expired, IP "
                "changed, or User-Agent mismatch. Re-paste cookies + UA "
                "into secrets.json. (See CLAUDE.md → toomics setup.)"
            )

    # --- Provider interface ------------------------------------------

    def _fetch_listing(self, code: str) -> str:
        """
        Fetch the listing page, retrying with /search/Y on an empty
        result so adult-flagged toons that haven't had their age gate
        accepted in this session render too.
        """
        html = self._fetch(self._listing_url(code))
        if not any(True for _ in self._iter_accessible_episodes(html)):
            logger.info(
                "toomics: empty listing for toon %s — retrying with "
                "/search/Y (adult-content confirm).", code,
            )
            html = self._fetch(self._listing_url(code, adult_confirmed=True))
        return html

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        self._toon_id = str(code)
        html = self._fetch_listing(code)
        title = self._parse_title(html)
        # Prefer the first accessible episode's thumbnail as the cover.
        cover = None
        for ep in self._iter_accessible_episodes(html):
            if ep["thumb"]:
                cover = ep["thumb"]
                break
        return MangaInfo(
            manga_id=int(code) if str(code).isdigit() else None,
            hash_id=str(code),
            title=title,
            slug=str(code),
            manga_type="webtoon",
            poster_url=cover,
            original_language="en",
            status="",
            is_nsfw=True,
            description=(
                f"Toomics webtoon #{code}. Only episodes your account has "
                "access to (FREE + membership-included) will be listed; "
                "Coins-only episodes are skipped."
            ),
            source=self.name,
            source_url=self._listing_url(code),
        )

    def get_chapters(self, code: str) -> list[Chapter]:
        self._toon_id = str(code)
        html = self._fetch_listing(code)
        chapters: list[Chapter] = []
        for ep in self._iter_accessible_episodes(html):
            chapters.append(
                Chapter(
                    chapter_id=ep["code"],
                    number=str(ep["ep"]),
                    title=ep["title"] or None,
                    volume=str(ep["toon"]),  # carries toon id for re-fetch
                    pages_count=0,  # known only after viewer fetch
                    image_urls=[],   # signed URLs expire — fetch on demand
                )
            )
        chapters.sort(key=lambda c: int(c.number) if c.number.isdigit() else 0)
        if not chapters:
            logger.warning(
                "toomics: no accessible episodes found for toon %s. Either "
                "this series is fully Coin-locked for your account, or the "
                "session cookie is invalid.",
                code,
            )
        return chapters

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        # Always re-fetch — signed URLs carry a TTL.
        toon_id = chapter.volume or self._toon_id
        if not toon_id:
            raise RuntimeError(
                "Toomics chapter is missing the toon id; call "
                "get_chapters or extract_code first so the provider knows "
                "which series this chapter belongs to."
            )
        episode_url = self._episode_url(chapter.chapter_id, chapter.number, toon_id)
        try:
            html = self._fetch(episode_url, referer=self._listing_url(toon_id))
            self._assert_authenticated_viewer(html, episode_url)
        except ToomicsAuthError:
            # Toomics rotates the session_id on activity; if a parallel
            # download happened to grab a refreshed cookie that
            # invalidated this thread's view of the session, OR if our
            # session simply expired, try one auto-relogin and retry the
            # viewer fetch before surfacing the failure.
            if not self._try_auto_relogin():
                raise
            html = self._fetch(episode_url, referer=self._listing_url(toon_id))
            self._assert_authenticated_viewer(html, episode_url)
        # Persist the (possibly rotated) cookie jar so the next run /
        # the next chapter starts with the latest server-issued state.
        self._persist_cookies()
        urls = self._extract_image_urls(html)
        if not urls:
            raise RuntimeError(
                f"toomics: viewer page for ep {chapter.number} loaded but "
                "no comic image URLs were found. Markup may have changed."
            )
        return urls

    def chapter_request_headers(self) -> dict:
        # Image fetches need the same auth / UA as the viewer fetch, since
        # toomics' CDN inspects them. Compose Cookie from the live jar so
        # we send whatever toomics has rotated to most recently, not a
        # snapshot from secrets.json.
        h = self._request_headers()
        cookie = self._current_cookie_string()
        if cookie:
            h["Cookie"] = cookie
        return h
