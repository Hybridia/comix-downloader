"""
manhwa18.cc provider — manga18fx-style engine (see ``_manga18.py``).

Unrelated to manhwa18.com / manhwa18.net (different operators); each
provider matches its own exact host. Plain HTTP, no Cloudflare check;
images on ``imgNN.manhwa18.cc`` load without a Referer.
"""

from ._manga18 import Manga18EngineProvider


class Manhwa18ccProvider(Manga18EngineProvider):
    name = "manhwa18cc"
    label = "manhwa18.cc"
    domains = ("manhwa18.cc",)
    base_url = "https://manhwa18.cc"
    series_path = "/webtoon/"
    image_referer = "https://manhwa18.cc/"
    example_url = "https://manhwa18.cc/webtoon/<slug>"
    title_suffixes = (r"^Read\s+", r"\s*Manhwa at Manhwa18CC\s*$")
