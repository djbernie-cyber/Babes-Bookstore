from typing import List, Optional
import asyncio
import logging

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)


class OpenLibrarySource(BaseSource):
    """Open Library — verify license per-item before adding."""

    name = "open_library"
    description = "Open Library (license-verified items only)"
    license_type = "verified_per_item"
    rate_limit = 0.5

    SEARCH_URL = "https://openlibrary.org/search.json"
    WORKS_URL = "https://openlibrary.org/works/{work_id}.json"
    EDITIONS_URL = "https://openlibrary.org/books/{edition_id}.json"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        params = {
            "q": query,
            "limit": min(max(limit * 3, 30), 100),
            "fields": "key,title,author_name,first_publish_year,ia,edition_count,public_scan_b,ebook_access",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Open Library search failed", exc_info=True)
            return []

        books: List[BookMetadata] = []
        for doc in data.get("docs", [])[:limit]:
            if not doc.get("public_scan_b"):
                continue

            work_key = doc.get("key", "").replace("/works/", "")
            if not work_key:
                continue

            authors = doc.get("author_name", [])
            author = ", ".join(authors[:3]) if authors else None

            books.append(
                BookMetadata(
                    title=doc.get("title", "Unknown"),
                    author=author,
                    source=self.name,
                    source_id=work_key,
                    source_url=f"https://openlibrary.org/works/{work_key}",
                    license_type=self._licence(doc),
                    publication_year=doc.get("first_publish_year"),
                )
            )

        return books[:limit]

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        await asyncio.sleep(self.rate_limit)
        try:
            response = await self.client.get(self.WORKS_URL.format(work_id=source_id))
            if response.status_code != 200:
                return None
            data = response.json()

            title = data.get("title", "Unknown")
            description = None
            if isinstance(data.get("description"), dict):
                description = data["description"].get("value")
            elif isinstance(data.get("description"), str):
                description = data["description"]

            return BookMetadata(
                title=title,
                description=description,
                source=self.name,
                source_id=source_id,
                source_url=f"https://openlibrary.org/works/{source_id}",
                license_type="verify_per_item",
            )
        except Exception:
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        return None

    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        # `q=*` is not valid Solr syntax here and returns nothing. Restrict to
        # items with a public scan so results are actually redistributable, and
        # over-fetch because many hits are filtered out below.
        params = {
            "q": "public_scan_b:true",
            "sort": "readinglog",
            "limit": min(max(limit * 3, 30), 100),
            "fields": "key,title,author_name,first_publish_year,public_scan_b,ia,ebook_access",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Open Library popular fetch failed", exc_info=True)
            return []

        books: List[BookMetadata] = []
        for doc in data.get("docs", [])[:limit]:
            if not doc.get("public_scan_b"):
                continue
            work_key = doc.get("key", "").replace("/works/", "")
            if not work_key:
                continue
            authors = doc.get("author_name", [])
            books.append(
                BookMetadata(
                    title=doc.get("title", "Unknown"),
                    author=", ".join(authors[:3]) if authors else None,
                    source=self.name,
                    source_id=work_key,
                    source_url=f"https://openlibrary.org/works/{work_key}",
                    license_type=self._licence(doc),
                    publication_year=doc.get("first_publish_year"),
                )
            )
        return books[:limit]

    @staticmethod
    def _licence(doc: dict) -> str:
        """Public scans of pre-1929 works are public domain in the US.

        Anything newer stays "verify_per_item" so the licence verifier holds
        it for manual review rather than auto-publishing it.
        """
        year = doc.get("first_publish_year")
        if doc.get("public_scan_b") and isinstance(year, int) and year < 1929:
            return "public_domain"
        return "verify_per_item"
