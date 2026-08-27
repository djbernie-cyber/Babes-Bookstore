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
    rate_limit = 1.0

    API_URL = "https://gutendex.com/books"
    PAGE_SIZE = 32  # Gutendex fixed page size

    async def search(self, query: str, limit: int = 20, start_page: int = 1) -> List[BookMetadata]:
        return await self._collect({"search": query} if query else {}, limit, start_page)

    async def list_popular(self, limit: int = 50, start_page: int = 1) -> List[BookMetadata]:
        # Gutendex sorts by download count by default.
        return await self._collect({"sort": "popular", "languages": "en"}, limit, start_page)

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

    async def _get_page(self, query: Dict[str, Any], page: int) -> dict:
        """Fetch a single results page, retrying on transient failures.

        Gutenberg rate-limits / occasionally drops connections under load, so a
        single failed request must not abort the whole import. We retry with
        exponential backoff and re-raise only after the budget is exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                response = await self.client.get(
                    self.API_URL, params={**query, "page": page}, follow_redirects=True
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - retry regardless of cause
                last_exc = exc
                await asyncio.sleep(min(2 ** attempt, 16))
        logger.warning("Gutenberg page %s failed after retries", page)
        raise last_exc if last_exc else RuntimeError("unknown fetch error")

    async def _collect(
        self, params: Dict[str, Any], limit: int, start_page: int = 1
    ) -> List[BookMetadata]:
        """Page through the API until `limit` books are gathered.

        Starts at `start_page` so large imports can be resumed in batches
        without re-fetching earlier pages. A page that keeps failing is skipped
        rather than aborting the run, so a brief outage can't truncate the
        catalogue.
        """
        books: List[BookMetadata] = []
        query: Dict[str, Any] = {**params, "copyright": "false"}
        page = max(1, start_page)
        failures = 0

        while len(books) < limit:
            try:
                payload = await self._get_page(query, page)
            except Exception:
                failures += 1
                if failures >= 10:
                    logger.warning(
                        "Too many consecutive Gutenberg failures; stopping at page %s", page
                    )
                    break
                page += 1
                await asyncio.sleep(self.rate_limit * 2)
                continue

            failures = 0
            results = payload.get("results", [])
            for raw in results:
                book = self._parse(raw)
                if book:
                    books.append(book)
                    if len(books) >= limit:
                        break

            if not results or not payload.get("next"):
                break  # reached the end of the catalogue
            page += 1
            await asyncio.sleep(self.rate_limit)

        return books[:limit]

    @staticmethod
    def _categorise(bookshelves, subjects):
        """Best-effort genre from Gutenberg bookshelves / subjects."""
        hay = " ".join(bookshelves or []) + " " + " ".join(subjects or [])
        hay = hay.lower()
        rules = [
            ("mystery", "Mystery & Detective"),
            ("detective", "Mystery & Detective"),
            ("horror", "Gothic & Horror"),
            ("gothic", "Gothic & Horror"),
            ("ghost", "Gothic & Horror"),
            ("science fiction", "Science Fiction"),
            ("fantasy", "Fantasy"),
            ("fairy", "Children & Fairy Tales"),
            ("children", "Children & Fairy Tales"),
            ("adventure", "Adventure"),
            ("western", "Adventure"),
            ("romance", "Romance"),
            ("love", "Romance"),
            ("poetry", "Poetry"),
            ("drama", "Drama"),
            ("play", "Drama"),
            ("history", "History"),
            ("philosophy", "Philosophy"),
            ("religion", "Philosophy"),
            ("biography", "Biography"),
            ("cooking", "Non-Fiction"),
            ("art", "Non-Fiction"),
        ]
        for needle, label in rules:
            if needle in hay:
                return label
        if bookshelves:
            shelf = bookshelves[0].split(":")[0].strip().title()
            if shelf:
                return shelf
        return "Classics"

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
        if "en" not in languages:
            return None  # keep the store English-only and clean

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
            category=self._categorise(raw.get("bookshelves"), raw.get("subjects")),
            tags=[s for s in (raw.get("subjects") or [])[:5]],
            language=languages[0],
            publication_year=year,
        )
