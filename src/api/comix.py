"""
Comix.to API wrapper (``/api/v1`` revision, May 2026).

The site moved from a snake-case ``/api/v2`` API to a camel-case
``/api/v1`` SPA backend. The chapter list and per-chapter pages now
return **encrypted** JSON bodies (``{"e": "<long string>"}``) signed
with a path-bound ``_=`` token; both the signing key set and the
response cipher live in an obfuscated VMProtect-style JS bundle.

Two-tier strategy
-----------------

1. **Fast path** — sign the request with the algorithm in
   :mod:`src.utils.hash` (a port of HaruNeko's ``ComixTo`` connector).
   When the server accepts AND returns a non-encrypted body, parse it
   directly. As of 2026-05-10 the live site returns encrypted bodies
   even with a valid token, so this path is currently dormant — but
   we leave it in place for the day comix walks back the cipher (or
   HaruNeko ships a decryption port).

2. **Slow path** — :mod:`src.utils.comix_capture`. A real Chromium
   loads the page, the SPA decrypts everything client-side, and we
   scrape chapter rows and reader images out of the rendered DOM.

The fallback is transparent to callers — every public method keeps the
same signature and return type as before.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from ..core.models import Chapter, MangaInfo
from ..utils.hash import generate_comix_hash
from ..utils.logger import get_logger
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session

logger = get_logger(__name__)


_BASE = "https://comix.to/api/v1"
_INVALID_TOKEN_RE = re.compile(r"invalid\s+token|missing\s+token", re.IGNORECASE)

# Process-wide latch. The fast path either works site-wide or it
# doesn't — there's no per-endpoint variation. Once we observe one
# encrypted body or token rejection, skip the fast path for the rest
# of the process to avoid spamming the rate limiter with 403s on
# every per-chapter call. Re-flips on a fresh process / restart, so
# when comix walks back the cipher we'll naturally pick the fast
# path back up.
_FAST_PATH_BROKEN = False


def _fast_path_payload(path: str, *, params: Optional[dict] = None) -> Optional[dict]:
    """
    Sign + GET ``BASE + path``. Return the decoded JSON dict if and only
    if the server replied with a plain-text ``{"status":"ok",...}``
    structure. Returns None on any failure mode (transport error, 403,
    encrypted body, missing keys), so callers can fall through to the
    Playwright path without further error handling.
    """
    global _FAST_PATH_BROKEN
    if _FAST_PATH_BROKEN:
        return None
    token = generate_comix_hash(path)
    full_params = {"_": token}
    if params:
        full_params.update(params)
    url = f"{_BASE}{path}"
    try:
        r = get_session().get(url, timeout=20, params=full_params)
        body = r.json()
    except Exception as e:
        logger.debug(f"comix: fast-path GET {path} failed transport: {e!r}")
        _FAST_PATH_BROKEN = True
        return None
    if not isinstance(body, dict):
        _FAST_PATH_BROKEN = True
        return None
    # Encrypted-body shape: {"e": "<long base64-ish>"} with no other keys.
    if "e" in body and "status" not in body and "result" not in body:
        logger.info("comix: fast-path returned encrypted body — Playwright fallback")
        _FAST_PATH_BROKEN = True
        return None
    if body.get("status") != "ok":
        msg = body.get("message", "")
        if _INVALID_TOKEN_RE.search(str(msg)):
            logger.info("comix: fast-path token rejected (%s) — Playwright fallback", msg)
        else:
            logger.debug("comix: fast-path GET %s returned non-ok: %s", path, body)
        _FAST_PATH_BROKEN = True
        return None
    return body


class ComixAPI:
    """Low-level HTTP client for comix.to's ``/api/v1`` endpoints."""

    BASE_URL = _BASE  # exposed for diagnostic scripts / tests

    # ── URL parsing ─────────────────────────────────────────────────

    @staticmethod
    def extract_manga_code(url: str) -> str:
        """
        Pull the canonical hid from a title URL such as
        ``https://comix.to/title/kl2x6-that-time-i-got-reincarnated-as-a-slime``.
        """
        parts = url.rstrip("/").split("/")
        last = parts[-1] if parts[-1] else parts[-2]
        code = last.split("-")[0]
        logger.debug(f"Extracted manga code: {code} from URL: {url}")
        return code

    @staticmethod
    def chapter_reader_url(hid: str, slug: str, chapter_id: int, number: Any) -> str:
        """Build the ``/title/<hid>-<slug>/<id>-chapter-<n>`` reader URL."""
        seg = f"{hid}-{slug}" if slug else hid
        return f"https://comix.to/title/{seg}/{chapter_id}-chapter-{number}"

    # ── Manga info (no token needed) ────────────────────────────────

    @classmethod
    @retry_with_backoff()
    def get_manga_info(cls, manga_code: str) -> Optional[MangaInfo]:
        url = f"{cls.BASE_URL}/manga/{manga_code}"
        logger.debug(f"Fetching manga info from: {url}")

        response = get_session().get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            logger.error(f"Manga info returned non-ok status: {payload}")
            return None
        data = payload.get("result")
        if not data:
            logger.error(f"Manga info missing result for {manga_code}: {payload}")
            return None

        poster = data.get("poster") or {}
        return MangaInfo(
            manga_id=data.get("id"),
            hash_id=data.get("hid"),
            title=data.get("title", "Unknown"),
            alt_titles=list(data.get("altTitles") or []),
            slug=cls._slug_from_url(data.get("url") or ""),
            rank=data.get("rank"),
            manga_type=data.get("type"),
            poster_url=poster.get("large") or poster.get("medium"),
            original_language=data.get("originalLanguage"),
            status=data.get("status"),
            final_chapter=cls._stringify(data.get("finalChapter")),
            latest_chapter=cls._stringify(data.get("latestChapter")),
            start_date=data.get("startDate"),
            end_date=data.get("endDate"),
            rated_avg=data.get("ratedAvg"),
            rated_count=data.get("ratedCount"),
            follows_total=data.get("followsTotal"),
            is_nsfw=(data.get("contentRating") or "").lower() in ("nsfw", "ero", "explicit"),
            year=data.get("year"),
            genres=[g.get("title") for g in (data.get("genres") or []) if isinstance(g, dict)],
            description=data.get("synopsis", "") or "",
            source="comix",
            source_url=data.get("url") or "",
            artists=[a.get("title") for a in (data.get("artists") or []) if isinstance(a, dict)],
            tags=[t.get("title") for t in (data.get("tags") or []) if isinstance(t, dict)],
        )

    @staticmethod
    def _stringify(value: Any) -> Optional[str]:
        if value is None or value == 0:
            return None
        return str(value)

    @staticmethod
    def _slug_from_url(url: str) -> Optional[str]:
        """``https://comix.to/title/<hid>-<slug>`` → ``<slug>``."""
        try:
            path = urlparse(url).path
        except Exception:
            return None
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2 or parts[0] != "title":
            return None
        last = parts[-1]
        if "-" not in last:
            return None
        return last.split("-", 1)[1] or None

    # ── Chapter list ────────────────────────────────────────────────

    @classmethod
    def get_all_chapters(cls, manga_code: str, slug: str = "") -> list[Chapter]:
        """
        Fetch every chapter for a manga.

        Tries the fast path first (paginated direct GETs with our hash);
        if either the token is rejected or the response is encrypted,
        falls back to scraping the rendered DOM via Playwright.
        """
        chapters = cls._fast_path_chapters(manga_code, slug)
        if chapters:
            return chapters

        from ..utils.comix_capture import ComixCaptureService
        rows = ComixCaptureService.shared().get_chapter_list(manga_code, slug)
        return cls._chapters_from_rows(manga_code, slug, rows)

    @classmethod
    def _fast_path_chapters(
        cls, manga_code: str, slug: str
    ) -> list[Chapter]:
        """
        Direct paginated fetch + parse. Returns an empty list (NOT None)
        on any failure mode — caller treats empty as "fall back".
        """
        path = f"/manga/{manga_code}/chapters"
        all_items: list[dict] = []
        page = 1
        while page < 100:  # safety
            payload = _fast_path_payload(
                path, params={"page": page, "limit": 100, "order[number]": "desc"}
            )
            if payload is None:
                if page == 1:
                    return []  # fast path unavailable
                break  # exhausted available pages
            result = payload.get("result")
            items = (result or {}).get("items") if isinstance(result, dict) else None
            if not items:
                break
            all_items.extend(items)
            if len(items) < 100:
                break
            page += 1

        if not all_items:
            return []

        chapters: list[Chapter] = []
        for chap in all_items:
            cid = chap.get("id") or chap.get("chapter_id")
            number = chap.get("number")
            if cid is None or number is None:
                continue
            group = chap.get("group") or chap.get("scanlation_group")
            if group:
                group_name = group.get("name")
            elif chap.get("is_official"):
                group_name = "Official"
            else:
                group_name = None
            chapters.append(
                Chapter(
                    chapter_id=cid,
                    number=str(number),
                    title=chap.get("name") or chap.get("title"),
                    volume=cls.chapter_reader_url(manga_code, slug, cid, number),
                    votes=chap.get("votes"),
                    group_name=group_name,
                    pages_count=chap.get("pagesCount") or chap.get("pages_count") or 0,
                )
            )
        chapters.reverse()  # oldest first
        logger.info(f"comix fast-path: parsed {len(chapters)} chapters")
        return chapters

    @classmethod
    def _chapters_from_rows(
        cls, manga_code: str, slug: str, rows: list[dict]
    ) -> list[Chapter]:
        """
        Adapt scraped DOM rows from :class:`ComixCaptureService` to
        :class:`Chapter` instances.
        """
        chapters: list[Chapter] = []
        for r in rows:
            cid = r.get("id")
            number = r.get("number")
            if cid is None or number is None:
                continue
            group_name = r.get("group_name")
            if not group_name and r.get("is_official"):
                group_name = "Official"
            chapters.append(
                Chapter(
                    chapter_id=int(cid),
                    number=str(number),
                    title=None,  # not exposed in chapter-list DOM
                    # Stash the reader URL — get_chapter_images reuses it
                    # for the Playwright fallback. Per CLAUDE.md
                    # "Chapter.volume is the per-provider stash field".
                    volume=cls.chapter_reader_url(manga_code, slug, cid, number),
                    group_name=group_name,
                    pages_count=0,  # not in chapter-list DOM either
                )
            )
        # DOM order is newest-first; pipeline expects oldest-first.
        chapters.reverse()
        logger.info(f"comix Playwright: scraped {len(chapters)} chapters")
        return chapters

    # ── Per-chapter pages ───────────────────────────────────────────

    @classmethod
    def get_chapter_images(
        cls, chapter_id: int, chapter_url: str = ""
    ) -> list[str]:
        """
        Fetch the page-image URLs for a single chapter.

        Tries the path-signed fast path first; on encrypted body / token
        rejection, falls back to scraping the rendered reader DOM via
        Playwright (which requires ``chapter_url``).
        """
        payload = _fast_path_payload(f"/chapters/{chapter_id}")
        if payload is not None:
            result = payload.get("result")
            if isinstance(result, dict):
                urls = _extract_page_urls(result)
                if urls:
                    logger.debug(f"comix fast-path: {len(urls)} pages")
                    return urls

        if not chapter_url:
            raise RuntimeError(
                f"comix: cannot Playwright-capture chapter {chapter_id} "
                f"without a reader URL (Chapter.volume was empty)"
            )
        from ..utils.comix_capture import ComixCaptureService
        urls = ComixCaptureService.shared().get_chapter_pages(chapter_url)
        if not urls:
            raise RuntimeError(
                f"comix: Playwright captured chapter {chapter_id} but no "
                f"page URLs were present in the rendered DOM"
            )
        return urls


def _extract_page_urls(result: dict) -> list[str]:
    """
    Pull image URLs out of a non-encrypted ``/api/v1/chapters/{id}``
    response. Handles both shapes HaruNeko documented:

    * ``pages: [{"url": "..."} ...]``
    * ``pages: {"baseUrl": "...", "items": [{...}]}``
    """
    pages = result.get("pages")
    if pages is None:
        return []
    if isinstance(pages, list):
        return [p["url"] for p in pages if isinstance(p, dict) and p.get("url")]
    if isinstance(pages, dict):
        base = pages.get("baseUrl") or ""
        out: list[str] = []
        for item in pages.get("items") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("src") or item.get("path") or ""
            if not url:
                continue
            if url.startswith("http://") or url.startswith("https://"):
                out.append(url)
            else:
                out.append(base.rstrip("/") + "/" + url.lstrip("/"))
        return out
    return []
