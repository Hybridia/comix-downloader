"""
Shared base for the manga18fx-style engine (manhwa18.cc, manga18.me).

Same operator family as manga18fx.com (identical markup and sidebar),
built on Madara's summary sidebar, so metadata parsing is inherited
from ``MadaraProvider``. The differences:

- Chapters are bare ``<a class="chapter-name …" href="/<path>/<slug>/chapter-N">``
  anchors. The "Read First / Read Last" buttons (``rfirst``/``rlast``)
  and the sidebar's latest-updates list (``btn-link``, other series)
  use other classes, so the class alone isolates the series' chapters.
- Reader pages are ``<img data-src=…>`` inside ``<div class="read-content">``;
  manga18.me writes the attributes with single quotes.
- Series URLs have no trailing slash; slugs can be canonicalised by a
  redirect (manhwa18.cc ``secret-class`` → ``secret-class-01``), which
  is harmless because chapters keep their absolute reader URL.
"""

import re
from html import unescape

from ._madara import MadaraProvider, chapter_number

_CHAPTER_A_RE = re.compile(
    r'<a\s+class="chapter-name[^"]*"\s+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
)
_READ_IMG_RE = re.compile(
    r"""<img[^>]*?\b(?:data-src|src)=(["'])\s*(.+?)\s*\1""", re.I
)


class Manga18EngineProvider(MadaraProvider):

    def series_url(self, code: str) -> str:
        return f"{self.base_url}{self.series_path}{code}"

    def _parse_chapter_rows(self, html: str, code: str) -> list[tuple[str, str]]:
        rows, seen = [], set()
        for href, label in _CHAPTER_A_RE.findall(html):
            url = unescape(href).strip()
            if not url.startswith("http"):
                url = self.base_url + url
            number = chapter_number(url, label)
            if url in seen or number is None:
                continue
            seen.add(url)
            rows.append((url, number))
        return rows

    def _extract_images(self, html: str) -> list[str]:
        start = html.find("read-content")
        if start < 0:
            return []
        # The reader block ends where the first non-image element begins.
        end = html.find("</div>", start)
        scope = html[start:end if end > 0 else None]
        urls: list[str] = []
        for _q, url in _READ_IMG_RE.findall(scope):
            url = unescape(url).strip()
            if url.startswith("http") and url not in urls:
                urls.append(url)
        return urls
