"""OpenStax adapter.

OpenStax publishes peer-reviewed university textbooks under CC BY 4.0,
which permits commercial redistribution with attribution. High value for
"study" and "science" bundles.
"""
import asyncio
import re
import logging
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

BASE = "https://openstax.org"


class OpenStaxSource(BaseSource):
    """OpenStax — CC BY licensed university textbooks."""

    name = "openstax"
    description = "OpenStax — peer-reviewed CC BY university textbooks"
    license_type = "cc_by_4.0"
    rate_limit = 0.5

    API_URL = f"{BASE}/apps/cms/api/v2/pages"

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        books = await self._catalogue(limit if not query else 200)
        if not query:
            return books[:limit]
        q = query.lower()
        return [
            b for b in books
            if q in b.title.lower() or q in " ".join(b.tags).lower()
        ][:limit]

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        return await self._catalogue(limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        for book in await self._catalogue(300):
            if book.source_id == source_id:
                return book
        return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        if not metadata.pdf_url:
            return None
        try:
            await asyncio.sleep(self.rate_limit)
            response = await self.client.get(metadata.pdf_url, timeout=120.0)
            if response.status_code == 200 and response.content[:4] == b"%PDF":
                return response.content
        except Exception:
            logger.debug("OpenStax download failed: %s", metadata.pdf_url, exc_info=True)
        return None

    async def _catalogue(self, limit: int) -> List[BookMetadata]:
        """Fetch the book list, paging through the CMS API.

        The API rejects unknown field names with 400, so we request a
        conservative set and read the rest from each item's `meta` block.
        """
        books: List[BookMetadata] = []
        offset = 0
        page_size = 100

        while len(books) < limit:
            try:
                response = await self.client.get(self.API_URL, params={
                    "type": "books.Book",
                    "fields": "title,book_subjects,description,cover_url,high_resolution_pdf_url,authors",
                    "limit": min(page_size, limit - len(books)),
                    "offset": offset,
                    "format": "json",
                })
                response.raise_for_status()
                payload = response.json()
            except Exception:
                logger.warning("OpenStax catalogue fetch failed", exc_info=True)
                break

            items = payload.get("items", [])
            if not items:
                break

            for item in items:
                book = self._parse(item)
                if book:
                    books.append(book)

            offset += len(items)
            total = payload.get("meta", {}).get("total_count")
            if total is not None and offset >= total:
                break
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    def _parse(self, raw: Dict[str, Any]) -> Optional[BookMetadata]:
        title = (raw.get("title") or "").strip()
        meta = raw.get("meta") or {}
        slug = raw.get("slug") or meta.get("slug")
        if not title or not slug:
            return None

        subjects = raw.get("book_subjects") or raw.get("subjects") or []
        if isinstance(subjects, str):
            subjects = [subjects]
        subjects = [str(s) for s in subjects if s]

        description = raw.get("description")
        if isinstance(description, str):
            # The CMS returns HTML fragments for descriptions.
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip() or None

        return BookMetadata(
            title=title[:500],
            author=self._authors(raw),
            description=description,
            source=self.name,
            source_id=str(slug),
            source_url=meta.get("html_url") or f"{BASE}/details/books/{slug}",
            license_type="cc_by_4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            pdf_url=raw.get("high_resolution_pdf_url"),
            cover_url=raw.get("cover_url"),
            category=(subjects[0] if subjects else "textbook"),
            tags=subjects[:5],
            language="en",
        )

    @staticmethod
    def _authors(raw: Dict[str, Any]) -> str:
        """OpenStax books are collectively authored; fall back to the imprint."""
        names = []
        for entry in raw.get("authors") or []:
            if isinstance(entry, dict):
                name = entry.get("value", {}).get("name") if isinstance(entry.get("value"), dict) else entry.get("name")
                if name:
                    names.append(str(name))
        return ", ".join(names[:3]) or "OpenStax"
