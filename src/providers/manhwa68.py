"""
manhwa68.com provider — Madara theme, plain HTTP (no Cloudflare check).

The series page only renders the latest few chapters; the full list
comes from Madara's ``POST <series url>ajax/chapters/``. Some series
start past chapter 1 (Locked With Her begins at chapter 2), so never
guess chapter URLs — take them from that list. Page images are on
``cdn.manhwa68.com`` (older chapters: ``manhwa68.com/wp-content``) and
load without a Referer.
"""

from ._madara import MadaraProvider


class Manhwa68Provider(MadaraProvider):
    name = "manhwa68"
    label = "manhwa68.com"
    domains = ("manhwa68.com",)
    base_url = "https://manhwa68.com"
    series_path = "/manga/"
    ajax_chapters = True
    image_referer = "https://manhwa68.com/"
    example_url = "https://manhwa68.com/manga/<slug>/"
    title_suffixes = (r"^Read\s+", r"\s*-\s*MANHWA68\s*$")
