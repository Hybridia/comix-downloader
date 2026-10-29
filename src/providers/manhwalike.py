"""
manhwalike.com provider — custom site (not WordPress), plain HTTP.

- Series ``/manga-<slug>``; chapters ``/manga-<slug>-chapter-N-ch<id>``
  (decimal chapters: ``chapter-316-5``). ``extract_code`` accepts both.
- Series page: title ``<div class="main-head"><h1>``, cover og:image,
  "Other name: A; B" (often just the title again), status
  ``<small>Status</small><strong>…``, synopsis ``<p class="about">``
  (the ``<p class="summary">`` next to it is site boilerplate).
- Chapters ``<ul class="chapter-list"><li><a href="…">``, newest-first.
- Reader images are ``<div [id="page-N"] class="page-chapter"><img src|data-src>``
  inside ``<div class="chapter-content">``. Hosts vary by chapter age
  (``stcdn.``/``cdn.manhwalike.com``) and all answer HTTP 520 without
  ``Referer: https://manhwalike.com/`` — image_referer is required.
"""

import re
from html import unescape

from ._madara import MadaraProvider, clean_text, split_alt_titles

_SLUG_RE = re.compile(r"manhwalike\.com/manga-(.+?)(?:-chapter-\d+(?:-\d+)?-ch\d+)?/?\s*(?:[?#]|$)", re.I)
_CHAPTER_RE = re.compile(r"<li>\s*<a\s+href=\"([^\"]+)\"", re.I)
_NUM_RE = re.compile(r"-chapter-(\d+(?:-\d+)?)-ch\d+", re.I)
_PAGE_IMG_RE = re.compile(r'<div[^>]*\bclass="page-chapter"[^>]*>\s*(<img[^>]*>)', re.I)


class ManhwalikeProvider(MadaraProvider):
    name = "manhwalike"
    label = "manhwalike.com"
    domains = ("manhwalike.com",)
    base_url = "https://manhwalike.com"
    image_referer = "https://manhwalike.com/"
    example_url = "https://manhwalike.com/manga-<slug>"

    def extract_code(self, url: str) -> str:
        m = _SLUG_RE.search((url or "").strip())
        if not m:
            raise ValueError(f"Could not find the series slug in URL: {url}")
        return m.group(1)

    def series_url(self, code: str) -> str:
        return f"{self.base_url}/manga-{code}"

    def _parse_metadata(self, html: str, code: str) -> dict:
        title_m = re.search(r'class="main-head">\s*<h1[^>]*>(.*?)</h1>', html, re.S)
        title = clean_text(title_m.group(1)) if title_m else code
        cover_m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        other_m = re.search(r'class="other-name">\s*<span>\s*Other name:\s*(.*?)</span>', html, re.S)
        status_m = re.search(r"<small>\s*Status\s*</small>\s*<strong[^>]*>(.*?)</strong>", html, re.S)
        about_m = re.search(r'<p\s+class="about">(.*?)</p>', html, re.S)
        about = clean_text(about_m.group(1)) if about_m else ""
        if "manhwalike" in about.lower():
            about = ""  # series without a synopsis get site boilerplate here
        return {
            "title": title,
            "cover": unescape(cover_m.group(1)).strip() if cover_m else None,
            "description": about,
            "alt_titles": split_alt_titles(clean_text(other_m.group(1)) if other_m else None, title),
            "status": clean_text(status_m.group(1)) if status_m else None,
        }

    def _parse_chapter_rows(self, html: str, code: str) -> list[tuple[str, str]]:
        start = html.find('class="chapter-list"')
        if start < 0:
            return []
        end = html.find("</ul>", start)
        rows, seen = [], set()
        for href in _CHAPTER_RE.findall(html[start:end if end > 0 else None]):
            url = unescape(href).strip()
            if not url.startswith("http"):
                url = self.base_url + url
            m = _NUM_RE.search(url)
            if url in seen or not m:
                continue
            seen.add(url)
            rows.append((url, m.group(1).replace("-", ".")))
        return rows

    def _extract_images(self, html: str) -> list[str]:
        urls: list[str] = []
        for tag in _PAGE_IMG_RE.findall(html):
            # Lazy pages carry the real URL in data-src and a loading gif in src.
            m = re.search(r'\bdata-src="([^"]+)"', tag) or re.search(r'\bsrc="([^"]+)"', tag)
            url = unescape(m.group(1)).strip() if m else ""
            if url.startswith("http") and url not in urls:
                urls.append(url)
        return urls
