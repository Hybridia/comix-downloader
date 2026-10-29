"""
webtoon.xyz provider — Madara theme behind a Cloudflare human check.

Pages are challenged and solved through FlareSolverr by
``get_session()``. The image CDNs (``cdnN.webtoon.xyz``) are challenged
too, but the ``cf_clearance`` cookie FlareSolverr returns is scoped to
``.webtoon.xyz``, so image fetches through the same session pass
(verified: 200 image/jpeg after a page solve, 403 challenge without).
The site mixes adult and general titles; ``is_nsfw`` is set for all,
like the other providers in this group.
"""

from ._madara import MadaraProvider


class WebtoonxyzProvider(MadaraProvider):
    name = "webtoonxyz"
    label = "webtoon.xyz"
    domains = ("webtoon.xyz",)
    base_url = "https://www.webtoon.xyz"
    series_path = "/read/"
    image_referer = "https://www.webtoon.xyz/"
    example_url = "https://www.webtoon.xyz/read/<slug>/"
    title_suffixes = (r"\s*Manhwa\s*:\s*Read Manhwa Free at WEBTOON XYZ\s*$",)
