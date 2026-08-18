from typing import List, Optional
import asyncio

from .base import BaseSource, BookMetadata


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
            "limit": limit,
            "fields": "key,title,author_name,first_publish_year,ia,edition_count,public_scan_b,ebook_count_i",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
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
                    license_type="verify_per_item",
                    publication_year=doc.get("first_publish_year"),
                )
            )

        return books

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
        params = {
            "q": "*",
            "sort": "readinglog_count",
            "limit": limit,
            "fields": "key,title,author_name,first_publish_year,public_scan_b",
        }
        try:
            response = await self.client.get(self.SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
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
                    license_type="verify_per_item",
                    publication_year=doc.get("first_publish_year"),
                )
            )
        return books