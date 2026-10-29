"""
URL-based provider router. Pick the right Provider for an arbitrary URL.
"""

from typing import Optional, Type
from .base import Provider
from .comix import ComixProvider
from .nhentai import NhentaiProvider
from .hitomi import HitomiProvider
from .hentaifc import HentaiFCProvider
from .hentairead import HentaireadProvider
from .hentaifox import HentaifoxProvider
from .toonily import ToonilyProvider
from .manhwaread import ManhwareadProvider
from .manhwabuddy import ManhwabuddyProvider
from .manhwa18 import Manhwa18Provider
from .manhwa18net import Manhwa18NetProvider
from .mangadistrict import MangadistrictProvider
from .manga18fx import Manga18fxProvider
from .webtoonscan import WebtoonscanProvider
from .manhwa68 import Manhwa68Provider
from .toongod import ToongodProvider
from .webtoonxyz import WebtoonxyzProvider
from .manhwa18cc import Manhwa18ccProvider
from .manga18me import Manga18meProvider
from .hentai20 import Hentai20Provider
from .manhwalike import ManhwalikeProvider
from .toomics import ToomicsProvider
from .mangafire import MangafireProvider


_REGISTRY: list[Type[Provider]] = [
    ComixProvider,
    NhentaiProvider,
    HitomiProvider,
    HentaiFCProvider,
    HentaireadProvider,
    HentaifoxProvider,
    ToonilyProvider,
    ManhwareadProvider,
    ManhwabuddyProvider,
    Manhwa18Provider,
    Manhwa18NetProvider,
    MangadistrictProvider,
    Manga18fxProvider,
    WebtoonscanProvider,
    Manhwa68Provider,
    ToongodProvider,
    WebtoonxyzProvider,
    Manhwa18ccProvider,
    Manga18meProvider,
    Hentai20Provider,
    ManhwalikeProvider,
    ToomicsProvider,
    MangafireProvider,
]


def register_provider(provider_cls: Type[Provider]) -> None:
    """Register an additional provider class."""
    if provider_cls not in _REGISTRY:
        _REGISTRY.append(provider_cls)


def list_providers() -> list[Type[Provider]]:
    """All currently-registered provider classes."""
    return list(_REGISTRY)


def get_provider_for_url(url: str) -> Optional[Provider]:
    """Return an instantiated provider that handles `url`, or None."""
    if not url:
        return None
    for cls in _REGISTRY:
        if cls.matches(url):
            return cls()
    return None


SUPPORTED_SITES_HUMAN = ", ".join(
    f"{p.label} ({'/'.join(p.domains)})" for p in _REGISTRY
)
