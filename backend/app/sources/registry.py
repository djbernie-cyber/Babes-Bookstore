"""Source registry.

Sources are registered as *classes* and instantiated on demand. Each
instance owns an httpx client, and scrape tasks call `close()` when done —
so sharing a single long-lived instance (the previous behaviour) left the
registry handing out sources with closed transports after the first run.
"""
from typing import Dict, List, Type

from .base import BaseSource
from .doab import DOABSource
from .gutenberg import GutenbergSource
from .internet_archive import InternetArchiveSource
from .oapen import OAPENSource
from .open_library import OpenLibrarySource
from .openstax import OpenStaxSource
from .standard_ebooks import StandardEbooksSource
from .wikisource import WikisourceSource

#: Registered in rough order of catalogue quality.
SOURCE_CLASSES: tuple[Type[BaseSource], ...] = (
    GutenbergSource,        # ~79,000 public domain ebooks
    StandardEbooksSource,   # ~3,500 professionally typeset
    WikisourceSource,       # proofread transcriptions
    OpenStaxSource,         # CC BY university textbooks
    InternetArchiveSource,  # per-item verified
    DOABSource,             # CC-licensed academic books
    OAPENSource,            # open access academic
    OpenLibrarySource,      # metadata + public scans
)


class SourceRegistry:
    """Creates source adapters by name."""

    def __init__(self, classes: tuple[Type[BaseSource], ...] = SOURCE_CLASSES):
        self._classes: Dict[str, Type[BaseSource]] = {c.name: c for c in classes}

    def get(self, name: str) -> BaseSource:
        """Return a *new* adapter instance for `name`.

        Raises:
            KeyError: if the source is not registered.
        """
        try:
            return self._classes[name]()
        except KeyError:
            raise KeyError(f"Source '{name}' not registered") from None

    def describe(self) -> Dict[str, dict]:
        """Metadata for every source, without opening HTTP clients."""
        return {
            name: {
                "description": cls.description,
                "license_type": cls.license_type,
                "rate_limit": cls.rate_limit,
                "requires_api_key": cls.requires_api_key,
            }
            for name, cls in self._classes.items()
        }

    def all(self) -> Dict[str, Type[BaseSource]]:
        return dict(self._classes)

    def list_names(self) -> List[str]:
        return list(self._classes)

    def __contains__(self, name: object) -> bool:
        return name in self._classes


source_registry = SourceRegistry()
