"""
Site provider abstraction. Each provider knows how to talk to one source
(comix.to, nhentai.to, ...) and exposes a uniform interface to the rest of
the downloader.
"""

from .base import Provider
from .router import (
    get_provider_for_url,
    list_providers,
    register_provider,
    SUPPORTED_SITES_HUMAN,
)

__all__ = [
    "Provider",
    "get_provider_for_url",
    "list_providers",
    "register_provider",
    "SUPPORTED_SITES_HUMAN",
]
