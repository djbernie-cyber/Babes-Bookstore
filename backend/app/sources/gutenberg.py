"""Project Gutenberg adapter.

Uses Gutendex (https://gutendex.com), the maintained JSON API over the
Gutenberg catalogue. The legacy `/ebooks/search.opds` endpoint now returns
403 to automated clients, which previously made this source return zero
books.

Everything on Gutenberg is public domain in the US.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from .base import BaseSource, BookMetadata

logger = logging.getLogger(__name__)

LICENSE_URL = "https://www.gutenberg.org/policy/license.html"


class GutenbergSource(BaseSource):
    """Project Gutenberg — ~79,000 public domain ebooks."""

    name = "gutenberg"
    description = "Project Gutenberg — public domain ebooks"
    license_type = "public_domain"
    rate_limit = 0.3

    API_URL = "https://gutendex.com/books"
    PAGE_SIZE = 32  # Gutendex fixed page size

    async def search(self, query: str, limit: int = 20) -> List[BookMetadata]:
        return await self._collect({"search": query} if query else {}, limit)

    async def list_popular(self, limit: int = 50) -> List[BookMetadata]:
        # Gutendex sorts by download count by default.
        return await self._collect({"sort": "popular"}, limit)

    async def get_metadata(self, source_id: str) -> Optional[BookMetadata]:
        try:
            response = await self.client.get(f"{self.API_URL}/{source_id}")
            if response.status_code != 200:
                return None
            return self._parse(response.json())
        except Exception:
            logger.warning("Gutenberg metadata fetch failed for %s", source_id, exc_info=True)
            return None

    async def download(self, metadata: BookMetadata) -> Optional[bytes]:
        """Fetch the best available file, preferring EPUB then PDF then text."""
        candidates = [metadata.epub_url, metadata.pdf_url]
        candidates += [metadata.source_metadata.get("text_url")]

        for url in [u for u in candidates if u]:
            try:
                await asyncio.sleep(self.rate_limit)
                response = await self.client.get(url, follow_redirects=True)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception:
                logger.debug("Gutenberg download failed: %s", url, exc_info=True)
        return None

    async def _collect(self, params: Dict[str, Any], limit: int) -> List[BookMetadata]:
        """Page through the API until `limit` books are gathered."""
        books: List[BookMetadata] = []
        url: Optional[str] = self.API_URL
        query: Optional[Dict[str, Any]] = {**params, "copyright": "false"}

        while url and len(books) < limit:
            try:
                response = await self.client.get(url, params=query, follow_redirects=True)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                logger.warning("Gutenberg fetch failed (%s)", url, exc_info=True)
                break

            for raw in payload.get("results", []):
                book = self._parse(raw)
                if book:
                    books.append(book)
                    if len(books) >= limit:
                        break

            url = payload.get("next")
            query = None  # `next` already carries the querystring
            if url:
                await asyncio.sleep(self.rate_limit)

        return books[:limit]

    def _parse(self, raw: Dict[str, Any]) -> Optional[BookMetadata]:
        book_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        if not book_id or not title:
            return None

        # Gutendex exposes `copyright: true` for the rare restricted item.
        if raw.get("copyright") is True:
            return None

        authors = [a.get("name") for a in raw.get("authors", []) if a.get("name")]
        formats: Dict[str, str] = raw.get("formats", {}) or {}

        def pick(*needles: str) -> Optional[str]:
            for mime, href in formats.items():
                if any(n in mime for n in needles) and not href.endswith(".zip"):
                    return href
            return None

        year = None
        for author in raw.get("authors", []):
            if author.get("death_year"):
                year = author["death_year"]
                break

        languages = raw.get("languages") or ["en"]

        return BookMetadata(
            title=title[:500],
            author=", ".join(authors[:3]) or None,
            description=(raw.get("summaries") or [None])[0],
            source=self.name,
            source_id=str(book_id),
            source_url=f"https://www.gutenberg.org/ebooks/{book_id}",
            source_metadata={
                "download_count": raw.get("download_count"),
                "subjects": (raw.get("subjects") or [])[:8],
                "text_url": pick("text/plain"),
            },
            license_type="public_domain",
            license_url=LICENSE_URL,
            epub_url=pick("application/epub"),
            pdf_url=pick("application/pdf"),
            cover_url=pick("image/jpeg"),
            category=(raw.get("bookshelves") or [None])[0],
            tags=[s for s in (raw.get("subjects") or [])[:5]],
            language=languages[0],
            publication_year=year,
        )
