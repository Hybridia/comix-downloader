"""
hentai20.io provider — WordPress "MangaReader" theme (not Madara).

- Series ``/manga/<slug>/``: title in ``<h1 class="entry-title">``,
  cover is the ``<div class="thumb">`` image — a ``-193x278`` thumbnail,
  but the only size published (the un-suffixed file 404s), status in the
  ``infotable``. No og:image and no alternative-titles field.
- Chapters are ``<div class="eph-num"><a href="/<slug>-chapter-N/">``,
  newest-first. Note chapter URLs sit at the site root, not under
  ``/manga/``, so ``extract_code`` accepts both shapes.
- Reader images are in ``<div id="readerarea">``, listed twice (a
  ``<noscript>`` copy and the live copy) — de-duplicated in order.
  The CDN (``img.hentai1.io``) needs no Referer.
"""

import re
from html import unescape

from ._madara import MadaraProvider, clean_text

_CHAPTER_RE = re.compile(r'<div\s+class="eph-num">\s*<a\s+href="([^"]+)"', re.I)
_NUM_RE = re.compile(r"-chapter-(\d+(?:-\d+)?)/?$", re.I)
_IMG_RE = re.compile(r'<img[^>]*?\bsrc="([^"]+)"', re.I)


class Hentai20Provider(MadaraProvider):
    name = "hentai20"
    label = "hentai20.io"
    domains = ("hentai20.io",)
    base_url = "https://hentai20.io"
    series_path = "/manga/"
    image_referer = "https://hentai20.io/"
    example_url = "https://hentai20.io/manga/<slug>/"

    def extract_code(self, url: str) -> str:
        m = re.search(r"/manga/([^/?#]+)", url or "") or re.search(
            r"hentai20\.io/([^/?#]+?)-chapter-\d+(?:-\d+)?/?(?:[?#]|$)", url or ""
        )
        if not m:
            raise ValueError(f"Could not find the series slug in URL: {url}")
        return m.group(1)

    def _parse_metadata(self, html: str, code: str) -> dict:
        title_m = re.search(r'<h1[^>]*class="entry-title"[^>]*>(.*?)</h1>', html, re.S)
        cover_m = re.search(r'<div\s+class="thumb"[^>]*>.*?<img[^>]*?\bsrc="([^"]+)"', html, re.S)
        status_m = re.search(r"<td>\s*Status\s*</td>\s*<td>(.*?)</td>", html, re.S)
        desc_m = re.search(r'<meta\s+property="og:description"\s+content="([^"]+)"', html)
        cover = unescape(cover_m.group(1)) if cover_m else None
        return {
            "title": clean_text(title_m.group(1)) if title_m else code,
            "cover": cover,
            "description": clean_text(desc_m.group(1)) if desc_m else "",
            "alt_titles": [],
            "status": clean_text(status_m.group(1)) if status_m else None,
        }

    def _parse_chapter_rows(self, html: str, code: str) -> list[tuple[str, str]]:
        rows, seen = [], set()
        for href in _CHAPTER_RE.findall(html):
            url = unescape(href).strip()
            m = _NUM_RE.search(url)
            if url in seen or not m:
                continue
            seen.add(url)
            rows.append((url, m.group(1).replace("-", ".")))
        return rows

    def _extract_images(self, html: str) -> list[str]:
        start = html.find('id="readerarea"')
        if start < 0:
            return []
        end = html.find("</div>", start)
        urls: list[str] = []
        for url in _IMG_RE.findall(html[start:end if end > 0 else None]):
            url = unescape(url).strip()
            if url.startswith("http") and "/wp-content/themes/" not in url and url not in urls:
                urls.append(url)
        return urls
