from typing import Dict, Type
from .base import BaseSource
from .gutenberg import GutenbergSource
from .standard_ebooks import StandardEbooksSource
from .open_library import OpenLibrarySource
from .internet_archive import InternetArchiveSource
from .doab import DOABSource
from .oapen import OAPENSource


class SourceRegistry:
    """Registry of all available book sources."""

    def __init__(self):
        self._sources: Dict[str, BaseSource] = {}
        self._register_defaults()

    def _register_defaults(self):
        for cls in (
            GutenbergSource,
            StandardEbooksSource,
            OpenLibrarySource,
            InternetArchiveSource,
            DOABSource,
            OAPENSource,
        ):
            instance = cls()
            self._sources[instance.name] = instance

    def get(self, name: str) -> BaseSource:
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not registered")
        return self._sources[name]

    def all(self) -> Dict[str, BaseSource]:
        return dict(self._sources)

    def list_names(self) -> list[str]:
        return list(self._sources.keys())

    async def close_all(self):
        for source in self._sources.values():
            await source.close()


source_registry = SourceRegistry()