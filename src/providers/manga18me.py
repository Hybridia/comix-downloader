"""
manga18.me provider — manga18fx-style engine (see ``_manga18.py``).

Plain HTTP, no Cloudflare check. Reader markup uses single-quoted
attributes; images on ``img-rNN.manga18.me`` load without a Referer.
"""

from ._manga18 import Manga18EngineProvider


class Manga18meProvider(Manga18EngineProvider):
    name = "manga18me"
    label = "manga18.me"
    domains = ("manga18.me",)
    base_url = "https://manga18.me"
    series_path = "/manga/"
    image_referer = "https://manga18.me/"
    example_url = "https://manga18.me/manga/<slug>"
    title_suffixes = (r"^Read\s+", r"\s*Manhwa at Manga18\.ME\s*$")
