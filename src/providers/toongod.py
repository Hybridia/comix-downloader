"""
toongod.org provider — Madara theme behind a Cloudflare human check.

Every page (series + reader) is challenged; ``get_session()`` solves it
through FlareSolverr (auto-started), same as manhwaread. Chapters are
rendered inline on the series page. Page images live on
``i.tngcdn.com``, which answers 403 without ``Referer: toongod.org``.
"""

from ._madara import MadaraProvider


class ToongodProvider(MadaraProvider):
    name = "toongod"
    label = "toongod.org"
    domains = ("toongod.org",)
    base_url = "https://www.toongod.org"
    series_path = "/webtoon/"
    image_referer = "https://www.toongod.org/"
    example_url = "https://www.toongod.org/webtoon/<slug>/"
    title_suffixes = (r"\s*Manhwa Free.*$", r"\s*\|\s*ToonGod\s*$")
