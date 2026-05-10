"""
hitomi.la provider.

Hitomi describes a gallery with a small JSON payload (gallery info) and
computes per-page CDN URLs at runtime via a separate ``gg.js`` script
that exports a base path, a routing whitelist, and a hash-rearrange
helper. We fetch both, decode them in Python, and produce static image
URLs that the rest of the pipeline can consume.

URL pattern (current as of 2026-04):
    https://{a|w}{1|2}.gold-usergeneratedcontent.net/{gg.b}{gg.s(hash)}/{hash}.{avif|webp}

- ``a*`` for AVIF, ``w*`` for WEBP. Suffix is ``2`` when ``gg.m(g)``
  whitelists the hash, ``1`` otherwise.
- ``gg.s(hash)`` rearranges the last 3 hex chars of the hash and parses
  them as a hex int → decimal string.
- ``gg.b`` is a deploy-stamped numeric prefix (e.g. ``"1777626001/"``).

A "gallery" maps onto our model as a manga with exactly one chapter.
"""

import json
import re
import threading
from typing import Optional, Tuple

from .base import Provider
from ..core.models import MangaInfo, Chapter
from ..utils.retry import retry_with_backoff
from ..utils.session import get_session
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Gallery URL: /{type}/{slug}-{lang?}-{numeric_id}.html(#anchor)?
# We match the trailing -<digits>.html anchored against the hash/end so
# we don't accidentally pick up a number that happens to live mid-slug.
_GALLERY_ID_RE = re.compile(r"-(\d+)\.html(?:[#?].*)?$", re.IGNORECASE)

# gg.js parsers. gg.b is a quoted numeric path prefix, gg.m's whitelist
# is encoded as a switch with `case <int>:` lines that all fall through
# into ``o = 1; break;``. Anything not in the switch returns 0.
_GG_B_RE = re.compile(r"""\bb\s*:\s*['"]([^'"]+)['"]""")
_GG_M_CASE_RE = re.compile(r"\bcase\s+(\d+)\s*:")


def _hash_g(hash_str: str) -> int:
    """Same value gg.s/gg.m use for routing — last char + previous 2 as hex."""
    m = re.search(r"(..)(.)$", hash_str)
    if not m:
        return 0
    return int(m.group(2) + m.group(1), 16)


class HitomiProvider(Provider):
    """Provider for https://hitomi.la/."""

    name = "hitomi"
    label = "hitomi.la"
    domains = ("hitomi.la",)
    image_referer = "https://hitomi.la/"
    example_url = "https://hitomi.la/manga/<title>-<id>.html"

    def __init__(self) -> None:
        self._gg_b: Optional[str] = None
        self._gg_m: Optional[set[int]] = None
        self._gg_lock = threading.Lock()

    @classmethod
    def matches(cls, url: str) -> bool:
        return "hitomi.la" in (url or "").lower()

    def extract_code(self, url: str) -> str:
        m = _GALLERY_ID_RE.search(url or "")
        if not m:
            raise ValueError(f"Could not find gallery id in URL: {url}")
        return m.group(1)

    # ---- gg.js -----------------------------------------------------

    @retry_with_backoff()
    def _ensure_gg(self) -> Tuple[str, set[int]]:
        """Load and cache gg.b + the gg.m whitelist."""
        with self._gg_lock:
            if self._gg_b is not None and self._gg_m is not None:
                return self._gg_b, self._gg_m

            url = "https://ltn.gold-usergeneratedcontent.net/gg.js"
            logger.debug(f"Fetching hitomi gg.js: {url}")
            response = get_session().get(
                url, timeout=30, headers={"Referer": "https://hitomi.la/"}
            )
            response.raise_for_status()
            text = response.text

            b_match = _GG_B_RE.search(text)
            if not b_match:
                raise RuntimeError("Could not parse gg.b from gg.js")
            gg_b = b_match.group(1)

            cases = {int(m.group(1)) for m in _GG_M_CASE_RE.finditer(text)}
            if not cases:
                raise RuntimeError("Could not parse gg.m table from gg.js")

            self._gg_b = gg_b
            self._gg_m = cases
            logger.debug(f"hitomi gg: b={gg_b!r}, |m|={len(cases)}")
            return gg_b, cases

    # ---- gallery info ---------------------------------------------

    @retry_with_backoff()
    def _fetch_gallery(self, code: str) -> dict:
        url = f"https://ltn.gold-usergeneratedcontent.net/galleries/{code}.js"
        logger.debug(f"Fetching hitomi gallery info: {url}")
        response = get_session().get(
            url, timeout=30, headers={"Referer": "https://hitomi.la/"}
        )
        response.raise_for_status()
        text = response.text.strip()
        # Strip the ``var galleryinfo = `` JS prefix and trailing semicolon.
        text = re.sub(r"^\s*var\s+galleryinfo\s*=\s*", "", text)
        text = text.rstrip().rstrip(";")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse hitomi gallery info: {e}") from e

    # ---- image URL computation ------------------------------------

    def _image_url(self, image: dict) -> str:
        gg_b, gg_m = self._ensure_gg()
        hash_str = image["hash"]
        g = _hash_g(hash_str)
        # subdomain_from_url: suffix is `1 + gg.m(g)`, where gg.m returns
        # 1 iff g is whitelisted, else 0.
        suffix = 2 if g in gg_m else 1

        if image.get("hasavif"):
            sub_letter, ext = "a", "avif"
        elif image.get("haswebp"):
            sub_letter, ext = "w", "webp"
        elif image.get("hasjxl"):
            # Hitomi serves jxl off the same `a*` subdomain group.
            sub_letter, ext = "a", "jxl"
        else:
            # Original-format fallback (rare). Use the 'a' group; if this
            # ever breaks, gg.js's logic for non-webp/avif goes through a
            # bare numeric subdomain we don't currently model.
            sub_letter = "a"
            ext = (image.get("name") or "x.jpg").rsplit(".", 1)[-1].lower() or "jpg"

        # gg.s(hash) is the same int as g, just stringified as decimal.
        full_path = f"{gg_b}{g}/{hash_str}"
        return f"https://{sub_letter}{suffix}.gold-usergeneratedcontent.net/{full_path}.{ext}"

    def _all_image_urls(self, gallery: dict) -> list[str]:
        files = gallery.get("files") or []
        return [self._image_url(f) for f in files]

    # ---- model construction ---------------------------------------

    def _build_manga_info(
        self, code: str, gallery: dict, image_urls: list[str]
    ) -> MangaInfo:
        title = gallery.get("title") or "Unknown Gallery"
        japanese_title = gallery.get("japanese_title") or ""

        artists: list[str] = []
        for a in gallery.get("artists") or []:
            name = (a or {}).get("artist")
            if name:
                artists.append(name)

        tags: list[str] = []
        for t in gallery.get("tags") or []:
            name = (t or {}).get("tag")
            if not name:
                continue
            if (t or {}).get("female"):
                tags.append(f"female:{name}")
            elif (t or {}).get("male"):
                tags.append(f"male:{name}")
            else:
                tags.append(name)

        # Groups, characters, and parodys are flat lists with their own
        # singular keys. Be defensive: hitomi sometimes sets them to null.
        for key, singular in (
            ("groups", "group"),
            ("characters", "character"),
            ("parodys", "parody"),
        ):
            for entry in gallery.get(key) or []:
                name = (entry or {}).get(singular)
                if name:
                    tags.append(name)

        cover_url = image_urls[0] if image_urls else None
        gallery_url = gallery.get("galleryurl") or f"/manga/{code}.html"
        if not gallery_url.startswith("http"):
            gallery_url = "https://hitomi.la" + gallery_url

        return MangaInfo(
            manga_id=int(code) if code.isdigit() else None,
            hash_id=str(code),
            title=title,
            alt_titles=[japanese_title]
            if japanese_title and japanese_title != title
            else [],
            slug=str(code),
            manga_type=gallery.get("type") or "manga",
            poster_url=cover_url,
            original_language=gallery.get("language") or None,
            status="complete",
            final_chapter="1",
            latest_chapter="1",
            is_nsfw=True,
            description=(
                f"hitomi.la gallery #{code} ({len(image_urls)} pages)."
                + (f" Artists: {', '.join(artists)}." if artists else "")
            ),
            source=self.name,
            source_url=gallery_url,
            artists=artists,
            tags=tags,
            genres=tags,
        )

    # ---- Provider interface ---------------------------------------

    def get_manga_info(self, code: str) -> Optional[MangaInfo]:
        gallery = self._fetch_gallery(code)
        urls = self._all_image_urls(gallery)
        return self._build_manga_info(code, gallery, urls)

    def get_chapters(self, code: str) -> list[Chapter]:
        gallery = self._fetch_gallery(code)
        urls = self._all_image_urls(gallery)
        manga = self._build_manga_info(code, gallery, urls)
        chapter = Chapter(
            chapter_id=int(code) if code.isdigit() else 0,
            number="1",
            title=manga.title,
            volume=None,
            votes=None,
            group_name=", ".join(manga.artists) if manga.artists else None,
            pages_count=len(urls),
            image_urls=urls,
        )
        return [chapter]

    def get_chapter_images(self, chapter: Chapter) -> list[str]:
        if chapter.image_urls:
            return list(chapter.image_urls)
        gallery = self._fetch_gallery(str(chapter.chapter_id))
        return self._all_image_urls(gallery)
